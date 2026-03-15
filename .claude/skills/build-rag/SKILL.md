---
name: build-rag
description: Build or refresh the Qdrant vector index from prepared chunks.
---

When invoked:
1. Read chunk files from `data/chunks/*.chunks.jsonl`.
2. Compute embeddings using `nomic-embed-text` via Ollama.
3. Upsert chunks into the Qdrant collection (local file-based by default).
4. Preserve metadata: `source_file`, `page_or_section`, `chunk_id`, `document_title`, `hash`.
5. Write index stats to `outputs/reports/index_report.md`.

Prerequisites:
- Ollama running with `nomic-embed-text` model pulled.
- Ingest pipeline completed (`data/chunks/` populated).

Run via:
```bash
bash nanoclaw/tasks/build_index.sh
```

Or step by step:
```bash
uv run python3 -m src.rag.embed
uv run python3 -m src.rag.index
```

To switch to Qdrant server mode, set `qdrant.mode: server` in `nanoclaw/config/settings.yaml`.
