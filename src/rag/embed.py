"""Compute embeddings for all chunks and write back to chunk files."""

from __future__ import annotations

import json
import sys

from src.common.config import get_settings, project_root
from src.common.ollama_client import embed


def main() -> None:
    cfg = get_settings()
    root = project_root()
    chunks_dir = root / cfg.ingest.chunks_dir

    chunk_files = list(chunks_dir.glob("*.chunks.jsonl"))
    if not chunk_files:
        print("No chunk files found. Run ingest pipeline first.", file=sys.stderr)
        sys.exit(1)

    for chunk_file in chunk_files:
        print(f"Embedding: {chunk_file.name}")
        lines = chunk_file.read_text(encoding="utf-8").splitlines()
        updated = []
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            chunk = json.loads(line)
            if chunk.get("embedding"):
                updated.append(line)
                continue
            vec = embed(chunk["text"])
            chunk["embedding"] = vec
            updated.append(json.dumps(chunk))
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(lines)} chunks embedded")

        chunk_file.write_text("\n".join(updated) + "\n" if updated else "", encoding="utf-8")
        print(f"  Done: {len(updated)} chunks")

    print("Embedding complete.")


if __name__ == "__main__":
    main()
