"""Gradio interactive quiz app.

Two modes
---------
Practice  — answer each question and get immediate feedback + rationale before moving on.
Exam      — answer all questions within a time limit; full debrief with explanations at the end.

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
        "quiz_name": "",  # stored for restart
        "idx": 0,
        "answers": [],  # 1-based chosen index per question, None = unanswered
        "submitted": False,  # whether current question was submitted (practice only)
        "mode": "practice",  # "practice" | "exam"
        "start_time": None,  # time.time() when exam started, None when inactive
        "limit_seconds": 0,  # exam time limit in seconds
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


def _record_answer(state: dict, choice: str | None) -> None:
    """Parse the radio choice string and store the 1-based index in state."""
    if choice is None or not state.get("quiz"):
        return
    letter = choice.split(")")[0].strip() if ")" in choice else choice
    chosen_idx = _LETTER.index(letter) + 1 if letter in _LETTER else None
    idx = state["idx"]
    if idx < len(state["answers"]):
        state["answers"][idx] = chosen_idx


# ---------------------------------------------------------------------------
# HTML rendering (all LLM-generated text is escaped)
# ---------------------------------------------------------------------------


def _no_quiz_html() -> str:
    return "<p style='color:grey'>Select a quiz and click <strong>▶ Load</strong> to begin.</p>"


def _question_html(state: dict, with_feedback: bool = False) -> str:
    q = _current_q(state)
    if q is None:
        return _no_quiz_html()
    idx = state["idx"]
    total = _total(state)
    section = _html.escape(q.get("section", ""))
    text = _html.escape(q.get("question", ""))
    section_tag = (
        f"<span style='color:#7f8c8d;font-size:0.85em'>{section}</span><br>" if section else ""
    )
    out = (
        f"{section_tag}"
        f"<strong>Q{idx + 1} / {total}</strong><br>"
        f"<p style='font-size:1.1em'>{text}</p>"
    )
    if with_feedback:
        ans = state["answers"][idx] if idx < len(state["answers"]) else None
        correct = q["correct_answer"]
        is_correct = ans == correct
        correct_letter = _LETTER[correct - 1]
        verdict = (
            "✅ Correct!" if is_correct else f"❌ Incorrect — correct answer: {correct_letter})"
        )
        rationale = _html.escape(q.get("explanation", ""))
        out += f"<div style='margin-top:0.8em'><strong>{verdict}</strong>"
        if rationale:
            out += f"<p><em>Rationale:</em> {rationale}</p>"
        out += "</div>"
    return out


def _choices(state: dict) -> list[str]:
    q = _current_q(state)
    if not q:
        return []
    return [f"{_LETTER[i]}) {opt}" for i, opt in enumerate(q.get("options", []))]


def _debrief_html(state: dict) -> str:
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
        f"<h2 style='color:{color}'>{badge}</h2>",
        f"<p><strong>Score:</strong> {score}/{total} ({pct}%)</p>",
        f"<p><strong>Passing threshold:</strong> {passing}%</p>",
        "<hr><h3>Question Review</h3><ol>",
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
        snippet = _html.escape(q["question"][:100])
        lines.append(
            f"<li style='margin-bottom:0.8em'>{ok} <em>{snippet}…</em><br>"
            f"Your answer: <strong>{user_letter}</strong> | "
            f"Correct: <strong>{correct_letter}) {correct_text}</strong>"
        )
        if explanation:
            lines.append(f"<br><small><em>Rationale: {explanation}</em></small>")
        lines.append("</li>")
    lines.append("</ol>")
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"⏱ {seconds // 60:02d}:{seconds % 60:02d}"


# ---------------------------------------------------------------------------
# Event handlers
#
# Full output contract (10 values):
#   state, question_html, radio,
#   btn_submit, btn_next, btn_finish, btn_summary,
#   summary_html, timer_display, btn_restart
# ---------------------------------------------------------------------------


def _blank() -> tuple:
    """Return a fully-reset 10-output tuple (no quiz loaded)."""
    return (
        _initial_state(),
        _no_quiz_html(),
        gr.update(choices=[], value=None),
        gr.update(visible=False),  # btn_submit
        gr.update(visible=False),  # btn_next
        gr.update(visible=False),  # btn_finish
        gr.update(visible=False),  # btn_summary
        gr.update(value="", visible=False),  # summary_html
        gr.update(value="", visible=False),  # timer_display
        gr.update(visible=False),  # btn_restart
    )


def on_load_quiz(name: str, mode: str) -> tuple:
    """Load a quiz and initialise the correct mode layout."""
    if not name:
        return _blank()
    quiz = _load_quiz(name)
    if quiz is None:
        return _blank()

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
        _question_html(state),
        gr.update(choices=_choices(state), value=None, interactive=True),
        gr.update(visible=not is_exam),  # btn_submit: practice only
        gr.update(visible=is_exam),  # btn_next: exam immediately; practice after submit
        gr.update(visible=is_exam),  # btn_finish: exam only
        gr.update(visible=False),  # btn_summary
        gr.update(value="", visible=False),  # summary_html
        gr.update(value=_fmt_time(limit_seconds), visible=is_exam),  # timer: show start time
        gr.update(visible=False),  # btn_restart
    )


def on_timer_tick(state: dict) -> tuple:
    """Update the countdown display every second (exam mode only).

    Returns (timer_display update, state).  State is returned so the
    timer can mark itself inactive when time runs out.
    """
    if state.get("mode") != "exam" or state.get("start_time") is None:
        return gr.update(), state

    elapsed = time.time() - state["start_time"]
    remaining = state["limit_seconds"] - elapsed

    if remaining <= 0:
        state = {**state, "start_time": None}  # deactivate
        return gr.update(value="⏱ 00:00 — Time's up!", visible=True), state

    return gr.update(value=_fmt_time(remaining), visible=True), state


def on_submit(state: dict, choice: str | None) -> tuple:
    """Practice mode: record answer, show immediate feedback.

    6 outputs: state, question_html, radio, btn_submit, btn_next, btn_summary
    """
    if not state.get("quiz") or choice is None:
        return state, gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

    _record_answer(state, choice)
    state["submitted"] = True

    idx = state["idx"]
    is_last = idx >= _total(state) - 1
    return (
        state,
        _question_html(state, with_feedback=True),
        gr.update(interactive=False),  # lock radio
        gr.update(visible=False),  # hide Submit
        gr.update(visible=not is_last),  # Next → next question
        gr.update(visible=is_last),  # Show Results on last
    )


def on_next(state: dict, choice: str | None) -> tuple:
    """Advance to the next question.

    Practice: ignores choice (already recorded by on_submit), resets submit flow.
    Exam: records choice silently, shows next question; auto-finishes on last.
    """
    is_exam = state.get("mode") == "exam"

    if is_exam:
        _record_answer(state, choice)

    state["idx"] += 1
    state["submitted"] = False

    is_done = state["idx"] >= _total(state)

    # Exam: auto-finish when all questions answered
    if is_exam and is_done:
        state["start_time"] = None  # stop timer
        return (
            state,
            gr.update(value="", visible=False),
            gr.update(choices=[], visible=False),
            gr.update(visible=False),  # btn_submit
            gr.update(visible=False),  # btn_next
            gr.update(visible=False),  # btn_finish
            gr.update(visible=False),  # btn_summary
            gr.update(value=_debrief_html(state), visible=True),
            gr.update(value="", visible=False),  # hide timer
            gr.update(visible=True),  # btn_restart
        )

    return (
        state,
        _question_html(state),
        gr.update(choices=_choices(state), value=None, interactive=True),
        gr.update(visible=not is_exam),  # btn_submit: practice only
        gr.update(visible=is_exam),  # btn_next: always in exam
        gr.update(visible=is_exam),  # btn_finish: always in exam
        gr.update(visible=False),  # btn_summary
        gr.update(value="", visible=False),  # summary_html
        gr.update(),  # timer: leave as-is (still ticking)
        gr.update(visible=False),  # btn_restart
    )


def on_finish(state: dict, choice: str | None) -> tuple:
    """Exam mode: record current answer (if any) and show full debrief."""
    _record_answer(state, choice)
    state["start_time"] = None  # stop timer
    return (
        state,
        gr.update(value="", visible=False),
        gr.update(choices=[], visible=False),
        gr.update(visible=False),  # btn_submit
        gr.update(visible=False),  # btn_next
        gr.update(visible=False),  # btn_finish
        gr.update(visible=False),  # btn_summary
        gr.update(value=_debrief_html(state), visible=True),
        gr.update(value="", visible=False),  # hide timer
        gr.update(visible=True),  # btn_restart
    )


def on_show_results(state: dict) -> tuple:
    """Practice mode: show debrief after the last question (2 outputs)."""
    return gr.update(value=_debrief_html(state), visible=True), gr.update(visible=True)


def on_restart(state: dict, mode: str) -> tuple:
    """Restart the current quiz from scratch with the same mode."""
    return on_load_quiz(state.get("quiz_name", ""), mode)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def build_ui() -> gr.Blocks:
    available = _list_quizzes()

    with gr.Blocks(title="NanoClaw Quiz") as demo:
        gr.Markdown("# NanoClaw Interactive Quiz")

        state = gr.State(_initial_state())

        mode_radio = gr.Radio(
            choices=["Practice", "Exam"],
            value="Practice",
            label="Mode",
            info=(
                "Practice: submit each answer to see immediate feedback. "
                "Exam: answer all questions within the time limit, "
                "then receive a full debrief."
            ),
        )

        with gr.Row():
            quiz_dropdown = gr.Dropdown(choices=available, label="Select quiz", scale=3)
            btn_load = gr.Button("▶ Load", variant="primary", scale=1)

        timer_display = gr.Markdown(value="", visible=False)
        question_html = gr.HTML(_no_quiz_html())
        radio = gr.Radio(choices=[], label="Your answer", interactive=True)

        with gr.Row():
            btn_submit = gr.Button("Submit", variant="primary", visible=False)
            btn_next = gr.Button("Next →", visible=False)
            btn_finish = gr.Button("⏹ Finish Exam", variant="stop", visible=False)
            btn_summary = gr.Button("Show Results", variant="secondary", visible=False)

        summary_html = gr.HTML(visible=False)
        btn_restart = gr.Button("🔄 Restart Quiz", variant="secondary", visible=False)

        # Full 10-output list shared by load / next / finish / restart
        _all = [
            state,
            question_html,
            radio,
            btn_submit,
            btn_next,
            btn_finish,
            btn_summary,
            summary_html,
            timer_display,
            btn_restart,
        ]

        btn_load.click(on_load_quiz, inputs=[quiz_dropdown, mode_radio], outputs=_all)
        quiz_dropdown.change(on_load_quiz, inputs=[quiz_dropdown, mode_radio], outputs=_all)

        # Countdown ticker — fires every second, updates display + deactivates on 00:00
        gr.Timer(value=1).tick(
            on_timer_tick,
            inputs=[state],
            outputs=[timer_display, state],
        )

        # Practice: Submit → feedback; Next → advance
        btn_submit.click(
            on_submit,
            inputs=[state, radio],
            outputs=[state, question_html, radio, btn_submit, btn_next, btn_summary],
        )
        btn_next.click(on_next, inputs=[state, radio], outputs=_all)

        # Exam: Finish records last answer and shows debrief
        btn_finish.click(on_finish, inputs=[state, radio], outputs=_all)

        # Practice: Show Results after last question (2 outputs)
        btn_summary.click(
            on_show_results,
            inputs=[state],
            outputs=[summary_html, btn_restart],
        )

        # Restart: reload same quiz + mode from scratch
        btn_restart.click(on_restart, inputs=[state, mode_radio], outputs=_all)

    return demo


if __name__ == "__main__":
    build_ui().launch()
