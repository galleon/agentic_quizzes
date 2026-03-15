#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

TOPIC="${1:-}"
if [[ -z "$TOPIC" ]]; then
    echo "Usage: eval_quiz.sh <topic>" >&2
    exit 1
fi

echo "=== NanoClaw Quiz Evaluation ==="
echo "Re-validating topic: $TOPIC"

uv run python3 -m src.quiz.validate --topic "$TOPIC"
uv run python3 -m src.quiz.export   --topic "$TOPIC" --formats md json csv

echo "=== Evaluation complete ==="
