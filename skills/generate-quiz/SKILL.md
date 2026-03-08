---
name: generate-quiz
description: Generate grounded quizzes from PDFs using local tools in a sandbox-friendly workflow.
---

# Generate Quiz from PDFs

Use this skill when the user wants quizzes, assessments, flashcards, or MCQs generated from PDF source material.

## Goal

Produce grounded quiz artifacts from one or more PDFs using the local quiz toolchain.

## Assumptions

- Source PDFs are in `pdfs/`
- Outputs go to `outputs/`
- Temporary/intermediate files go to `tmp/`
- `quiz_tools.py` exists in the repo
- The environment is sandboxed externally
- The model backend may be served locally through vLLM or another local endpoint

## Required Workflow

For each PDF:

1. Inspect the source file and determine its stem.
2. Create per-document paths under `tmp/` and `outputs/`.
3. Run extraction.
4. Inspect the extraction result.
5. Run candidate generation.
6. Inspect the raw quiz result.
7. Run verification.
8. Inspect the verified result.
9. Export final artifacts.
10. Confirm the exported files exist.
11. Add a summary entry.

## Canonical Command Pattern

```bash
python quiz_tools.py extract_pdf "pdfs/<file>.pdf" "tmp/<stem>.chunks.json"
python quiz_tools.py generate_quiz "tmp/<stem>.chunks.json" "tmp/<stem>.raw_quiz.json"
python quiz_tools.py verify_quiz "tmp/<stem>.chunks.json" "tmp/<stem>.raw_quiz.json" "tmp/<stem>.verified.json"
python quiz_tools.py export_quiz "tmp/<stem>.verified.json" "outputs/<stem>" --stem "<stem>"
```

Use the actual local options required by the project, but keep the command structure consistent.

## Inspection Checklist

After extraction, inspect:

- chunk count
- whether chunk text is non-empty
- whether the file was actually created

After generation, inspect:

- number of generated candidates
- obvious malformed objects
- generation errors embedded in output

After verification, inspect:

- verified count
- dropped count
- repeated failure reasons

After export, inspect:

- expected output files exist
- markdown export is readable
- JSON export is structurally plausible

## Retry Strategy

Use at most one conservative retry per failed document unless the human asks for deeper iteration.

Allowed retries:

- reduce questions per chunk
- reduce chunk batch size
- separate verification from generation and inspect intermediate files
- regenerate only a problematic document, not the whole corpus

Do not retry blindly if the error is environmental.

## Quality Standard

A good quiz set should have:

- questions that test understanding rather than copying text
- plausible distractors
- concise explanations
- explicit source grounding
- no duplicate questions
- no unsupported claims

## Deliverable Summary Format

For each PDF, summarize:

- source file
- chunk count
- raw item count
- verified item count
- exported paths
- one-line issue summary

## Refusal/Stop Conditions

Stop and report clearly if:

- the PDF has no extractable text
- the toolchain is missing
- outputs cannot be written
- repeated failures suggest the source document is unsuitable
