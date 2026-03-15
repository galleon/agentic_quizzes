---
name: ingest-docs
description: Parse source documents, clean text, chunk content, and save normalized artifacts.
---

When invoked:
1. Scan `data/raw/` for supported files (PDF, HTML, MD, TXT).
2. Parse each file into plain text, preserving page markers.
3. Save extracted text under `data/extracted/`.
4. Clean and normalize into `data/cleaned/`.
5. Chunk documents into `data/chunks/` as `.chunks.jsonl` files.
6. Update `data/metadata/manifest.jsonl`.
7. **Never delete or modify raw files.**
8. Write a run report to `outputs/reports/parse_report.md`.

Run via:
```bash
bash nanoclaw/tasks/ingest.sh
```

Or step by step:
```bash
uv run python3 -m src.ingest.parse
uv run python3 -m src.ingest.clean
uv run python3 -m src.ingest.chunk
uv run python3 -m src.ingest.enrich_metadata
```
