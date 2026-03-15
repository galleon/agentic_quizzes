"""Compute embeddings for all chunks and write back to chunk files."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from src.common.config import get_settings, project_root
from src.common.ollama_client import embed


def main() -> None:
    cfg = get_settings()
    root = project_root()
    chunks_dir = root / cfg.ingest.chunks_dir

    chunk_files = sorted(
        chunks_dir.rglob("*.chunks.jsonl"),
        key=lambda p: p.relative_to(chunks_dir).as_posix(),
    )
    if not chunk_files:
        print("No chunk files found. Run ingest pipeline first.", file=sys.stderr)
        sys.exit(1)

    for chunk_file in chunk_files:
        print(f"Embedding: {chunk_file.relative_to(chunks_dir)}")
        count = 0
        # Use NamedTemporaryFile so the fd is owned and closed by the context
        # manager — no fd leak even if chunk_file.open() or processing fails.
        ntf = tempfile.NamedTemporaryFile(
            delete=False, dir=chunk_file.parent, suffix=".tmp", mode="w", encoding="utf-8"
        )
        tmp = Path(ntf.name)
        try:
            with ntf, chunk_file.open(encoding="utf-8") as src:
                for i, line in enumerate(src):
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if not chunk.get("embedding"):
                        chunk["embedding"] = embed(chunk["text"])
                        if (i + 1) % 10 == 0:
                            print(f"  {i + 1} chunks processed")
                    ntf.write(json.dumps(chunk) + "\n")
                    count += 1
            tmp.replace(chunk_file)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        print(f"  Done: {count} chunks")

    print("Embedding complete.")


if __name__ == "__main__":
    main()
