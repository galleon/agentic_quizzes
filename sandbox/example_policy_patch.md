# Example policy improvement proposal

Observed issue:
- Too many rote extraction questions with weak distractors.

Evidence:
- Multiple generated quizzes contained near-verbatim questions and obviously wrong options.

Proposed instruction change:
- Strengthen the preference for conceptual questions and plausible distractors.

Expected benefit:
- Better pedagogical value and reduced low-quality MCQs.

Minimal patch:
- In `CLAUDE.md`, under "Prefer", add:
  - concept checks that require interpretation, not just copying
  - distractors that are plausible but clearly incorrect based on the source
