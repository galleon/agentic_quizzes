"""Build/update data/metadata/manifest.jsonl from chunk files."""

from __future__ import annotations

import json
from datetime import datetime

from src.common.config import get_settings, project_root


def main() -> None:
    cfg = get_settings()
    root = project_root()
    chunks_dir = root / cfg.ingest.chunks_dir
    meta_dir = root / cfg.ingest.metadata_dir
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = root / cfg.ingest.manifest_file

    entries = []
    for chunk_file in sorted(chunks_dir.rglob("*.chunks.jsonl")):
        with chunk_file.open(encoding="utf-8") as fh:
            num_chunks = sum(1 for line in fh if line.strip())
        entries.append(
            {
                "stem": chunk_file.stem.replace(".chunks", ""),
                "chunk_file": str(chunk_file.relative_to(root)),
                "num_chunks": num_chunks,
                "ingested_at": datetime.now().isoformat(),
            }
        )

    with manifest_path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")

    print(f"Manifest updated: {len(entries)} documents → {manifest_path}")


if __name__ == "__main__":
    main()
