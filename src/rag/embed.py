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

    chunk_files = list(chunks_dir.rglob("*.chunks.jsonl"))
    if not chunk_files:
        print("No chunk files found. Run ingest pipeline first.", file=sys.stderr)
        sys.exit(1)

    for chunk_file in chunk_files:
        print(f"Embedding: {chunk_file.relative_to(chunks_dir)}")
        count = 0
        # Stream line-by-line through a temp file to keep memory bounded and
        # avoid partial-file corruption if the process is interrupted.
        tmp = Path(tempfile.mktemp(dir=chunk_file.parent, suffix=".tmp"))
        try:
            with chunk_file.open(encoding="utf-8") as src, tmp.open("w", encoding="utf-8") as dst:
                for i, line in enumerate(src):
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if not chunk.get("embedding"):
                        chunk["embedding"] = embed(chunk["text"])
                        if (i + 1) % 10 == 0:
                            print(f"  {i + 1} chunks processed")
                    dst.write(json.dumps(chunk) + "\n")
                    count += 1
            tmp.replace(chunk_file)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        print(f"  Done: {count} chunks")

    print("Embedding complete.")


if __name__ == "__main__":
    main()
