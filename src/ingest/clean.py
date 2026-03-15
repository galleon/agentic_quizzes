"""Normalize extracted text: remove noise, fix whitespace, write to data/cleaned/."""

from __future__ import annotations

import re
import sys

from src.common.config import get_settings, project_root

_MULTI_NEWLINE = re.compile(r"\n{3,}")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_PAGE_MARKER = re.compile(r"<!-- page \d+ -->")


def clean_text(raw: str) -> str:
    # Drop page markers (keep content)
    text = _PAGE_MARKER.sub("", raw)
    text = _MULTI_NEWLINE.sub("\n\n", text)

    # Collapse consecutive spaces/tabs per line, but skip lines inside code
    # fences so that indentation (e.g. Python indent) is not destroyed.
    cleaned: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            cleaned.append(line.rstrip())
        elif in_fence:
            cleaned.append(line.rstrip())
        else:
            cleaned.append(_MULTI_SPACE.sub(" ", line).rstrip())

    return "\n".join(cleaned).strip()


def main() -> None:
    cfg = get_settings()
    root = project_root()
    in_dir = root / cfg.ingest.extracted_dir
    out_dir = root / cfg.ingest.cleaned_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.rglob("*.txt"), key=lambda p: p.relative_to(in_dir).as_posix())
    if not files:
        print("No extracted files found. Run parse.py first.", file=sys.stderr)
        sys.exit(1)

    for f in files:
        raw = f.read_text(encoding="utf-8")
        cleaned = clean_text(raw)
        # Mirror subdirectory structure from extracted/ into cleaned/
        out_path = out_dir / f.relative_to(in_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(cleaned, encoding="utf-8")
        print(f"Cleaned: {f.relative_to(in_dir)} ({len(raw)} → {len(cleaned)} chars)")

    print(f"Done. {len(files)} files cleaned to {out_dir}")


if __name__ == "__main__":
    main()
