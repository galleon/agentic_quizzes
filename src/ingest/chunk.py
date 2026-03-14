"""Chunk cleaned documents into overlapping segments and save to data/chunks/."""

from __future__ import annotations

import hashlib
import json
import re
import sys

from src.common.config import get_settings, project_root
from src.common.models import Chunk, ChunkMetadata


def _approx_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token."""
    return len(text) // 4


def _extract_title(text: str, fallback: str) -> str:
    """Try to grab the first non-empty line as the document title."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return fallback


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    """Split text into overlapping chunks of approximately chunk_size tokens."""
    words = text.split()
    chunks = []
    step = max(1, chunk_size - overlap)
    i = 0
    while i < len(words):
        segment = words[i : i + chunk_size]
        chunks.append(" ".join(segment))
        if i + chunk_size >= len(words):
            break
        i += step
    return chunks


def infer_page(chunk_text: str, full_text: str) -> str:
    """Attempt to find the page number nearest to this chunk in the source."""
    # Find position of chunk in full text (approximate)
    idx = full_text.find(chunk_text[:80])
    if idx == -1:
        return ""
    # Look backwards for the nearest page marker
    before = full_text[:idx]
    pages = re.findall(r"<!-- page (\d+) -->", before)
    return pages[-1] if pages else ""


def main() -> None:
    cfg = get_settings()
    root = project_root()
    in_dir = root / cfg.ingest.cleaned_dir
    out_dir = root / cfg.ingest.chunks_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Also read the extracted dir to get page markers for provenance
    extracted_dir = root / cfg.ingest.extracted_dir

    files = list(in_dir.glob("*.txt"))
    if not files:
        print("No cleaned files found. Run clean.py first.", file=sys.stderr)
        sys.exit(1)

    total_chunks = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        # Try to get raw text with page markers for provenance
        raw_path = extracted_dir / f.name
        raw_text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else text

        title = _extract_title(text, fallback=f.stem)
        raw_chunks = chunk_text(text, cfg.ingest.chunk_size, cfg.ingest.chunk_overlap)

        chunks: list[dict] = []
        for i, chunk_str in enumerate(raw_chunks):
            page = infer_page(chunk_str, raw_text)
            content_hash = hashlib.sha256(chunk_str.encode()).hexdigest()[:16]
            meta = ChunkMetadata(
                source_file=f.name,
                document_title=title,
                page_or_section=f"page {page}" if page else f"chunk {i + 1}",
                topic_tags=[],
                hash=content_hash,
            )
            chunk = Chunk(metadata=meta, text=chunk_str)
            chunks.append(chunk.model_dump(exclude={"embedding"}))

        out_path = out_dir / (f.stem + ".chunks.jsonl")
        with out_path.open("w", encoding="utf-8") as fh:
            for c in chunks:
                fh.write(json.dumps(c) + "\n")

        total_chunks += len(chunks)
        print(f"Chunked: {f.name} → {len(chunks)} chunks")

    print(f"Done. {total_chunks} total chunks written to {out_dir}")


if __name__ == "__main__":
    main()
