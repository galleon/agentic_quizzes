"""Gradio interactive quiz app.

Two modes
---------
Practice  — answer each question and get immediate feedback + rationale before moving on.
Exam      — navigate freely between questions, submit when ready (or when time runs out).

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
        "submitted": False,  # True after on_submit in practice (locks radio)
        "mode": "practice",  # "practice" | "exam"
        "start_time": None,  # time.time() when exam started; None = inactive
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


def _record_answer(state: dict, choice: str | None) -> None:
    """Store the 1-based answer index for the current question."""
    if choice is None or not state.get("quiz"):
        return
    letter = choice.split(")")[0].strip() if ")" in choice else choice
    chosen_idx = _LETTER.index(letter) + 1 if letter in _LETTER else None
    idx = state["idx"]
    if idx < len(state["answers"]):
        state["answers"][idx] = chosen_idx


def _stored_choice(state: dict) -> str | None:
    """Return the radio choice string for the already-recorded answer, or None."""
    idx = state["idx"]
    answers = state.get("answers", [])
    if idx >= len(answers) or answers[idx] is None:
        return None
    ans = answers[idx]  # 1-based
    choices = _choices_for(state)
    return choices[ans - 1] if 1 <= ans <= len(choices) else None


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


def _choices_for(state: dict) -> list[str]:
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
    s = max(0, int(seconds))
    return f"⏱ {s // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------------------
# Output helpers
#
# Full contract — 11 outputs (_ALL):
#   state, question_html, radio,
#   btn_submit, btn_prev, btn_next, btn_finish, btn_summary,
#   summary_html, timer_display, btn_restart
# ---------------------------------------------------------------------------


def _blank() -> tuple:
    """Fully-reset 11-output tuple for when no quiz is loaded."""
    return (
        _initial_state(),
        _no_quiz_html(),
        gr.update(choices=[], value=None),
        gr.update(visible=False),  # btn_submit
        gr.update(visible=False),  # btn_prev
        gr.update(visible=False),  # btn_next
        gr.update(visible=False),  # btn_finish
        gr.update(visible=False),  # btn_summary
        gr.update(value="", visible=False),  # summary_html
        gr.update(value="", visible=False),  # timer_display
        gr.update(visible=False),  # btn_restart
    )


def _exam_nav(state: dict) -> tuple:
    """Return the 11-output tuple for a normal exam question view."""
    idx = state["idx"]
    total = _total(state)
    at_first = idx == 0
    at_last = idx >= total - 1
    return (
        state,
        _question_html(state),
        gr.update(
            choices=_choices_for(state),
            value=_stored_choice(state),  # restore previously selected answer
            interactive=True,
        ),
        gr.update(visible=False),  # btn_submit
        gr.update(visible=not at_first),  # btn_prev
        gr.update(visible=not at_last),  # btn_next
        gr.update(visible=True),  # btn_finish (always)
        gr.update(visible=False),  # btn_summary
        gr.update(value="", visible=False),  # summary_html
        gr.update(),  # timer_display: keep as-is
        gr.update(visible=False),  # btn_restart
    )


def _debrief_outputs(state: dict) -> tuple:
    """Return the 11-output tuple showing the debrief panel."""
    state = {**state, "start_time": None}  # stop timer
    return (
        state,
        gr.update(value="", visible=False),
        gr.update(choices=[], visible=False),
        gr.update(visible=False),  # btn_submit
        gr.update(visible=False),  # btn_prev
        gr.update(visible=False),  # btn_next
        gr.update(visible=False),  # btn_finish
        gr.update(visible=False),  # btn_summary
        gr.update(value=_debrief_html(state), visible=True),
        gr.update(value="", visible=False),  # hide timer
        gr.update(visible=True),  # btn_restart
    )


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def on_load_quiz(name: str, mode: str) -> tuple:
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
        # Exam: show first question with nav buttons + timer
        total = _total(state)
        return (
            state,
            _question_html(state),
            gr.update(choices=_choices_for(state), value=None, interactive=True),
            gr.update(visible=False),  # btn_submit
            gr.update(visible=False),  # btn_prev (at Q1)
            gr.update(visible=total > 1),  # btn_next
            gr.update(visible=True),  # btn_finish
            gr.update(visible=False),  # btn_summary
            gr.update(value="", visible=False),  # summary_html
            gr.update(value=_fmt_time(limit_seconds), visible=True),
            gr.update(visible=False),  # btn_restart
        )
    else:
        # Practice: show first question with Submit
        return (
            state,
            _question_html(state),
            gr.update(choices=_choices_for(state), value=None, interactive=True),
            gr.update(visible=True),  # btn_submit
            gr.update(visible=False),  # btn_prev
            gr.update(visible=False),  # btn_next (appears after submit)
            gr.update(visible=False),  # btn_finish
            gr.update(visible=False),  # btn_summary
            gr.update(value="", visible=False),  # summary_html
            gr.update(value="", visible=False),  # no timer
            gr.update(visible=False),  # btn_restart
        )


def on_radio_change(state: dict, choice: str | None) -> dict:
    """Exam mode only: auto-save answer on radio selection (no server round-trip needed
    for practice — Submit handles that)."""
    if state.get("mode") == "exam":
        _record_answer(state, choice)
    return state


def on_submit(state: dict, choice: str | None) -> tuple:
    """Practice mode: record answer and show immediate feedback.

    6 outputs: state, question_html, radio, btn_submit, btn_next, btn_summary
    """
    if not state.get("quiz") or choice is None:
        return state, gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

    # Create a fresh state dict to avoid Gradio identity-check skipping the update
    state = {**state}
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


def on_next(state: dict) -> tuple:
    """Practice mode: advance to the next question after feedback."""
    # Fresh dict so Gradio always detects the state change
    state = {**state, "idx": state["idx"] + 1, "submitted": False}
    return (
        state,
        _question_html(state),
        gr.update(choices=_choices_for(state), value=None, interactive=True),
        gr.update(visible=True),  # btn_submit
        gr.update(visible=False),  # btn_prev
        gr.update(visible=False),  # btn_next (hidden until next submit)
        gr.update(visible=False),  # btn_finish
        gr.update(visible=False),  # btn_summary
        gr.update(value="", visible=False),  # summary_html
        gr.update(visible=False),  # timer_display
        gr.update(visible=False),  # btn_restart
    )


def on_prev_exam(state: dict) -> tuple:
    """Exam mode: go to the previous question."""
    if state["idx"] == 0:
        return _exam_nav(state)
    state = {**state, "idx": state["idx"] - 1}
    return _exam_nav(state)


def on_next_exam(state: dict) -> tuple:
    """Exam mode: go to the next question."""
    total = _total(state)
    if state["idx"] >= total - 1:
        return _exam_nav(state)
    state = {**state, "idx": state["idx"] + 1}
    return _exam_nav(state)


def on_finish_exam(state: dict) -> tuple:
    """Exam mode: submit all answers and show debrief."""
    return _debrief_outputs(state)


def on_show_results(state: dict) -> tuple:
    """Practice mode: show debrief after the last question. 2 outputs."""
    return gr.update(value=_debrief_html(state), visible=True), gr.update(visible=True)


def on_restart(state: dict, mode: str) -> tuple:
    """Restart the current quiz from scratch."""
    return on_load_quiz(state.get("quiz_name", ""), mode)


def on_timer_tick(state: dict) -> tuple:
    """Update countdown every second; auto-submit when time is up.

    11 outputs matching _ALL so the debrief can be shown directly from
    the timer without any extra user interaction.
    """
    if state.get("mode") != "exam" or state.get("start_time") is None:
        # No active exam — emit no-ops for everything except timer_display
        return (gr.update(),) * 9 + (gr.update(visible=False),) + (gr.update(),)

    elapsed = time.time() - state["start_time"]
    remaining = state["limit_seconds"] - elapsed

    if remaining <= 0:
        return _debrief_outputs(state)

    # Normal tick: only update the timer display
    noop = gr.update()
    return (noop,) * 9 + (gr.update(value=_fmt_time(remaining), visible=True),) + (noop,)


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
                "Exam: navigate freely, submit when ready (timer auto-submits on expiry)."
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
            btn_prev = gr.Button("← Prev", visible=False)
            btn_next = gr.Button("Next →", visible=False)
            btn_finish = gr.Button("Submit Exam", variant="stop", visible=False)
            btn_summary = gr.Button("Show Results", variant="secondary", visible=False)

        summary_html = gr.HTML(visible=False)
        btn_restart = gr.Button("🔄 Restart Quiz", variant="secondary", visible=False)

        # 11-output contract shared by load / exam nav / finish / restart / timer
        _ALL = [
            state,
            question_html,
            radio,
            btn_submit,
            btn_prev,
            btn_next,
            btn_finish,
            btn_summary,
            summary_html,
            timer_display,
            btn_restart,
        ]

        # --- Load ---
        btn_load.click(on_load_quiz, inputs=[quiz_dropdown, mode_radio], outputs=_ALL)
        quiz_dropdown.change(on_load_quiz, inputs=[quiz_dropdown, mode_radio], outputs=_ALL)

        # --- Exam mode: auto-save answer on selection ---
        radio.change(on_radio_change, inputs=[state, radio], outputs=[state])

        # --- Practice mode ---
        btn_submit.click(
            on_submit,
            inputs=[state, radio],
            outputs=[state, question_html, radio, btn_submit, btn_next, btn_summary],
        )
        btn_next.click(on_next, inputs=[state], outputs=_ALL)
        btn_summary.click(on_show_results, inputs=[state], outputs=[summary_html, btn_restart])

        # --- Exam mode ---
        btn_prev.click(on_prev_exam, inputs=[state], outputs=_ALL)
        btn_finish.click(on_finish_exam, inputs=[state], outputs=_ALL)

        # --- Countdown (fires every second; auto-submits when time's up) ---
        gr.Timer(value=1).tick(on_timer_tick, inputs=[state], outputs=_ALL)

        # --- Restart ---
        btn_restart.click(on_restart, inputs=[state, mode_radio], outputs=_ALL)

    return demo


if __name__ == "__main__":
    build_ui().launch()
