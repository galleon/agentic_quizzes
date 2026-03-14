"""Validate quiz grounding: verify each answer is supported by retrieved chunks."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from src.common.config import get_settings, project_root
from src.common.models import Quiz, QuizItem
from src.common.ollama_client import generate, parse_json_response
from src.rag.retrieve import retrieve

SYSTEM_PROMPT_PATH = (
    Path(__file__).parent.parent.parent / "nanoclaw" / "prompts" / "validate_system.md"
)


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text()
    return (
        "You are a quiz validator. Output valid JSON only. "
        "Verify each answer against provided chunks."
    )


def _build_validate_prompt(item: QuizItem, chunks: list[dict]) -> str:
    chunk_texts = "\n\n---\n\n".join(f"[{c['chunk_id']}] {c['text']}" for c in chunks)
    answer = item.answer or (
        item.choices[item.answer_index] if item.choices and item.answer_index is not None else "N/A"
    )
    return f"""Question: {item.question}
Answer: {answer}
Rationale: {item.rationale}

Source chunks:
{chunk_texts}

Return a single JSON object with fields:
  verdict: "supported" | "partial" | "hallucinated"
  reason: one sentence

Output only the JSON object."""


def validate_quiz(quiz: Quiz) -> Quiz:
    cfg = get_settings()
    system = _load_system_prompt()
    validated_items = []

    source_filter = quiz.source_scope if quiz.source_scope else None
    for item in quiz.items:
        # Re-retrieve within the same scope used during generation
        chunks = retrieve(
            item.question,
            top_k=cfg.quiz.top_k_chunks,
            source_filter=source_filter,
        )
        prompt = _build_validate_prompt(item, chunks)
        raw = generate(prompt, system=system)

        try:
            result = parse_json_response(raw)
            verdict = result.get("verdict", "unverified")
        except (ValueError, AttributeError):
            verdict = "unverified"

        item.grounding_verdict = verdict
        if verdict == "hallucinated":
            item.confidence_flag = "rejected"
        elif verdict in ("partial", "unverified"):
            # unverified means validation failed (parse error / unexpected response);
            # treat as low-confidence rather than silently passing through as "ok"
            item.confidence_flag = "low"
        else:
            item.confidence_flag = "ok"

        validated_items.append(item)
        icons = {"supported": "✓", "partial": "~", "hallucinated": "✗", "unverified": "?"}
        status = icons.get(verdict, "?")
        print(f"  [{status}] {verdict}: {item.question[:70]}")

    quiz.items = validated_items
    return quiz


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate quiz grounding.")
    parser.add_argument(
        "--topic",
        required=True,
        help="Topic string used during generation (e.g. 'GPU monitoring with DCGM')",
    )
    args = parser.parse_args()

    cfg = get_settings()
    root = project_root()
    slug = re.sub(r"[^\w-]", "", args.topic.lower().replace(" ", "_"))[:40]
    quiz_path = root / cfg.quiz.quizzes_dir / f"{slug}.json"

    if not quiz_path.exists():
        raise FileNotFoundError(f"Quiz not found: {quiz_path}")

    quiz = Quiz.model_validate_json(quiz_path.read_text())
    print(f"Validating {len(quiz.items)} questions for topic: {quiz.topic!r}")
    quiz = validate_quiz(quiz)

    # Overwrite with verdicts
    quiz_path.write_text(quiz.model_dump_json(indent=2))
    rejected = sum(1 for i in quiz.items if i.confidence_flag == "rejected")
    print(f"Validation done. {rejected}/{len(quiz.items)} questions rejected.")


if __name__ == "__main__":
    main()
