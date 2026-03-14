"""Shared helper for converting a topic string to a safe filename stem."""

from __future__ import annotations

import re


def make_slug(topic: str) -> str:
    """Return a safe, deterministic filename stem from a topic string.

    Lowercases, replaces spaces with underscores, strips any character that
    is not alphanumeric, underscore, or hyphen (prevents path traversal), and
    truncates to 40 characters.
    """
    return re.sub(r"[^\w-]", "", topic.lower().replace(" ", "_"))[:40]
