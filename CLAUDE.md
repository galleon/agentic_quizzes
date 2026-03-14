# Quiz RAG Agent (NanoClaw)

Generates grounded quizzes from source documents using local LLMs via Ollama + Qdrant.

## Rules
- **Never modify** files under `data/raw/`.
- Always preserve provenance: source document → chunk → generated question.
- Never generate an answer without retrieved supporting chunks.
- Prefer deterministic scripts in `nanoclaw/tasks/` over ad hoc shell one-liners.
- Write reports to `outputs/reports/`.
- Keep responses concise; do not emit long reasoning traces.
- Use `uv run` or activate `.venv` before running Python modules.

## Stack
- **Generation**: Ollama (`qwen2.5:instruct` default, `qwen3:latest` optional with `think: false`)
- **Embeddings**: Ollama `nomic-embed-text` (separate from generation model)
- **Vector store**: Qdrant (local file-based via `qdrant-client`)
- **PDF parsing**: PyMuPDF (`pymupdf`)
- **Config**: `nanoclaw/config/settings.yaml`

## Main tasks
```bash
bash nanoclaw/tasks/ingest.sh
bash nanoclaw/tasks/build_index.sh
bash nanoclaw/tasks/generate_quiz.sh "GPU monitoring" 10 medium
bash nanoclaw/tasks/eval_quiz.sh "GPU monitoring"
```

## Pipeline overview
1. **Ingest** — parse PDFs → clean text → chunk → manifest
2. **Index** — embed chunks → upsert to Qdrant
3. **Generate** — retrieve top-k chunks → generate MCQ/short-answer/T-F
4. **Validate** — check grounding → reject hallucinated answers → export

## Data layout
```
data/raw/        # immutable source files (PDF, DOCX, HTML)
data/extracted/  # raw text per document
data/cleaned/    # normalized text
data/chunks/     # chunk JSONL files
data/metadata/   # manifest.jsonl
vectorstore/     # Qdrant collection files
outputs/quizzes/         # generated quizzes (MD + JSON)
outputs/answer_keys/     # answer keys
outputs/rationales/      # per-question rationale
outputs/reports/         # ingest/index run reports
```

## Chunk metadata fields
`chunk_id`, `source_file`, `document_title`, `page_or_section`, `document_date`, `topic_tags`, `language`, `hash`

## Quiz item fields
`question_id`, `question_type`, `difficulty`, `question`, `choices`, `answer_index`, `answer`, `rationale`, `supporting_chunk_ids`, `source_files`, `grounding_verdict`, `confidence_flag`
