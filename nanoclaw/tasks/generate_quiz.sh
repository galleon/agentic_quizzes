#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

TOPIC="${1:-general}"
NUM="${2:-10}"
DIFFICULTY="${3:-medium}"

echo "=== NanoClaw Quiz Generation ==="
echo "Topic: $TOPIC | Questions: $NUM | Difficulty: $DIFFICULTY"

uv run python3 -m src.quiz.generate --topic "$TOPIC" --num "$NUM" --difficulty "$DIFFICULTY"
uv run python3 -m src.quiz.validate --topic "$TOPIC"
uv run python3 -m src.quiz.export   --topic "$TOPIC" --formats md json csv

echo "=== Quiz generation complete ==="
echo "Outputs in: outputs/quizzes/ outputs/answer_keys/ outputs/rationales/"
