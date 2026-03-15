#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== NanoClaw Index Pipeline ==="
echo "Using configured embedding model from settings.yaml (via Ollama)"

uv run python3 -m src.rag.embed
uv run python3 -m src.rag.index

echo "=== Index complete ==="
