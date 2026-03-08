# Quiz Generation Repo Skeleton

This repository is a Claude Code-oriented, sandbox-friendly skeleton for grounded quiz generation from PDFs.

## Included

- `CLAUDE.md`: project-wide operating rules
- `skills/generate-quiz/SKILL.md`: main workflow skill
- `skills/review-quiz-quality/SKILL.md`: quality review skill
- `skills/improve-quiz-policy/SKILL.md`: controlled self-improvement skill
- `sandbox/mini_bash_agent.py`: minimal guarded bash agent example
- `sandbox/Dockerfile`: simple container wrapper for sandboxed execution
- `pdfs/`, `tmp/`, `outputs/`: working directories

## Suggested usage

Place your PDFs in `pdfs/`, add your `quiz_tools.py`, and run Claude Code in this repo.

The operational pattern is:

1. extract PDF chunks
2. generate quiz candidates
3. verify them
4. export final artifacts
5. review quality
6. propose tiny policy updates only when evidence supports them

## Self-improving policy

The repo is designed so Claude can **propose** improvements to `CLAUDE.md` and Skills over time.
It should not silently rewrite them during routine runs.

Recommended loop:

- normal quiz generation
- quality review
- policy improvement proposal
- human approval
- commit to git

## External sandboxing

The markdown files steer behavior, but do not enforce security.
Use a real sandbox such as:

- Docker with `--network none`
- gVisor
- Firecracker-based runners

## Next steps

- add `quiz_tools.py`
- add tests for output schema
- add a review dataset to measure quiz quality over time
