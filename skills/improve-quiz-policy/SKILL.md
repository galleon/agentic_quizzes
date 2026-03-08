---
name: improve-quiz-policy
description: Propose targeted improvements to CLAUDE.md and quiz-generation skills based on repeated failure patterns.
---

# Improve Quiz Policy

Use this skill when the user asks to improve the workflow, or when repeated failures show that current instructions are insufficient.

## Goal

Refine the repository's behavioral instructions without changing them recklessly.

## Core Principle

Policy should evolve slowly and only from evidence.

Do not make broad stylistic rewrites.
Prefer minimal, evidence-based instruction changes.

## Evidence Sources

You may use:

- repeated generation failures
- repeated verification failures
- duplicate question patterns
- poor distractor patterns
- user feedback on quiz quality
- recurring export or workflow mistakes

## Allowed Targets

- `CLAUDE.md`
- `skills/generate-quiz/SKILL.md`
- `skills/review-quiz-quality/SKILL.md`

## Required Process

1. Identify a recurring issue.
2. Quote or summarize the evidence briefly.
3. Explain which instruction is missing, weak, or misleading.
4. Propose the smallest useful textual change.
5. Show the proposed patch or replacement section.
6. Explain the expected benefit.
7. Avoid changing unrelated text.

## Good Examples of Policy Evolution

- add a stronger rule against unsupported explanations
- add a retry rule after repeated malformed JSON
- add a review step for duplicate questions
- add preference for conceptual questions over rote extraction
- tighten the requirement to inspect output files before claiming success

## Bad Examples of Policy Evolution

- rewriting the whole file for style
- adding many speculative rules without evidence
- silently changing workflow policy during a normal run
- encoding environment-specific assumptions without need

## Output Format

When invoked, produce:

- Observed issue
- Evidence
- Proposed instruction change
- Expected benefit
- Minimal patch
