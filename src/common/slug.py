"""Shared helper for converting a topic string to a safe filename stem."""

from __future__ import annotations

import re


def make_slug(topic: str) -> str:
    """Return a safe, deterministic filename stem from a topic string.

    Lowercases, replaces spaces with underscores, strips any character that
    is not ASCII alphanumeric, underscore, or hyphen (prevents path traversal
    and non-ASCII surprises), and truncates to 40 characters.

    Raises ValueError if the resulting slug is empty (e.g. topic is all
    punctuation), so callers get a clear error instead of writing to '.json'.
    """
    slug = re.sub(r"[^a-z0-9_-]", "", topic.lower().replace(" ", "_"))[:40]
    if not slug:
        raise ValueError(f"Topic {topic!r} produces an empty slug after sanitization.")
    return slug
