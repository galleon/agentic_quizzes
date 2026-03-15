#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== NanoClaw Ingest Pipeline ==="
echo "Project root: $PROJECT_ROOT"

uv run python3 -m src.ingest.parse
uv run python3 -m src.ingest.clean
uv run python3 -m src.ingest.chunk
uv run python3 -m src.ingest.enrich_metadata

echo "=== Ingest complete ==="
