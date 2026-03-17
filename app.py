"""Gradio interactive quiz app.

Two modes
---------
Practice  — select an answer and get immediate feedback + rationale; move on with Next.
Exam      — navigate freely with Prev/Next; Submit appears once all questions answered;
            timer auto-submits on expiry.

Launch with:
    uv run --group app python app.py
"""

from __future__ import annotations

import html as _html
import json
import time
from pathlib import Path

import gradio as gr

from src.common.config import get_settings, project_root

_LETTER = "ABCD"

# ---------------------------------------------------------------------------
# Path / data helpers
# ---------------------------------------------------------------------------


def _quizzes_dir() -> Path:
    return project_root() / get_settings().quiz.quizzes_dir


def _list_quizzes() -> list[str]:
    d = _quizzes_dir()
    if not d.exists():
        return []
    return sorted(p.stem.replace(".gradio", "") for p in d.glob("*.gradio.json"))


def _load_quiz(name: str) -> dict | None:
    path = _quizzes_dir() / f"{name}.gradio.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def _initial_state() -> dict:
    return {
        "quiz": None,
        "quiz_name": "",
        "idx": 0,
        "answers": [],  # 1-based answer index per question, None = unanswered
        "mode": "practice",  # "practice" | "exam"
        "start_time": None,  # Unix timestamp when exam started; None = inactive
        "limit_seconds": 0,
    }


def _total(state: dict) -> int:
    q = state.get("quiz")
    return len(q["questions"]) if q else 0


def _current_q(state: dict) -> dict | None:
    q = state.get("quiz")
    if not q:
        return None
    qs = q["questions"]
    idx = state["idx"]
    return qs[idx] if idx < len(qs) else None


def _score(state: dict) -> int:
    q = state.get("quiz")
    if not q:
        return 0
    return sum(
        1
        for i, ans in enumerate(state["answers"])
        if i < len(q["questions"]) and ans == q["questions"][i]["correct_answer"]
    )


def _all_answered(state: dict) -> bool:
    return bool(state.get("answers")) and all(a is not None for a in state["answers"])


def _record_answer(state: dict, choice: str | None) -> None:
    if choice is None or not state.get("quiz"):
        return
    letter = choice.split(")")[0].strip() if ")" in choice else choice
    chosen_idx = _LETTER.index(letter) + 1 if letter in _LETTER else None
    idx = state["idx"]
    if idx < len(state["answers"]):
        state["answers"][idx] = chosen_idx


def _stored_choice(state: dict) -> str | None:
    """Return the radio choice string for the stored answer at current idx."""
    idx = state["idx"]
    answers = state.get("answers", [])
    if idx >= len(answers) or answers[idx] is None:
        return None
    ans = answers[idx]
    choices = _choices_for(state)
    return choices[ans - 1] if 1 <= ans <= len(choices) else None


# ---------------------------------------------------------------------------
# HTML rendering (all LLM-generated text escaped)
# ---------------------------------------------------------------------------


def _question_html(state: dict, with_feedback: bool = False) -> str:
    q = _current_q(state)
    if q is None:
        return "<p style='color:grey'>No question loaded.</p>"
    idx = state["idx"]
    total = _total(state)
    section = _html.escape(q.get("section", ""))
    text = _html.escape(q.get("question", ""))
    section_tag = (
        f"<p style='color:#7f8c8d;font-size:0.85em;margin:0'>{section}</p>" if section else ""
    )
    out = f"{section_tag}<h3 style='margin:0.3em 0'>Q{idx + 1} / {total}</h3><p>{text}</p>"

    if with_feedback:
        ans = state["answers"][idx] if idx < len(state["answers"]) else None
        correct = q["correct_answer"]
        is_correct = ans == correct
        correct_letter = _LETTER[correct - 1]
        wrong = f"<span style='color:#c0392b'>❌ Incorrect — correct: {correct_letter})</span>"
        verdict = "<span style='color:#27ae60'>✅ Correct!</span>" if is_correct else wrong
        rationale = _html.escape(q.get("explanation", ""))
        out += f"<div style='margin-top:0.8em'><strong>{verdict}</strong>"
        if rationale:
            out += f"<p style='margin-top:0.4em'><em>Explanation:</em> {rationale}</p>"
        out += "</div>"
    return out


def _choices_for(state: dict) -> list[str]:
    q = _current_q(state)
    if not q:
        return []
    return [f"{_LETTER[i]}) {opt}" for i, opt in enumerate(q.get("options", []))]


def _report_html(state: dict) -> str:
    quiz = state.get("quiz")
    if not quiz:
        return ""
    exam = quiz.get("exam_info", {})
    total = _total(state)
    score = _score(state)
    passing = exam.get("passing_score", 70)
    pct = round(score / total * 100) if total else 0
    passed = pct >= passing
    badge = "🎉 PASSED" if passed else "❌ FAILED"
    color = "#27ae60" if passed else "#c0392b"

    lines = [
        f"<h2 style='color:{color}'>{badge} — {pct}%</h2>",
        f"<p><strong>Score:</strong> {score} / {total} correct (passing: {passing}%)</p>",
        "<hr><h3>Review</h3><ol style='padding-left:1.2em'>",
    ]
    for i, q in enumerate(quiz["questions"]):
        user_ans = state["answers"][i] if i < len(state["answers"]) else None
        correct = q["correct_answer"]
        options = q.get("options", [])
        user_letter = _LETTER[user_ans - 1] if user_ans and 1 <= user_ans <= 4 else "–"
        correct_letter = _LETTER[correct - 1]
        ok = "✅" if user_ans == correct else "❌"
        correct_text = _html.escape(options[correct - 1]) if 0 < correct <= len(options) else ""
        explanation = _html.escape(q.get("explanation", ""))
        snippet = _html.escape(q["question"])
        lines.append("<li style='margin-bottom:1em'>")
        lines.append(f"<strong>{ok} {snippet}</strong><br>")
        lines.append(
            f"Your answer: <em>{user_letter}</em> &nbsp;|&nbsp; "
            f"Correct: <em>{correct_letter}) {correct_text}</em>"
        )
        if explanation:
            lines.append(f"<br><span style='color:#555;font-size:0.9em'>💡 {explanation}</span>")
        lines.append("</li>")
    lines.append("</ol>")
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"## ⏱ {s // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------------------
# Output contract — 9 components
#   state, question_html, radio,
#   btn_prev, btn_next, btn_submit_exam,
#   report_html, timer_md, btn_restart
# ---------------------------------------------------------------------------


def _blank_outputs() -> tuple:
    return (
        _initial_state(),
        gr.update(value="", visible=False),  # question_html
        gr.update(choices=[], value=None, visible=False),  # radio
        gr.update(visible=False),  # btn_prev
        gr.update(visible=False),  # btn_next
        gr.update(visible=False),  # btn_submit_exam
        gr.update(value="", visible=False),  # report_html
        gr.update(value="", visible=False),  # timer_md
        gr.update(visible=False),  # btn_restart
    )


def _report_outputs(state: dict) -> tuple:
    """Transition to the final report screen."""
    state = {**state, "start_time": None}
    return (
        state,
        gr.update(value="", visible=False),
        gr.update(choices=[], value=None, visible=False),
        gr.update(visible=False),  # btn_prev
        gr.update(visible=False),  # btn_next
        gr.update(visible=False),  # btn_submit_exam
        gr.update(value=_report_html(state), visible=True),
        gr.update(value="", visible=False),  # hide timer
        gr.update(visible=True),  # btn_restart
    )


def _exam_question_outputs(state: dict) -> tuple:
    """Render the current exam question with correct nav-button states."""
    idx = state["idx"]
    total = _total(state)
    return (
        state,
        gr.update(value=_question_html(state), visible=True),
        gr.update(
            choices=_choices_for(state),
            value=_stored_choice(state),
            interactive=True,
            visible=True,
        ),
        gr.update(visible=idx > 0),  # btn_prev: disabled at Q1
        gr.update(visible=idx < total - 1),  # btn_next: disabled at last Q
        gr.update(visible=_all_answered(state)),  # btn_submit_exam
        gr.update(value="", visible=False),  # report
        gr.update(),  # timer: leave as-is
        gr.update(visible=False),  # btn_restart
    )


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def on_start(name: str, mode: str) -> tuple:
    """Start button: load quiz and show first question."""
    if not name:
        return _blank_outputs()
    quiz = _load_quiz(name)
    if quiz is None:
        return _blank_outputs()

    state = _initial_state()
    state["quiz"] = quiz
    state["quiz_name"] = name
    state["mode"] = mode.lower()
    state["answers"] = [None] * len(quiz.get("questions", []))

    is_exam = state["mode"] == "exam"
    exam_info = quiz.get("exam_info", {})
    limit_seconds = exam_info.get("time_limit_minutes", 30) * 60

    if is_exam:
        state["start_time"] = time.time()
        state["limit_seconds"] = limit_seconds
        return (
            state,
            gr.update(value=_question_html(state), visible=True),
            gr.update(choices=_choices_for(state), value=None, interactive=True, visible=True),
            gr.update(visible=False),  # btn_prev (at Q1)
            gr.update(visible=_total(state) > 1),  # btn_next
            gr.update(visible=False),  # btn_submit_exam (not all answered yet)
            gr.update(value="", visible=False),  # report
            gr.update(value=_fmt_time(limit_seconds), visible=True),
            gr.update(visible=False),  # btn_restart
        )
    else:
        # Practice: show first question; radio.change handles feedback
        return (
            state,
            gr.update(value=_question_html(state), visible=True),
            gr.update(choices=_choices_for(state), value=None, interactive=True, visible=True),
            gr.update(visible=False),  # btn_prev
            gr.update(visible=False),  # btn_next (appears after answering)
            gr.update(visible=False),  # btn_submit_exam
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(visible=False),
        )


def on_answer(state: dict, choice: str | None) -> tuple:
    """Fires whenever the radio value changes.

    Practice: show immediate feedback, lock radio, reveal Next.
    Exam:     save answer, update Submit Exam visibility.
    """
    # Guard: ignore programmatic resets (value→None when loading next question)
    if choice is None or not state.get("quiz"):
        return (state,) + (gr.update(),) * 8

    mode = state.get("mode", "practice")
    state = {**state}  # fresh dict to ensure Gradio detects state change

    if mode == "practice":
        _record_answer(state, choice)
        idx = state["idx"]
        is_last = idx >= _total(state) - 1
        return (
            state,
            gr.update(value=_question_html(state, with_feedback=True), visible=True),
            gr.update(interactive=False),  # lock radio
            gr.update(visible=False),  # btn_prev
            gr.update(visible=True, value="Next →" if not is_last else "See Results →"),
            gr.update(visible=False),  # btn_submit_exam
            gr.update(value="", visible=False),
            gr.update(),  # timer: no-op
            gr.update(visible=False),
        )
    else:  # exam
        _record_answer(state, choice)
        return (
            state,
            gr.update(),  # question_html: no-op
            gr.update(),  # radio: keep selection
            gr.update(),  # btn_prev: no-op
            gr.update(),  # btn_next: no-op
            gr.update(visible=_all_answered(state)),  # reveal Submit when done
            gr.update(value="", visible=False),
            gr.update(),
            gr.update(visible=False),
        )


def on_next(state: dict) -> tuple:
    """Practice mode: advance after feedback (or show report on last question)."""
    new_idx = state["idx"] + 1
    state = {**state, "idx": new_idx}

    if new_idx >= _total(state):
        return _report_outputs(state)

    return (
        state,
        gr.update(value=_question_html(state), visible=True),
        gr.update(choices=_choices_for(state), value=None, interactive=True, visible=True),
        gr.update(visible=False),  # btn_prev
        gr.update(visible=False),  # btn_next (hidden until next answer)
        gr.update(visible=False),  # btn_submit_exam
        gr.update(value="", visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
    )


def on_prev_exam(state: dict) -> tuple:
    if state["idx"] == 0:
        return _exam_question_outputs(state)
    state = {**state, "idx": state["idx"] - 1}
    return _exam_question_outputs(state)


def on_next_exam(state: dict) -> tuple:
    total = _total(state)
    if state["idx"] >= total - 1:
        return _exam_question_outputs(state)
    state = {**state, "idx": state["idx"] + 1}
    return _exam_question_outputs(state)


def on_submit_exam(state: dict) -> tuple:
    return _report_outputs(state)


def on_restart(state: dict, mode: str) -> tuple:
    return on_start(state.get("quiz_name", ""), mode)


def on_timer_tick(state: dict) -> tuple:
    """Server-side countdown tick; auto-submits when time expires."""
    if state.get("mode") != "exam" or state.get("start_time") is None:
        return (state,) + (gr.update(),) * 8

    remaining = state["limit_seconds"] - (time.time() - state["start_time"])
    if remaining <= 0:
        return _report_outputs(state)

    return (
        state,
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(value=_fmt_time(remaining), visible=True),
        gr.update(),
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def build_ui() -> gr.Blocks:
    available = _list_quizzes()

    with gr.Blocks(title="NanoClaw Quiz") as demo:
        gr.Markdown("# NanoClaw Quiz")

        state = gr.State(_initial_state())

        mode_radio = gr.Radio(
            choices=["Practice", "Exam"],
            value="Practice",
            label="Mode",
            info=(
                "Practice: select an answer to see immediate feedback. "
                "Exam: navigate freely, submit when ready (timer auto-submits)."
            ),
        )

        quiz_dropdown = gr.Dropdown(choices=available, label="Select quiz")
        btn_start = gr.Button("▶ Start", variant="primary")

        timer_md = gr.Markdown(value="", visible=False)
        question_html = gr.HTML(visible=False)
        radio = gr.Radio(choices=[], label="", interactive=True, visible=False)

        with gr.Row():
            btn_prev = gr.Button("← Prev", visible=False)
            btn_next = gr.Button("Next →", visible=False)
            btn_submit_exam = gr.Button("Submit Exam", variant="stop", visible=False)

        report_html = gr.HTML(visible=False)
        btn_restart = gr.Button("🔄 Restart", variant="secondary", visible=False)

        # 9-output list used by most handlers
        _ALL = [
            state,
            question_html,
            radio,
            btn_prev,
            btn_next,
            btn_submit_exam,
            report_html,
            timer_md,
            btn_restart,
        ]

        btn_start.click(on_start, inputs=[quiz_dropdown, mode_radio], outputs=_ALL)

        # Practice: immediate feedback on selection; exam: auto-save + Submit visibility
        radio.change(on_answer, inputs=[state, radio], outputs=_ALL)

        # Practice navigation
        btn_next.click(on_next, inputs=[state], outputs=_ALL)

        # Exam navigation
        btn_prev.click(on_prev_exam, inputs=[state], outputs=_ALL)
        btn_submit_exam.click(on_submit_exam, inputs=[state], outputs=_ALL)

        # Countdown — fires every second
        gr.Timer(value=1).tick(on_timer_tick, inputs=[state], outputs=_ALL)

        btn_restart.click(on_restart, inputs=[state, mode_radio], outputs=_ALL)

    return demo


if __name__ == "__main__":
    build_ui().launch()
