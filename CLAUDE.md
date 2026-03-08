# Project Operating Rules

This repository is for grounded quiz generation from PDF source material.

## Mission

Turn PDF documents into high-quality quiz artifacts with explicit source grounding, verification, and reproducible outputs.

The preferred workflow is:

1. Extract PDF text into chunked JSON
2. Generate quiz candidates from chunks
3. Verify each candidate against the chunk source
4. Export final quiz artifacts
5. Summarize what was produced and what failed

## Hard Operating Constraints

You must behave as if you are operating in a restricted workspace.

- Only work inside:
  - `pdfs/`
  - `outputs/`
  - `tmp/`
- Prefer read/inspect actions before write actions.
- Never claim success unless the expected output files actually exist.
- Never say a quiz has been generated unless you have inspected the output file paths.
- Never use the network unless the human explicitly asks for it.
- Never install packages unless the human explicitly asks for it.
- Never modify files outside this repository.
- Never delete source PDFs.
- Never overwrite final outputs without first checking whether they already exist.

## Preferred Tooling

Use existing local tools before inventing new code.

Preferred commands:

```bash
python quiz_tools.py extract_pdf ...
python quiz_tools.py generate_quiz ...
python quiz_tools.py verify_quiz ...
python quiz_tools.py export_quiz ...
```

If these commands fail, inspect the error, explain the failure briefly, and adapt conservatively.

## Quiz Quality Rules

Every final quiz item must be:

- directly supported by the PDF source text
- answerable without external knowledge
- clear and unambiguous
- written in clean language
- associated with source page metadata
- associated with a supporting excerpt
- verified before export

Avoid:

- trivia with no learning value
- distractors that are absurdly easy
- explanations that introduce unsupported facts
- questions whose answer depends on unstated background knowledge
- duplicate or near-duplicate questions

Prefer:

- definitions
- comparisons
- processes
- cause/effect
- decision criteria
- distinctions between similar concepts
- practical interpretation of source content

## Output Expectations

For each input PDF, produce a dedicated folder under `outputs/`.

Expected files may include:

- `*.chunks.json`
- `*.raw_quiz.json`
- `*.verified.json`
- `*.quiz.json`
- `*.quiz.jsonl`
- `*.quiz.md`

At the end of a run, write or update a concise summary file documenting:

- input file
- number of chunks
- number of raw items
- number of verified items
- exported file paths
- issues encountered

## Failure Handling

When a step fails:

1. Inspect the exact error
2. Check whether the expected intermediate file exists
3. Retry with smaller scope if appropriate
4. Do not loop forever
5. Prefer one conservative retry over repeated blind retries

Examples of valid conservative retries:

- fewer questions per chunk
- fewer chunks in one pass
- re-running verification separately
- exporting only after inspecting verified outputs

## Editing Policy

You may improve helper scripts or prompts only when necessary for the current task.

Before editing core workflow files:

- first inspect them
- explain the reason briefly
- keep changes minimal
- preserve compatibility with the existing output schema

## Self-Improvement Policy

You may propose improvements to this `CLAUDE.md` or to Skills, but do not silently rewrite them during normal quiz runs.

Only update operational instructions when one of these is true:

- the human explicitly asks for improvement
- repeated failures show a stable pattern
- quality review identifies a recurring weakness
- a new local tool becomes the preferred path

When proposing instruction updates:

- prefer small diffs
- explain the observed issue
- explain why the change should help
- keep a changelog entry in the proposal
