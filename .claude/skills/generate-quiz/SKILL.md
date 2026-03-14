---
name: generate-quiz
description: Retrieve relevant chunks and generate grounded quizzes with answers and evidence.
---

When invoked:
1. Accept a topic, source scope, difficulty, and target number of questions.
2. Retrieve top-k chunks from the Qdrant vector store.
3. Generate MCQ, short-answer, or true/false questions via the local LLM.
4. For each question, include:
   - answer / answer_index
   - rationale (one sentence)
   - supporting_chunk_ids
   - confidence_flag (ok | low | rejected)
5. Validate grounding: reject hallucinated questions.
6. Save outputs under:
   - `outputs/quizzes/<topic>.{json,md,csv}`
   - `outputs/answer_keys/<topic>_key.md`
   - `outputs/rationales/<topic>_rationales.md`
7. **Refuse to generate unsupported answers** if evidence is insufficient.

Run via:
```bash
bash nanoclaw/tasks/generate_quiz.sh "GPU monitoring" 10 medium
```

Or step by step:
```bash
python -m src.quiz.generate --topic "GPU monitoring" --num 10 --difficulty medium
python -m src.quiz.validate --topic "GPU monitoring"
python -m src.quiz.export   --topic "GPU monitoring" --formats md json csv
```

LLM verbosity controls (see `nanoclaw/config/settings.yaml`):
- `think: false` — disables Qwen3 chain-of-thought
- `temperature: 0.2` — low randomness for factual output
- `num_predict: 600` — caps response length
