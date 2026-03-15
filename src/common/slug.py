"""Shared helper for converting a topic string to a safe filename stem."""

from __future__ import annotations

import hashlib
import re


def make_slug(topic: str) -> str:
    """Return a safe, deterministic, unique filename stem from a topic string.

    Lowercases, replaces spaces with underscores, strips any character that
    is not ASCII alphanumeric, underscore, or hyphen (prevents path traversal
    and non-ASCII surprises), truncates the readable part to 32 characters,
    then appends an 8-hex-char hash of the *full* original topic so that two
    topics sharing the same 32-char prefix still produce distinct slugs.

    Raises ValueError if the sanitized prefix is empty (e.g. topic is all
    punctuation), so callers get a clear error instead of writing to '.json'.
    """
    prefix = re.sub(r"[^a-z0-9_-]", "", topic.lower().replace(" ", "_"))[:32]
    if not prefix:
        raise ValueError(f"Topic {topic!r} produces an empty slug after sanitization.")
    suffix = hashlib.sha256(topic.encode()).hexdigest()[:8]
    return f"{prefix}_{suffix}"
