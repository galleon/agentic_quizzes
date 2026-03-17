"""Export quiz to Markdown, JSON, CSV, and Gradio formats."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date

from src.common.config import ExamInfoConfig, get_settings, project_root
from src.common.models import Quiz
from src.common.slug import make_slug


def _choice_letter(idx: int) -> str:
    return "ABCD"[idx] if 0 <= idx <= 3 else str(idx)


def to_markdown(quiz: Quiz) -> str:
    lines = [f"# Quiz: {quiz.topic}\n"]
    lines.append(f"**Difficulty**: {quiz.difficulty}  ")
    lines.append(f"**Generated**: {quiz.generated_at}  ")
    lines.append(f"**Model**: {quiz.model}\n\n")

    accepted = [i for i in quiz.items if i.confidence_flag != "rejected"]
    lines.append(f"**Questions**: {len(accepted)} (of {len(quiz.items)} generated)\n\n---\n")

    for n, item in enumerate(accepted, 1):
        lines.append(f"\n## Q{n}. {item.question}\n")
        lines.append(f"*Type*: {item.question_type} | *Difficulty*: {item.difficulty}\n")
        if item.question_type == "mcq" and item.choices:
            for i, choice in enumerate(item.choices):
                marker = "**" if i == item.answer_index else ""
                lines.append(f"- {_choice_letter(i)}) {marker}{choice}{marker}\n")
        elif item.answer:
            lines.append(f"**Answer**: {item.answer}\n")
        if item.rationale:
            lines.append(f"\n> *Rationale*: {item.rationale}\n")
        if item.supporting_chunk_ids:
            lines.append(f"> *Chunks*: {', '.join(item.supporting_chunk_ids)}\n")

    return "".join(lines)


def to_answer_key(quiz: Quiz) -> str:
    lines = [f"# Answer Key: {quiz.topic}\n\n"]
    accepted = [i for i in quiz.items if i.confidence_flag != "rejected"]
    for n, item in enumerate(accepted, 1):
        choices = item.choices or []
        if (
            item.question_type == "mcq"
            and item.answer_index is not None
            and 0 <= item.answer_index < len(choices)
        ):
            answer = f"{_choice_letter(item.answer_index)}) {choices[item.answer_index]}"
        else:
            answer = item.answer or "N/A"
        lines.append(f"{n}. {answer}\n")
    return "".join(lines)


def to_csv_rows(quiz: Quiz) -> list[dict]:
    rows = []
    for item in quiz.items:
        if item.confidence_flag == "rejected":
            continue
        rows.append(
            {
                "question_id": item.question_id,
                "question_type": item.question_type,
                "difficulty": item.difficulty,
                "question": item.question,
                "choice_a": (item.choices or ["", "", "", ""])[0],
                "choice_b": (item.choices or [])[1] if len(item.choices or []) > 1 else "",
                "choice_c": (item.choices or [])[2] if len(item.choices or []) > 2 else "",
                "choice_d": (item.choices or [])[3] if len(item.choices or []) > 3 else "",
                "answer_index": item.answer_index if item.answer_index is not None else "",
                "answer": item.answer or "",
                "rationale": item.rationale,
                "supporting_chunk_ids": "|".join(item.supporting_chunk_ids),
                "source_files": "|".join(item.source_files),
                "grounding_verdict": item.grounding_verdict,
            }
        )
    return rows


def to_gradio(quiz: Quiz, exam_info_overrides: ExamInfoConfig | None = None) -> dict:
    """Serialise *quiz* to the Gradio-compatible schema used by the HuggingFace Space.

    Only MCQ items that have not been rejected are included.  ``correct_answer``
    is 1-indexed (the Space convention) while ``answer_index`` is 0-indexed.

    ``exam_info_overrides`` takes precedence over whatever is in settings.yaml;
    pass ``None`` to use the project defaults.
    """
    cfg_exam = exam_info_overrides or get_settings().exam_info
    accepted_mcq = [
        i
        for i in quiz.items
        if i.question_type == "mcq"
        and i.confidence_flag != "rejected"
        and i.choices
        and i.answer_index is not None
        and 0 <= i.answer_index < len(i.choices)
    ]
    questions = []
    for n, item in enumerate(accepted_mcq, 1):
        questions.append(
            {
                "id": n,
                "section": quiz.topic,
                "question": item.question,
                "options": item.choices,
                "correct_answer": item.answer_index + 1,  # 1-indexed
                "explanation": item.rationale,
            }
        )
    last_updated = date.today().strftime("%B %Y")
    return {
        "exam_info": {
            "title": cfg_exam.title,
            "certifications": cfg_exam.certifications,
            "total_questions": len(questions),
            "time_limit_minutes": cfg_exam.time_limit_minutes,
            "passing_score": cfg_exam.passing_score,
            "last_updated": last_updated,
        },
        "questions": questions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export quiz to MD/JSON/CSV/Gradio.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--formats", nargs="+", default=["md", "json", "csv"])
    args = parser.parse_args()

    cfg = get_settings()
    root = project_root()
    slug = make_slug(args.topic)
    quiz_path = root / cfg.quiz.quizzes_dir / f"{slug}.json"

    if not quiz_path.exists():
        raise FileNotFoundError(f"Quiz not found: {quiz_path}")

    quiz = Quiz.model_validate_json(quiz_path.read_text(encoding="utf-8"))

    unverified = sum(1 for i in quiz.items if i.grounding_verdict == "unverified")
    if unverified:
        print(
            f"Warning: {unverified} item(s) have grounding_verdict='unverified'."
            " Run validate first for a fully grounded export.",
            file=sys.stderr,
        )

    quizzes_dir = root / cfg.quiz.quizzes_dir
    keys_dir = root / cfg.quiz.answer_keys_dir
    rationales_dir = root / cfg.quiz.rationales_dir
    for d in (quizzes_dir, keys_dir, rationales_dir):
        d.mkdir(parents=True, exist_ok=True)

    if "md" in args.formats:
        md = to_markdown(quiz)
        out = quizzes_dir / f"{slug}.md"
        out.write_text(md, encoding="utf-8")
        key_out = keys_dir / f"{slug}_key.md"
        key_out.write_text(to_answer_key(quiz), encoding="utf-8")
        print(f"Markdown: {out}")
        print(f"Answer key: {key_out}")

    if "csv" in args.formats:
        rows = to_csv_rows(quiz)
        out = quizzes_dir / f"{slug}.csv"
        # Always write the file (with headers) so downstream tooling doesn't
        # encounter a missing file when all questions happen to be rejected.
        fieldnames = (
            list(rows[0].keys())
            if rows
            else [
                "question_id",
                "question_type",
                "difficulty",
                "question",
                "choice_a",
                "choice_b",
                "choice_c",
                "choice_d",
                "answer_index",
                "answer",
                "rationale",
                "supporting_chunk_ids",
                "source_files",
                "grounding_verdict",
            ]
        )
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV: {out}{' (0 rows — all questions rejected)' if not rows else ''}")

    if "json" in args.formats:
        # Already exists; optionally export a clean version without embeddings
        print(f"JSON: {quiz_path} (already written by generate/validate)")

    if "gradio" in args.formats:
        gradio_data = to_gradio(quiz)
        out = quizzes_dir / f"{slug}.gradio.json"
        out.write_text(json.dumps(gradio_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Gradio: {out}")

    # Write rationales (only accepted items, numbered to match the exported quiz)
    rationale_lines = []
    for n, item in enumerate((i for i in quiz.items if i.confidence_flag != "rejected"), 1):
        chunks_str = ", ".join(item.supporting_chunk_ids)
        rationale_lines.append(f"{n}. {item.rationale}  (chunks: {chunks_str})\n")
    (rationales_dir / f"{slug}_rationales.md").write_text(
        "".join(rationale_lines), encoding="utf-8"
    )
    print(f"Rationales: {rationales_dir / f'{slug}_rationales.md'}")


if __name__ == "__main__":
    main()
