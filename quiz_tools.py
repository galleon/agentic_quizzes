from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import typer
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

app = typer.Typer(add_completion=False, no_args_is_help=True)


# ============================================================
# Data models
# ============================================================

class QuizItem(BaseModel):
    question: str = Field(min_length=8)
    choices: list[str] = Field(min_length=4, max_length=4)
    correct_answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=8)
    source_page_start: int = Field(ge=1)
    source_page_end: int = Field(ge=1)
    source_excerpt: str = Field(min_length=12)
    difficulty: str = Field(pattern=r"^(easy|medium|hard)$")
    topic: str = Field(min_length=2)


class VerificationResult(BaseModel):
    supported: bool
    issues: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


@dataclass
class Chunk:
    chunk_id: str
    page_start: int
    page_end: int
    text: str


# ============================================================
# Utilities
# ============================================================

def build_client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(
        base_url=base_url.rstrip("/") + "/v1",
        api_key=api_key,
    )


def normalize_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    for para in paras:
        para = re.sub(r"\s+", " ", para).strip()
        if len(para) >= 40:
            out.append(para)
    return out


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_json_from_text(text: str) -> Any:
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1).strip())

    arr = re.search(r"(\[\s*{.*}\s*\])", text, flags=re.DOTALL)
    if arr:
        return json.loads(arr.group(1))

    obj = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if obj:
        return json.loads(obj.group(1))

    raise ValueError("No valid JSON found in model output.")


def llm_json(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 2200,
) -> Any:
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = response.choices[0].message.content or ""
    return extract_json_from_text(content)


def dedupe_items(items: list[QuizItem]) -> list[QuizItem]:
    seen: set[str] = set()
    kept: list[QuizItem] = []

    for item in items:
        key = re.sub(r"[^\w\s]", "", item.question.lower()).strip()
        key = re.sub(r"\s+", " ", key)
        if key not in seen:
            seen.add(key)
            kept.append(item)

    return kept


# ============================================================
# PDF extraction and chunking
# ============================================================

def extract_pages(pdf_path: Path) -> list[dict[str, Any]]:
    doc = fitz.open(pdf_path)
    pages: list[dict[str, Any]] = []
    try:
        for i, page in enumerate(doc):
            # sort=True improves reading order for many PDFs
            text = page.get_text("text", sort=True).strip()
            if text:
                pages.append(
                    {
                        "page_num": i + 1,
                        "text": normalize_whitespace(text),
                    }
                )
    finally:
        doc.close()
    return pages


def build_chunks(
    pages: list[dict[str, Any]],
    *,
    min_chars: int = 1200,
    max_chars: int = 3500,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_start: int | None = None
    current_end: int | None = None
    current_len = 0
    chunk_idx = 0

    def flush() -> None:
        nonlocal current_parts, current_start, current_end, current_len, chunk_idx
        if not current_parts or current_start is None or current_end is None:
            return
        chunk_idx += 1
        chunks.append(
            Chunk(
                chunk_id=f"chunk-{chunk_idx:04d}",
                page_start=current_start,
                page_end=current_end,
                text="\n\n".join(current_parts).strip(),
            )
        )
        current_parts = []
        current_start = None
        current_end = None
        current_len = 0

    for page in pages:
        page_num = page["page_num"]
        paras = split_paragraphs(page["text"])

        for para in paras:
            if current_start is None:
                current_start = page_num

            # flush if this paragraph would exceed chunk size
            if current_len > 0 and current_len + len(para) + 2 > max_chars:
                flush()
                current_start = page_num

            current_parts.append(para)
            current_end = page_num
            current_len += len(para) + 2

            # flush at a natural boundary when enough content was accumulated
            if current_len >= min_chars and para.endswith((".", ":", ";", "?", "!")):
                flush()

    flush()
    return chunks


# ============================================================
# Prompts
# ============================================================

GEN_SYSTEM = """
You generate grounded multiple-choice quiz questions from source material.

Rules:
- Output ONLY valid JSON.
- Return a JSON array.
- Each item must contain exactly these keys:
  question, choices, correct_answer_index, explanation,
  source_page_start, source_page_end, source_excerpt, difficulty, topic
- choices must have exactly 4 distinct options.
- correct_answer_index must be an integer 0..3.
- Every answer must be directly supported by the supplied source text.
- Do not invent facts.
- source_excerpt must be a short verbatim excerpt from the source text.
- explanation must stay faithful to the source text.
- Prefer concept checks, definitions, comparisons, process understanding, cause/effect, or interpretation.
- Avoid trivial copy-paste questions unless the source is itself definitional.
- Use clear and concise language.
"""

VERIFY_SYSTEM = """
You verify whether a multiple-choice quiz item is supported by the supplied source text.

Rules:
- Output ONLY valid JSON.
- Return an object with exactly these keys:
  supported, issues, confidence
- supported=true only if:
  1. the correct answer is directly supported,
  2. the explanation adds no unsupported facts,
  3. the excerpt genuinely supports the answer,
  4. the distractors do not make the question ambiguous.
- confidence must be between 0 and 1.
- issues must be short strings.
"""


# ============================================================
# Commands
# ============================================================

@app.command("extract_pdf")
def extract_pdf_cmd(
    pdf: Path = typer.Argument(..., exists=True, readable=True, help="Input PDF"),
    out_json: Path = typer.Argument(..., help="Output chunks JSON"),
    min_chars: int = typer.Option(1200, help="Minimum chars per chunk"),
    max_chars: int = typer.Option(3500, help="Maximum chars per chunk"),
) -> None:
    pages = extract_pages(pdf)
    chunks = build_chunks(pages, min_chars=min_chars, max_chars=max_chars)

    payload = {
        "pdf": str(pdf),
        "page_count": len(pages),
        "chunk_count": len(chunks),
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "text": chunk.text,
            }
            for chunk in chunks
        ],
    }

    save_json(out_json, payload)
    typer.echo(str(out_json))


@app.command("generate_quiz")
def generate_quiz_cmd(
    chunks_json: Path = typer.Argument(..., exists=True, readable=True, help="Chunk JSON"),
    out_json: Path = typer.Argument(..., help="Raw quiz JSON"),
    model: str = typer.Option("qwen3.5", help="Model name"),
    base_url: str = typer.Option("http://localhost:8000", help="vLLM base URL without /v1"),
    api_key: str = typer.Option("local-token", help="API key"),
    questions_per_chunk: int = typer.Option(2, min=1, max=8, help="MCQs per chunk"),
    max_chunks: int = typer.Option(0, help="0 means all chunks"),
) -> None:
    data = load_json(chunks_json)
    raw_chunks = data["chunks"]
    if max_chunks > 0:
        raw_chunks = raw_chunks[:max_chunks]

    client = build_client(base_url=base_url, api_key=api_key)
    all_items: list[dict[str, Any]] = []

    for raw in raw_chunks:
        chunk = Chunk(
            chunk_id=raw["chunk_id"],
            page_start=raw["page_start"],
            page_end=raw["page_end"],
            text=raw["text"],
        )

        user_prompt = f"""
Generate {questions_per_chunk} multiple-choice quiz items from the source below.

Metadata:
- chunk_id: {chunk.chunk_id}
- source_page_start: {chunk.page_start}
- source_page_end: {chunk.page_end}

Source:
\"\"\"
{chunk.text}
\"\"\"

Return only a JSON array.
"""

        try:
            result = llm_json(
                client=client,
                model=model,
                system_prompt=GEN_SYSTEM,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=2400,
            )

            if not isinstance(result, list):
                all_items.append(
                    {
                        "_generation_error": "Model did not return a JSON array.",
                        "_chunk_id": chunk.chunk_id,
                    }
                )
                continue

            for obj in result:
                try:
                    item = QuizItem.model_validate(obj)
                    # enforce provenance from chunk
                    item.source_page_start = chunk.page_start
                    item.source_page_end = chunk.page_end
                    all_items.append(item.model_dump())
                except ValidationError as exc:
                    all_items.append(
                        {
                            "_generation_error": f"Schema validation failed: {exc}",
                            "_chunk_id": chunk.chunk_id,
                            "_raw_item": obj,
                        }
                    )
        except Exception as exc:
            all_items.append(
                {
                    "_generation_error": str(exc),
                    "_chunk_id": chunk.chunk_id,
                }
            )

    save_json(out_json, all_items)
    typer.echo(str(out_json))


@app.command("verify_quiz")
def verify_quiz_cmd(
    chunks_json: Path = typer.Argument(..., exists=True, readable=True, help="Chunk JSON"),
    quiz_json: Path = typer.Argument(..., exists=True, readable=True, help="Raw quiz JSON"),
    out_json: Path = typer.Argument(..., help="Verified quiz JSON"),
    model: str = typer.Option("qwen3.5", help="Model name"),
    base_url: str = typer.Option("http://localhost:8000", help="vLLM base URL without /v1"),
    api_key: str = typer.Option("local-token", help="API key"),
    min_confidence: float = typer.Option(0.75, min=0.0, max=1.0, help="Minimum confidence"),
) -> None:
    chunks_data = load_json(chunks_json)
    quiz_data = load_json(quiz_json)
    client = build_client(base_url=base_url, api_key=api_key)

    chunk_map: dict[tuple[int, int], Chunk] = {}
    for raw in chunks_data["chunks"]:
        chunk = Chunk(
            chunk_id=raw["chunk_id"],
            page_start=raw["page_start"],
            page_end=raw["page_end"],
            text=raw["text"],
        )
        chunk_map[(chunk.page_start, chunk.page_end)] = chunk

    kept: list[QuizItem] = []
    dropped: list[dict[str, Any]] = []

    for obj in quiz_data:
        if "_generation_error" in obj:
            dropped.append(obj)
            continue

        try:
            item = QuizItem.model_validate(obj)
        except ValidationError as exc:
            dropped.append(
                {
                    "item": obj,
                    "reason": f"schema_error: {exc}",
                }
            )
            continue

        chunk = chunk_map.get((item.source_page_start, item.source_page_end))
        if chunk is None:
            dropped.append(
                {
                    "item": item.model_dump(),
                    "reason": "missing_chunk_for_item",
                }
            )
            continue

        prompt = f"""
Verify the following quiz item against the source text.

Quiz item:
{item.model_dump_json(indent=2)}

Source text:
\"\"\"
{chunk.text}
\"\"\"

Return only a JSON object.
"""

        try:
            result = llm_json(
                client=client,
                model=model,
                system_prompt=VERIFY_SYSTEM,
                user_prompt=prompt,
                temperature=0.0,
                max_tokens=500,
            )
            verdict = VerificationResult.model_validate(result)

            if verdict.supported and verdict.confidence >= min_confidence:
                kept.append(item)
            else:
                dropped.append(
                    {
                        "item": item.model_dump(),
                        "verdict": verdict.model_dump(),
                    }
                )
        except Exception as exc:
            dropped.append(
                {
                    "item": item.model_dump(),
                    "reason": f"verification_error: {exc}",
                }
            )

    kept = dedupe_items(kept)

    payload = {
        "verified_count": len(kept),
        "dropped_count": len(dropped),
        "items": [item.model_dump() for item in kept],
        "dropped": dropped,
    }

    save_json(out_json, payload)
    typer.echo(str(out_json))


@app.command("export_quiz")
def export_quiz_cmd(
    verified_json: Path = typer.Argument(..., exists=True, readable=True, help="Verified quiz JSON"),
    out_dir: Path = typer.Argument(..., help="Output directory"),
    stem: str = typer.Option("quiz", help="Output filename stem"),
) -> None:
    data = load_json(verified_json)
    items = [QuizItem.model_validate(x) for x in data["items"]]

    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{stem}.quiz.json"
    jsonl_path = out_dir / f"{stem}.quiz.jsonl"
    md_path = out_dir / f"{stem}.quiz.md"
    summary_path = out_dir / f"{stem}.summary.json"

    json_path.write_text(
        json.dumps([item.model_dump() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with jsonl_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.model_dump(), ensure_ascii=False) + "\n")

    lines: list[str] = [f"# Quiz: {stem}", ""]
    for i, item in enumerate(items, start=1):
        lines.append(f"## Q{i}. {item.question}")
        lines.append("")
        for idx, choice in enumerate(item.choices):
            label = chr(ord("A") + idx)
            suffix = " ✅" if idx == item.correct_answer_index else ""
            lines.append(f"- {label}. {choice}{suffix}")
        lines.append("")
        lines.append(f"**Explanation:** {item.explanation}")
        lines.append(f"**Topic:** {item.topic}")
        lines.append(f"**Difficulty:** {item.difficulty}")
        lines.append(f"**Pages:** {item.source_page_start}-{item.source_page_end}")
        lines.append(f"**Excerpt:** {item.source_excerpt}")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "stem": stem,
        "item_count": len(items),
        "files": {
            "json": str(json_path),
            "jsonl": str(jsonl_path),
            "markdown": str(md_path),
        },
    }
    save_json(summary_path, summary)

    typer.echo(str(md_path))


if __name__ == "__main__":
    app()
