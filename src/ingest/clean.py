"""Normalize extracted text: remove noise, fix whitespace, write to data/cleaned/."""

from __future__ import annotations

import re
import sys

from src.common.config import get_settings, project_root

_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_PAGE_MARKER = re.compile(r"<!-- page \d+ -->")
_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})")


def _is_closing_fence(stripped: str, opener: str) -> bool:
    """Return True only when *stripped* is a valid closing fence for *opener*.

    A closing fence must consist solely of the fence delimiter character
    (no info string like ```python) and be at least as long as the opener.
    """
    return stripped.lstrip(opener[0]) == "" and len(stripped) >= len(opener)


def clean_text(raw: str) -> str:
    # Drop page markers (keep content)
    text = _PAGE_MARKER.sub("", raw)

    # Process line by line so that fence-interior content is never modified:
    # - inside a fence: preserve all whitespace (indentation, blank lines)
    # - outside a fence: collapse runs of spaces/tabs; limit to one blank line
    #   between paragraphs (i.e. suppress any blank line beyond the first in a
    #   consecutive run, equivalent to collapsing \n{3,} → \n\n but only
    #   outside fences).
    cleaned: list[str] = []
    fence_opener: str | None = None
    blank_run = 0

    for line in text.splitlines():
        stripped = line.strip()
        m = _FENCE_OPEN_RE.match(stripped) if fence_opener is None else None
        if m:
            fence_opener = m.group(1)  # exact run, e.g. "```" or "````" or "~~~"
            blank_run = 0
            cleaned.append(line.rstrip())
        elif fence_opener is not None and _is_closing_fence(stripped, fence_opener):
            fence_opener = None
            blank_run = 0
            cleaned.append(line.rstrip())
        elif fence_opener is not None:
            # Inside fence: preserve line verbatim (indentation + blank lines)
            cleaned.append(line.rstrip())
        else:
            if not stripped:
                blank_run += 1
                if blank_run == 1:
                    cleaned.append("")
                # else: suppress extra blank lines
            else:
                blank_run = 0
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
