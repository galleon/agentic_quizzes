---
name: review-quiz-quality
description: Review generated quizzes for grounding, ambiguity, duplicates, and pedagogical quality.
---

# Review Quiz Quality

Use this skill after quiz generation, or when the user asks to improve quiz quality.

## Goal

Review existing quiz outputs and identify concrete quality problems.

## Inputs

Typical inputs:

- `tmp/*.verified.json`
- `outputs/*/*.quiz.json`
- `outputs/*/*.quiz.md`

## Review Dimensions

Check for:

1. Grounding
   - Is the answer directly supported by the source?
   - Does the explanation add unsupported information?

2. Ambiguity
   - Could more than one option be defensible?
   - Is the wording vague or underspecified?

3. Pedagogical value
   - Does the question test understanding?
   - Is it too trivial or too superficial?

4. Distractor quality
   - Are wrong answers plausible?
   - Are they too obviously incorrect?

5. Duplication
   - Are multiple questions effectively the same?

## Output Style

Produce a concise review with:

- strengths
- recurring weaknesses
- 3 to 7 concrete improvement suggestions
- whether the issue is best fixed by:
  - prompt changes
  - verification changes
  - chunking changes
  - source extraction changes
  - instruction updates in `CLAUDE.md` or a Skill

## Editing Rule

Do not rewrite policy files automatically during a routine review.

Instead:

- propose a small diff
- explain the reason
- wait for explicit approval unless the human directly asked for the update
