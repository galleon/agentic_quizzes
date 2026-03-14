"""Export validated quiz to Markdown, JSON, and CSV formats."""

from __future__ import annotations

import argparse
import csv

from src.common.config import get_settings, project_root
from src.common.models import Quiz


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
        if item.question_type == "mcq" and item.answer_index is not None:
            choices = item.choices or []
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Export quiz to MD/JSON/CSV.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--formats", nargs="+", default=["md", "json", "csv"])
    args = parser.parse_args()

    cfg = get_settings()
    root = project_root()
    slug = args.topic.lower().replace(" ", "_")[:40]
    quiz_path = root / cfg.quiz.quizzes_dir / f"{slug}.json"

    if not quiz_path.exists():
        raise FileNotFoundError(f"Quiz not found: {quiz_path}")

    quiz = Quiz.model_validate_json(quiz_path.read_text())

    quizzes_dir = root / cfg.quiz.quizzes_dir
    keys_dir = root / cfg.quiz.answer_keys_dir
    rationales_dir = root / cfg.quiz.rationales_dir
    for d in (quizzes_dir, keys_dir, rationales_dir):
        d.mkdir(parents=True, exist_ok=True)

    if "md" in args.formats:
        md = to_markdown(quiz)
        out = quizzes_dir / f"{slug}.md"
        out.write_text(md)
        key_out = keys_dir / f"{slug}_key.md"
        key_out.write_text(to_answer_key(quiz))
        print(f"Markdown: {out}")
        print(f"Answer key: {key_out}")

    if "csv" in args.formats:
        rows = to_csv_rows(quiz)
        out = quizzes_dir / f"{slug}.csv"
        if rows:
            with out.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            print(f"CSV: {out}")

    if "json" in args.formats:
        # Already exists; optionally export a clean version without embeddings
        print(f"JSON: {quiz_path} (already written by generate/validate)")

    # Write rationales
    rationale_lines = []
    for n, item in enumerate(quiz.items, 1):
        if item.confidence_flag != "rejected":
            chunks_str = ", ".join(item.supporting_chunk_ids)
            rationale_lines.append(f"{n}. {item.rationale}  (chunks: {chunks_str})\n")
    (rationales_dir / f"{slug}_rationales.md").write_text("".join(rationale_lines))
    print(f"Rationales: {rationales_dir / f'{slug}_rationales.md'}")


if __name__ == "__main__":
    main()
