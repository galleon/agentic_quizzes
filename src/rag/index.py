"""Upsert embedded chunks into Qdrant and write index stats report."""

from __future__ import annotations

import json
import sys
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.common.config import get_settings, project_root


def get_client(cfg) -> QdrantClient:
    if cfg.qdrant.mode == "local":
        path = str(project_root() / cfg.qdrant.local_path)
        return QdrantClient(path=path)
    return QdrantClient(url=cfg.qdrant.server_url)


def ensure_collection(client: QdrantClient, cfg) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if cfg.qdrant.collection not in existing:
        client.create_collection(
            collection_name=cfg.qdrant.collection,
            vectors_config=VectorParams(
                size=cfg.qdrant.vector_size,
                distance=Distance.COSINE,
            ),
        )
        print(f"Created collection: {cfg.qdrant.collection}")


def main() -> None:
    cfg = get_settings()
    root = project_root()
    chunks_dir = root / cfg.ingest.chunks_dir

    chunk_files = sorted(
        chunks_dir.rglob("*.chunks.jsonl"),
        key=lambda p: p.relative_to(chunks_dir).as_posix(),
    )
    if not chunk_files:
        print("No chunk files found.", file=sys.stderr)
        sys.exit(1)

    client = get_client(cfg)
    ensure_collection(client, cfg)

    total_upserted = 0
    report_lines = [f"# Index Report\n\nRun: {datetime.now().isoformat()}\n\n"]

    batch_size = 100
    for chunk_file in chunk_files:
        batch: list[PointStruct] = []
        file_total = 0
        skipped = 0
        rel = chunk_file.relative_to(chunks_dir)
        # Stream and upsert in batches to keep memory bounded for large files.
        with chunk_file.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if not chunk.get("embedding"):
                    skipped += 1
                    continue
                meta = chunk["metadata"]
                batch.append(
                    PointStruct(
                        id=meta["chunk_id"],
                        vector=chunk["embedding"],
                        payload={
                            "text": chunk["text"],
                            "source_file": meta["source_file"],
                            "document_title": meta["document_title"],
                            "page_or_section": meta.get("page_or_section", ""),
                            "document_date": meta.get("document_date", ""),
                            "topic_tags": meta.get("topic_tags", []),
                            "language": meta.get("language", "en"),
                            "hash": meta.get("hash", ""),
                            "chunk_id": meta["chunk_id"],
                        },
                    )
                )
                if len(batch) >= batch_size:
                    client.upsert(collection_name=cfg.qdrant.collection, points=batch)
                    file_total += len(batch)
                    batch = []
            if batch:
                client.upsert(collection_name=cfg.qdrant.collection, points=batch)
                file_total += len(batch)

        if file_total:
            total_upserted += file_total
            print(f"Indexed: {rel} → {file_total} points ({skipped} skipped, no embedding)")
            report_lines.append(f"- `{rel}`: {file_total} indexed, {skipped} skipped\n")

    report_lines.append(f"\n**Total upserted**: {total_upserted}\n")
    reports_dir = root / cfg.quiz.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "index_report.md").write_text("".join(report_lines), encoding="utf-8")
    print(f"Indexing complete. {total_upserted} points in collection '{cfg.qdrant.collection}'.")
    if total_upserted == 0:
        print(
            "No points indexed — run embed.py before index.py, or check for embedding errors.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
