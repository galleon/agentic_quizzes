"""Generate quiz questions from retrieved chunks using the local LLM."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

from src.common.config import get_settings, project_root
from src.common.models import Quiz, QuizItem
from src.common.ollama_client import generate, parse_json_response
from src.rag.retrieve import retrieve

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent.parent / "nanoclaw" / "prompts" / "quiz_system.md"


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You are a quiz generator. Output valid JSON only. "
        "Do not output chain-of-thought. Only use the provided source chunks."
    )


def _build_prompt(
    topic: str,
    chunks: list[dict],
    num_questions: int,
    difficulty: str,
    question_types: list[str],
) -> str:
    chunk_texts = "\n\n---\n\n".join(
        f"[chunk_id: {c['chunk_id']}]"
        f" (source: {c['source_file']}, {c['page_or_section']})\n{c['text']}"
        for c in chunks
    )
    types_str = ", ".join(question_types)
    return f"""Topic: {topic}
Difficulty: {difficulty}
Number of questions: {num_questions}
Question types: {types_str}

Source chunks:
{chunk_texts}

Generate exactly {num_questions} quiz questions as a JSON array.
Each element must have these fields:
  question_type (one of: {types_str})
  difficulty
  question
  choices (array of 4 strings, MCQ only; omit for other types)
  answer_index (0-3, MCQ only; omit for other types)
  answer (string, for short_answer and true_false; omit for MCQ)
  rationale (one sentence citing the chunk)
  supporting_chunk_ids (array of chunk_id strings)
  source_files (array of source_file strings)

Output only the JSON array, no other text."""


def generate_quiz(
    topic: str,
    num_questions: int = 10,
    difficulty: str = "medium",
    question_types: list[str] | None = None,
    source_filter: list[str] | None = None,
) -> Quiz:
    cfg = get_settings()
    question_types = question_types or cfg.quiz.default_question_types

    print(f"Retrieving top-{cfg.quiz.top_k_chunks} chunks for topic: {topic!r}")
    chunks = retrieve(topic, top_k=cfg.quiz.top_k_chunks, source_filter=source_filter)
    if not chunks:
        raise RuntimeError("No chunks retrieved. Run the index pipeline first.")

    print(f"Retrieved {len(chunks)} chunks. Generating {num_questions} questions...")
    system = _load_system_prompt()
    prompt = _build_prompt(topic, chunks, num_questions, difficulty, question_types)
    raw = generate(prompt, system=system)

    try:
        items_data = parse_json_response(raw)
    except ValueError as e:
        raise RuntimeError(f"Failed to parse model response as JSON: {e}\nRaw:\n{raw[:600]}")

    if not isinstance(items_data, list):
        items_data = [items_data]

    items = []
    for d in items_data:
        item = QuizItem(
            question_type=d.get("question_type", "mcq"),
            difficulty=d.get("difficulty", difficulty),
            question=d.get("question", ""),
            choices=d.get("choices"),
            answer_index=d.get("answer_index"),
            answer=d.get("answer"),
            rationale=d.get("rationale", ""),
            supporting_chunk_ids=d.get("supporting_chunk_ids", []),
            source_files=d.get("source_files", []),
        )
        items.append(item)

    if len(items) > num_questions:
        print(f"  Warning: model returned {len(items)} items; truncating to {num_questions}")
        items = items[:num_questions]
    elif len(items) < num_questions:
        print(f"  Warning: model returned {len(items)} items, expected {num_questions}")

    quiz = Quiz(
        topic=topic,
        difficulty=difficulty,
        items=items,
        generated_at=datetime.now().isoformat(),
        model=cfg.ollama.generation_model,
        source_scope=source_filter or [],
    )
    return quiz


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a quiz from the vector index.")
    parser.add_argument("--topic", required=True, help="Topic or question to retrieve chunks for")
    parser.add_argument("--num", type=int, default=None, help="Number of questions")
    parser.add_argument("--difficulty", default=None, choices=["easy", "medium", "hard"])
    parser.add_argument(
        "--types", nargs="+", default=None, choices=["mcq", "short_answer", "true_false"]
    )
    parser.add_argument("--sources", nargs="+", default=None, help="Filter by source filenames")
    args = parser.parse_args()

    cfg = get_settings()
    root = project_root()
    quiz = generate_quiz(
        topic=args.topic,
        num_questions=cfg.quiz.default_num_questions if args.num is None else args.num,
        difficulty=cfg.quiz.default_difficulty if args.difficulty is None else args.difficulty,
        question_types=cfg.quiz.default_question_types if args.types is None else args.types,
        source_filter=args.sources,
    )

    out_dir = root / cfg.quiz.quizzes_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w-]", "", args.topic.lower().replace(" ", "_"))[:40]
    out_path = out_dir / f"{slug}.json"
    out_path.write_text(quiz.model_dump_json(indent=2), encoding="utf-8")
    print(f"Quiz saved: {out_path} ({len(quiz.items)} questions)")


if __name__ == "__main__":
    main()
