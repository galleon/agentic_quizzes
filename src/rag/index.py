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

    chunk_files = list(chunks_dir.glob("*.chunks.jsonl"))
    if not chunk_files:
        print("No chunk files found.", file=sys.stderr)
        sys.exit(1)

    client = get_client(cfg)
    ensure_collection(client, cfg)

    total_upserted = 0
    report_lines = [f"# Index Report\n\nRun: {datetime.now().isoformat()}\n\n"]

    for chunk_file in chunk_files:
        lines = chunk_file.read_text(encoding="utf-8").splitlines()
        points = []
        skipped = 0
        for line in lines:
            if not line.strip():
                continue
            chunk = json.loads(line)
            if not chunk.get("embedding"):
                skipped += 1
                continue
            meta = chunk["metadata"]
            point = PointStruct(
                id=meta["chunk_id"],
                vector=chunk["embedding"],
                payload={
                    "text": chunk["text"],
                    "source_file": meta["source_file"],
                    "document_title": meta["document_title"],
                    "page_or_section": meta["page_or_section"],
                    "document_date": meta.get("document_date", ""),
                    "topic_tags": meta.get("topic_tags", []),
                    "language": meta.get("language", "en"),
                    "hash": meta.get("hash", ""),
                    "chunk_id": meta["chunk_id"],
                },
            )
            points.append(point)

        if points:
            client.upsert(collection_name=cfg.qdrant.collection, points=points)
            total_upserted += len(points)
            print(
                f"Indexed: {chunk_file.name} → {len(points)} points"
                f" ({skipped} skipped, no embedding)"
            )
            report_lines.append(
                f"- `{chunk_file.name}`: {len(points)} indexed, {skipped} skipped\n"
            )

    report_lines.append(f"\n**Total upserted**: {total_upserted}\n")
    reports_dir = root / cfg.quiz.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "index_report.md").write_text("".join(report_lines))
    print(f"Indexing complete. {total_upserted} points in collection '{cfg.qdrant.collection}'.")


if __name__ == "__main__":
    main()
