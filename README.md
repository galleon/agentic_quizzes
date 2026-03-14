# NanoClaw Quiz RAG

Generates grounded quizzes from source documents using local LLMs (Ollama) and Qdrant.

## Prerequisites

```bash
# Install Python deps
uv sync --group dev

# Start Ollama (if not already running)
ollama serve &

# Pull required models
ollama pull nomic-embed-text        # embeddings
ollama pull qwen3.5-no-think:latest # generation

# Optional: create the no-think variant yourself
ollama create qwen3-nothink -f nanoclaw/config/modelfile_qwen3_nothink.txt
```

## Quick start

```bash
# Ensure Ollama is running
ollama serve &

# Full pipeline in one command (uses default topic/num/difficulty)
make all TOPIC="GPU monitoring with DCGM" NUM=10 DIFFICULTY=medium
```

Or step by step:

```bash
make ingest                                          # parse → clean → chunk → manifest
make index                                           # embed → upsert to Qdrant
make quiz TOPIC="GPU monitoring with DCGM"           # generate → validate → export
```

Outputs land under `outputs/` with a slug derived from the topic. The slug is
`<sanitized_prefix>_<8hex>` where the 8-character hex suffix is a SHA-256 hash of the
full topic string, ensuring uniqueness even when two topics share a long common prefix:

```
outputs/quizzes/gpu_monitoring_with_dcgm_3f8a1c2e.{md,json,csv}
outputs/answer_keys/gpu_monitoring_with_dcgm_3f8a1c2e_key.md
outputs/rationales/gpu_monitoring_with_dcgm_3f8a1c2e_rationales.md
```

Use `ls outputs/quizzes/` to find the exact filename for a given topic.

### Other useful targets

```bash
make eval  TOPIC="GPU monitoring with DCGM"   # re-validate an existing quiz
make clean                                     # wipe all generated artifacts, keep data/raw/
make help                                      # list all targets and defaults
```

## Configuration

Edit `nanoclaw/config/settings.yaml` to switch models, vector store mode, chunk sizes, etc.

## Qwen3 verbosity

Qwen3 has a hybrid think/no-think mode. NanoClaw suppresses chain-of-thought via three
layers:

1. `think=False` as a top-level kwarg in `ollama.chat()` — **the only reliably effective
   method** when you supply a custom system prompt (which overrides the modelfile default).
2. `/no_think` baked into the modelfile `SYSTEM` directive (effective only when no system
   message is passed in the API call).
3. `_strip_think_tags()` in `src/common/ollama_client.py` as a last-resort regex fallback.

> **Verified:** `qwen3.5-no-think:latest` has `SYSTEM /no_think` in its modelfile, but
> that default is silently overridden whenever a custom system message is sent. Always
> pass `think=False` explicitly.

## Skills (Claude Code)

- `/ingest-docs` — parse, clean, chunk source documents
- `/build-rag` — embed and index chunks into Qdrant
- `/generate-quiz` — retrieve + generate + validate + export

---

## Issues faced during first run

These were encountered and fixed during the initial end-to-end run.

### 1. `python` not on PATH
Task scripts used `python -m ...` but macOS ships without a `python` binary.
**Fix:** replaced with `uv run python3 -m ...` in all `nanoclaw/tasks/*.sh`.

### 2. `qdrant-client` API break
`QdrantClient.search()` was removed in v1.10+.
**Fix:** replaced with `client.query_points()` which returns `response.points`.

### 3. `pyproject.toml` build errors
Two issues with the initial config:
- `tool.uv.dev-dependencies` deprecated → replaced with `[dependency-groups]`
- `hatchling` couldn't auto-detect the package → added
  `[tool.hatch.build.targets.wheel] packages = ["src"]`

### 4. Custom system prompt overrides modelfile `/no_think`
`qwen3.5-no-think:latest` disables thinking via `SYSTEM /no_think` in its modelfile.
When `ollama.chat()` is called with an explicit system message, that default is silently
dropped. Verified by inspecting `response["message"]["thinking"]`.
**Fix:** always pass `think=False` as a top-level kwarg for any `qwen3*` model.

### 5. `num_predict: 600` truncates JSON output
600 tokens is sufficient for short chat responses but too tight for a full JSON array of
5 MCQ questions (each with 4 choices, rationale, chunk IDs). The output was cut off
mid-string, failing JSON parse.
**Fix:** raised to `num_predict: 4096` in `settings.yaml`.

### 6. Chunk size too coarse
Default `chunk_size: 512` (words) produces ~3000-char chunks. Four documents yielded
only 21 chunks total — too few for precise retrieval. The top-6 retrieved chunks for a
topic can cover 15 000+ chars (~4000 tokens) before the prompt even starts.
**Suggested fix:** reduce to `chunk_size: 200` for finer granularity (see improvements).

---

## Possible improvements

### Context management
The current pipeline sends raw chunk text directly into the generation prompt. For larger
corpora this breaks down quickly:

- **Token budgeting** — cap total chunk chars sent per generation call. Currently 6 × 3000
  chars = 18 KB with no guard.
- **Parent-child chunking** — index small chunks (128 words) for retrieval precision;
  expand to their parent chunk (512 words) for generation context. This avoids the
  coarse-vs-fine retrieval tradeoff.
- **Contextual retrieval** — prepend a brief document-level summary to each chunk before
  embedding (Anthropic-style), improving retrieval recall for short or context-light
  passages.
- **Reranking** — add a cross-encoder reranker step between retrieval and generation to
  filter out low-relevance chunks before they consume context budget.

### Better document extraction with docling
PyMuPDF extracts flat text. For NVIDIA technical documentation this misses:
- **Tables** — command references, parameter tables (e.g. DCGM subsystem table)
- **Code blocks** — CLI examples that are currently merged into prose
- **Document structure** — section hierarchy, captions, callouts

[docling](https://github.com/DS4SD/docling) (IBM) extracts rich structured Markdown/JSON
with full layout awareness. The user already has a docling instance running on a remote
host. A `ingest-docling` skill that calls that endpoint instead of `src/ingest/parse.py`
would significantly improve chunk quality for technical PDFs.

### Remote inference via vLLM
Ollama is convenient locally but limited in throughput and model selection. The user also
runs vLLM on a remote host. Because vLLM exposes an OpenAI-compatible API, the swap is
minimal — add a `vllm` provider option in `settings.yaml` and a thin adapter in
`ollama_client.py`. A `use-remote-llm` skill could configure the endpoint, model, and
auth token at runtime without touching source code.

### Gradio-compatible export format
The user has a Gradio quiz app that expects this schema:

```json
{
  "exam_info": {
    "title": "...",
    "certifications": ["NCP-AII"],
    "total_questions": 10,
    "time_limit_minutes": 30,
    "passing_score": 70,
    "last_updated": "March 2026"
  },
  "questions": [
    {
      "id": 1,
      "section": "GPU Monitoring",
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "correct_answer": 1,
      "explanation": "..."
    }
  ]
}
```

Key differences from the current `QuizItem` model:
- `options` (not `choices`)
- `correct_answer` is **1-indexed** (not 0-indexed `answer_index`)
- `explanation` (not `rationale`)
- `section` maps to `page_or_section` from chunk metadata
- `exam_info` wrapper with certification and timing metadata

Adding a `--format gradio` flag to `src/quiz/export.py` is straightforward.

### Chunk size tuning
Reduce `chunk_size` from 512 to 200 words (≈800 chars, ≈200 tokens) in `settings.yaml`.
This gives ~50–60 chunks for the current 4 PDFs — far better retrieval granularity — and
keeps per-chunk context under 1000 chars, reducing prompt bloat.
