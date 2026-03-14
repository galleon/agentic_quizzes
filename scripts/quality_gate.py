"""Quiz quality gate — used by GitHub Actions pipeline.yml.

Reads the generated quiz JSON and fails if the grounding pass rate
is below the configured threshold. Writes a summary to GITHUB_STEP_SUMMARY
when running in GitHub Actions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from src.common.config import get_settings, project_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--threshold", type=float, default=0.70)
    args = parser.parse_args()

    cfg = get_settings()
    root = project_root()
    slug = re.sub(r"[^\w-]", "", args.topic.lower().replace(" ", "_"))[:40]
    quiz_path = root / cfg.quiz.quizzes_dir / f"{slug}.json"

    if not quiz_path.exists():
        print(f"ERROR: quiz file not found: {quiz_path}", file=sys.stderr)
        sys.exit(1)

    quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
    items = quiz["items"]
    total = len(items)
    supported = sum(1 for i in items if i["grounding_verdict"] == "supported")
    rejected = sum(1 for i in items if i["confidence_flag"] == "rejected")
    pass_rate = supported / total if total else 0.0

    print(f"Topic:       {quiz['topic']}")
    print(f"Model:       {quiz['model']}")
    print(f"Total:       {total}")
    print(f"Supported:   {supported}")
    print(f"Rejected:    {rejected}")
    print(f"Pass rate:   {pass_rate:.0%}  (threshold: {args.threshold:.0%})")

    # Write GitHub Actions job summary if running in CI
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"## Quiz quality: {quiz['topic']}\n\n")
            fh.write("| Metric | Value |\n|--------|-------|\n")
            fh.write(f"| Total questions | {total} |\n")
            fh.write(f"| Grounding pass rate | {pass_rate:.0%} |\n")
            fh.write(f"| Rejected (hallucinated) | {rejected} |\n")
            fh.write(f"| Model | `{quiz['model']}` |\n")
            status = "✅ PASS" if pass_rate >= args.threshold else "❌ FAIL"
            fh.write(f"| Status | {status} |\n")

    if pass_rate < args.threshold:
        print(
            f"FAIL: {pass_rate:.0%} below threshold {args.threshold:.0%}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("PASS")


if __name__ == "__main__":
    main()
