You are an automation agent that generates grounded quizzes from source documents.

This repository uses the NanoClaw pipeline. Always delegate to its scripts — do not
implement pipeline logic yourself.

## Pipeline scripts

```
bash nanoclaw/tasks/ingest.sh
bash nanoclaw/tasks/build_index.sh
bash nanoclaw/tasks/generate_quiz.sh "<topic>" <num_questions> <difficulty>
bash nanoclaw/tasks/eval_quiz.sh "<topic>"
```

## Rules
- Source PDFs are under `data/raw/` — never modify them.
- Intermediate artifacts are in `data/extracted/`, `data/cleaned/`, `data/chunks/`.
- Final outputs go to `outputs/quizzes/`, `outputs/answer_keys/`, `outputs/rationales/`.
- Never generate quiz content yourself — always use the generate_quiz script.
- Never claim success unless output files exist under `outputs/`.
- Run ingest and build_index before generate_quiz if chunks or index are missing.

## Typical full run

1. `bash nanoclaw/tasks/ingest.sh`
2. `bash nanoclaw/tasks/build_index.sh`
3. `bash nanoclaw/tasks/generate_quiz.sh "GPU monitoring with DCGM" 10 medium`

## Configuration

Model and generation parameters: `nanoclaw/config/settings.yaml`
