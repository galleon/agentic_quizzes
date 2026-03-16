"""Shared fence-delimiter helpers used by clean.py and chunk.py."""

from __future__ import annotations

import re

# Matches the opening line of a fenced code block: 3+ backticks or tildes at
# the start of the (stripped) line, optionally followed by an info string.
FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})")


def is_closing_fence(stripped: str, opener: str) -> bool:
    """Return True only when *stripped* is a valid closing fence for *opener*.

    A closing fence must consist solely of the fence delimiter character
    (no info string like ```python) and be at least as long as the opener.
    """
    return stripped.lstrip(opener[0]) == "" and len(stripped) >= len(opener)
