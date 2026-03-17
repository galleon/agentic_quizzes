"""Gradio interactive quiz app.

Launch with:
    uv run --group app python app.py

Or deploy to HuggingFace Spaces by pointing at pre-generated Gradio JSON files
in outputs/quizzes/*.gradio.json.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import gradio as gr

from src.common.config import get_settings, project_root

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LETTER = "ABCD"


def _quizzes_dir() -> Path:
    cfg = get_settings()
    return project_root() / cfg.quiz.quizzes_dir


def _list_quizzes() -> list[str]:
    """Return display names (stems) of available Gradio quiz JSON files."""
    d = _quizzes_dir()
    if not d.exists():
        return []
    return sorted(p.stem.replace(".gradio", "") for p in d.glob("*.gradio.json"))


def _load_quiz(name: str) -> dict | None:
    path = _quizzes_dir() / f"{name}.gradio.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# State helpers — pure functions operating on the session state dict
# ---------------------------------------------------------------------------


def _initial_state() -> dict:
    return {
        "quiz": None,  # full Gradio JSON dict
        "idx": 0,  # current question index (0-based)
        "answers": [],  # user's answer indices (1-based, None if not answered)
        "submitted": False,  # whether current question has been submitted
    }


def _current_question(state: dict) -> dict | None:
    q = state.get("quiz")
    if q is None:
        return None
    questions = q.get("questions", [])
    idx = state.get("idx", 0)
    return questions[idx] if idx < len(questions) else None


def _total(state: dict) -> int:
    q = state.get("quiz")
    return len(q.get("questions", [])) if q else 0


def _score(state: dict) -> int:
    q = state.get("quiz")
    if not q:
        return 0
    correct = 0
    for i, ans in enumerate(state["answers"]):
        questions = q["questions"]
        if i < len(questions) and ans == questions[i]["correct_answer"]:
            correct += 1
    return correct


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def on_load_quiz(name: str) -> tuple:
    """Load a quiz by name and return initial UI state (7 outputs)."""
    blank = (
        _initial_state(),
        _no_quiz_html(),
        gr.update(choices=[], value=None),
        gr.update(visible=False),  # btn_submit
        gr.update(visible=False),  # btn_next
        gr.update(visible=False),  # btn_summary
        gr.update(value="", visible=False),  # summary_html
    )
    if not name:
        return blank

    quiz = _load_quiz(name)
    if quiz is None:
        return blank

    state = _initial_state()
    state["quiz"] = quiz
    state["answers"] = [None] * len(quiz.get("questions", []))

    question_html, choices, submit_vis, next_vis, summary_vis = _render_question(state)
    return (
        state,
        question_html,
        gr.update(choices=choices, value=None, interactive=True),
        submit_vis,
        next_vis,
        summary_vis,
        gr.update(value="", visible=False),  # reset summary panel
    )


def on_submit(state: dict, choice: str | None) -> tuple:
    """Record the user's answer and reveal rationale (6 outputs)."""
    if state.get("quiz") is None or choice is None:
        return (
            state,
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
        )

    # Parse chosen letter back to 1-based index
    letter = choice.split(")")[0].strip() if ")" in choice else choice
    chosen_idx = _LETTER.index(letter) + 1 if letter in _LETTER else None

    idx = state["idx"]
    state["answers"][idx] = chosen_idx
    state["submitted"] = True

    question = _current_question(state)
    correct = question["correct_answer"]
    is_correct = chosen_idx == correct
    explanation = question.get("explanation", "")

    # Build feedback HTML — escape LLM-generated text before embedding
    correct_letter = _LETTER[correct - 1]
    verdict = "✅ Correct!" if is_correct else f"❌ Incorrect. Correct answer: {correct_letter})"
    feedback_parts = [f"<div style='margin-top:1em'><strong>{verdict}</strong>"]
    if explanation:
        feedback_parts.append(f"<p><em>Rationale:</em> {html.escape(explanation)}</p>")
    feedback_parts.append("</div>")
    feedback_html = "".join(feedback_parts)

    question_html, choices, _, _, _ = _render_question(state)
    full_html = question_html + feedback_html

    total = _total(state)
    is_last = idx >= total - 1

    return (
        state,
        full_html,
        gr.update(choices=choices, interactive=False),  # lock radio
        gr.update(visible=False),  # hide Submit
        gr.update(visible=not is_last),  # Next (not on last)
        gr.update(visible=is_last),  # Show summary button on last
    )


def on_next(state: dict) -> tuple:
    """Advance to the next question (7 outputs)."""
    state["idx"] += 1
    state["submitted"] = False
    question_html, choices, submit_vis, next_vis, summary_vis = _render_question(state)
    return (
        state,
        question_html,
        gr.update(choices=choices, value=None, interactive=True),
        submit_vis,
        next_vis,
        summary_vis,
        gr.update(visible=False),  # keep summary panel hidden between questions
    )


def on_summary(state: dict) -> gr.update:
    """Build the final score summary and make the panel visible."""
    quiz = state.get("quiz")
    if not quiz:
        return gr.update(value="", visible=False)
    exam = quiz.get("exam_info", {})
    total = _total(state)
    score = _score(state)
    passing = exam.get("passing_score", 70)
    pct = round(score / total * 100) if total else 0
    passed = pct >= passing
    badge = "🎉 PASSED" if passed else "❌ FAILED"
    color = "#2ecc71" if passed else "#e74c3c"

    lines = [
        f"<h2 style='color:{color}'>{badge}</h2>",
        f"<p><strong>Score:</strong> {score}/{total} ({pct}%)</p>",
        f"<p><strong>Passing threshold:</strong> {passing}%</p>",
        "<hr><h3>Review</h3><ol>",
    ]
    for i, q in enumerate(quiz["questions"]):
        user_ans = state["answers"][i]
        correct = q["correct_answer"]
        options = q.get("options", [])
        user_letter = _LETTER[user_ans - 1] if user_ans and 1 <= user_ans <= 4 else "–"
        correct_letter = _LETTER[correct - 1]
        ok = "✅" if user_ans == correct else "❌"
        correct_text = html.escape(options[correct - 1]) if 0 < correct <= len(options) else ""
        question_snippet = html.escape(q["question"][:80])
        lines.append(
            f"<li>{ok} <em>{question_snippet}…</em><br>"
            f"Your answer: {user_letter} | Correct: {correct_letter}) {correct_text}</li>"
        )
    lines.append("</ol>")
    return gr.update(value="\n".join(lines), visible=True)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _no_quiz_html() -> str:
    return "<p style='color:grey'>Select a quiz and click <strong>Load</strong> to begin.</p>"


def _render_question(state: dict) -> tuple:
    """Return (question_html, radio_choices, submit_vis, next_vis, summary_vis)."""
    question = _current_question(state)
    if question is None:
        return (
            _no_quiz_html(),
            [],
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    idx = state["idx"]
    total = _total(state)
    options = question.get("options", [])
    choices = [f"{_LETTER[i]}) {opt}" for i, opt in enumerate(options)]

    section = html.escape(question.get("section", ""))
    section_tag = (
        f"<span style='color:grey;font-size:0.85em'>{section}</span><br>" if section else ""
    )
    question_text = html.escape(question.get("question", ""))
    question_html = (
        f"{section_tag}"
        f"<strong>Q{idx + 1} / {total}</strong><br>"
        f"<p style='font-size:1.1em'>{question_text}</p>"
    )
    submitted = state.get("submitted", False)
    return (
        question_html,
        choices,
        gr.update(visible=not submitted),  # Submit
        gr.update(visible=False),  # Next (shown after submit by on_submit)
        gr.update(visible=False),  # Summary button
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def build_ui() -> gr.Blocks:
    available = _list_quizzes()

    with gr.Blocks(title="NanoClaw Quiz") as demo:
        gr.Markdown("# NanoClaw Interactive Quiz")

        state = gr.State(_initial_state())

        with gr.Row():
            quiz_dropdown = gr.Dropdown(
                choices=available,
                label="Select quiz",
                scale=3,
            )
            btn_load = gr.Button("▶ Load", variant="primary", scale=1)

        question_html = gr.HTML(_no_quiz_html())
        radio = gr.Radio(choices=[], label="Your answer", interactive=True)

        with gr.Row():
            btn_submit = gr.Button("Submit", variant="primary", visible=False)
            btn_next = gr.Button("Next →", visible=False)
            btn_summary = gr.Button("Show results", variant="secondary", visible=False)

        summary_html = gr.HTML(visible=False)

        # Shared output list for events that reset the full quiz view (7 outputs)
        _quiz_view_outputs = [
            state,
            question_html,
            radio,
            btn_submit,
            btn_next,
            btn_summary,
            summary_html,
        ]

        btn_load.click(
            on_load_quiz,
            inputs=[quiz_dropdown],
            outputs=_quiz_view_outputs,
        )

        # Also trigger on dropdown change for keyboard/programmatic use
        quiz_dropdown.change(
            on_load_quiz,
            inputs=[quiz_dropdown],
            outputs=_quiz_view_outputs,
        )

        btn_submit.click(
            on_submit,
            inputs=[state, radio],
            outputs=[state, question_html, radio, btn_submit, btn_next, btn_summary],
        )

        btn_next.click(
            on_next,
            inputs=[state],
            outputs=_quiz_view_outputs,
        )

        btn_summary.click(
            on_summary,
            inputs=[state],
            outputs=[summary_html],
        )

    return demo


if __name__ == "__main__":
    build_ui().launch()
