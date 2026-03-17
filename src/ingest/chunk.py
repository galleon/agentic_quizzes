"""Chunk cleaned documents into overlapping segments and save to data/chunks/."""

from __future__ import annotations

import hashlib
import json
import re
import sys

from src.common.config import get_settings, project_root
from src.common.models import Chunk, ChunkMetadata
from src.ingest._fence import FENCE_OPEN_RE, is_closing_fence
from src.ingest.parse_docling import DOCLING_MARKER

_ATX_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)")


def _extract_title(text: str, fallback: str) -> str:
    """Try to grab the first non-empty line as the document title.

    Lines matching the ATX heading pattern (``^#{1,6}\\s+``) have their
    leading ``#`` markers stripped, so docling-structured docs don't produce
    titles like ``# My Document``.  Lines that start with ``#`` but are not
    ATX headings — shebangs (``#!/usr/bin/env bash``) or token-adjacent
    markers like ``#define`` — don't match the pattern and are returned as-is.
    Note that a bare ``# comment`` (hash + space) *does* match the ATX pattern
    and will have its ``#`` stripped.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _ATX_HEADING_RE.match(line)
        return (m.group(1).strip() if m else line)[:120]
    return fallback


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    """Split text into overlapping chunks of approximately chunk_size words."""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if overlap < 0:
        raise ValueError(f"overlap must be >= 0, got {overlap}")
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be < chunk_size ({chunk_size})")
    words = text.split()
    chunks = []
    step = max(1, chunk_size - overlap)
    i = 0
    while i < len(words):
        segment = words[i : i + chunk_size]
        chunks.append(" ".join(segment))
        if i + chunk_size >= len(words):
            break
        i += step
    return chunks


def split_into_blocks(text: str) -> list[str]:
    """Split Markdown text into semantic blocks preserving tables and code fences.

    Each returned block is one of:
    - a fenced code block (``` ... ```)
    - a contiguous run of table rows (| ... |), optionally preceded by a
      heading that is merged into the block rather than emitted in isolation
    - one or more headings merged with the content that follows them
      (paragraph, table, or fence); blank lines between headings and their
      body are absorbed; consecutive headings accumulate in the pending buffer
      so that hierarchical context (e.g. ``# Title`` + ``## Section``) is
      preserved in the same block as the following content — a heading that
      trails the entire input with no following content may still be emitted
      alone
    - a regular paragraph
    """
    blocks: list[str] = []
    current: list[str] = []
    # Incremental flag: True iff every non-empty line in current is an ATX
    # heading.  Updated on every append so the four flush decision-points can
    # check it in O(1) instead of rescanning current each time.
    current_heading_only: bool = True
    fence_opener: str | None = None  # exact opening run, e.g. "```" or "````" or "~~~"
    in_table = False

    for line in text.splitlines():
        stripped = line.strip()

        # ---- Code fence handling ----
        # Track the opening delimiter so a mismatched marker inside the fence
        # (e.g. a ``` line inside a ~~~ block) does not prematurely close it.
        m = FENCE_OPEN_RE.match(stripped) if fence_opener is None else None
        if m:
            # Opening a new fence: flush any pending paragraph first.
            # If current contains only headings, keep them so the heading
            # attaches to the fence block rather than becoming isolated.
            if current and not current_heading_only:
                block = "\n".join(current).strip()
                if block:
                    blocks.append(block)
                current = []
                current_heading_only = True
            fence_opener = m.group(1)  # exact run, e.g. "```" or "````" or "~~~"
            current.append(line)
            current_heading_only = False  # fence delimiter is not a heading
            continue

        if fence_opener is not None:
            current.append(line)
            current_heading_only = False  # fence content is never heading-only
            if is_closing_fence(stripped, fence_opener):
                # Closing fence: only delimiter chars, no info string (e.g. not ```python)
                blocks.append("\n".join(current))
                current = []
                current_heading_only = True
                fence_opener = None
            continue

        # ---- Table detection (contiguous pipe-prefixed lines) ----
        is_table_row = stripped.startswith("|")
        if is_table_row and not in_table:
            # Flush pending paragraph before the table.
            # If current contains only headings, keep them so the heading
            # attaches to the table block rather than becoming isolated.
            if current and not current_heading_only:
                block = "\n".join(current).strip()
                if block:
                    blocks.append(block)
                current = []
                current_heading_only = True
            in_table = True
        elif not is_table_row and in_table:
            # End of table — flush
            blocks.append("\n".join(current))
            current = []
            current_heading_only = True
            in_table = False

        if in_table:
            current.append(line)
            current_heading_only = False  # table rows are not headings
            continue

        # ---- Heading: flush pending paragraph first ----
        # If current contains only headings (no body yet), keep them so they
        # accumulate with the new heading and eventually attach to the next
        # content block, preserving hierarchical context (e.g. # Title + ##
        # Section both appear in the same block as their following paragraph).
        if _ATX_HEADING_RE.match(stripped) and current and not current_heading_only:
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)
            current = []
            current_heading_only = True

        # ---- Blank line: flush pending paragraph ----
        # Exception: if current contains only heading lines, keep them so the
        # heading attaches to the following content rather than becoming an
        # isolated heading-only block (e.g. "## Heading\n\nParagraph" → one block).
        if not stripped:
            if current and not current_heading_only:
                block = "\n".join(current).strip()
                if block:
                    blocks.append(block)
                current = []
                current_heading_only = True
            continue

        current.append(line)
        current_heading_only = current_heading_only and bool(_ATX_HEADING_RE.match(stripped))

    # Flush remainder
    if current:
        if fence_opener is not None:
            # Unclosed fence — emit as-is
            blocks.append("\n".join(current))
        elif in_table:
            blocks.append("\n".join(current))
        else:
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)

    return [b for b in blocks if b.strip()]


def last_heading(blocks: list[str], from_idx: int) -> str:
    """Return the most specific Markdown heading at or before *from_idx*.

    Searches backwards through blocks from *from_idx* (inclusive).  Within
    each block, lines are scanned top-to-bottom while tracking fence state so
    that heading-like lines inside fenced code blocks are ignored.  The last
    heading found outside a fence is returned, giving the most specific
    heading when multiple headings have been merged into one block.
    """
    for i in range(from_idx, -1, -1):
        fence_opener: str | None = None
        last: str = ""
        for line in blocks[i].splitlines():
            stripped = line.strip()
            if fence_opener is None:
                mf = FENCE_OPEN_RE.match(stripped)
                if mf:
                    fence_opener = mf.group(1)
                    continue
                mh = _ATX_HEADING_RE.match(stripped)
                if mh:
                    last = mh.group(1).strip()[:80]
            elif is_closing_fence(stripped, fence_opener):
                fence_opener = None
        if last:
            return last
    return ""


def chunk_structured_markdown(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[tuple[str, str]]:
    """Chunk structured Markdown text respecting block boundaries.

    Returns a list of ``(chunk_text, section_heading)`` tuples.  *section_heading*
    is the nearest preceding Markdown heading (stripped of ``#`` markers) which
    callers can use as ``page_or_section`` metadata.  Empty string when no
    heading precedes the chunk.

    Blocks larger than *chunk_size* words are emitted as single oversized chunks
    rather than being silently truncated or broken mid-table/mid-code.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if overlap < 0:
        raise ValueError(f"overlap must be >= 0, got {overlap}")
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be < chunk_size ({chunk_size})")

    blocks = split_into_blocks(text)
    if not blocks:
        return []

    result: list[tuple[str, str]] = []
    current_blocks: list[str] = []
    current_start_idx: int = 0  # index into blocks[] of first block in the current chunk
    current_word_count: int = 0

    for i, block in enumerate(blocks):
        block_words = len(block.split())
        if not block_words:
            continue

        # Oversized single block: flush accumulated then emit block alone
        if block_words > chunk_size:
            if current_blocks:
                section = last_heading(blocks, current_start_idx)
                result.append(("\n\n".join(current_blocks), section))
                current_blocks = []
                current_word_count = 0
            section = last_heading(blocks, i)
            result.append((block, section))
            current_start_idx = i + 1
            continue

        # Adding this block would exceed chunk_size: flush accumulated first
        if current_blocks and current_word_count + block_words > chunk_size:
            section = last_heading(blocks, current_start_idx)
            result.append(("\n\n".join(current_blocks), section))

            # Overlap: keep trailing blocks that fit within the overlap budget,
            # then trim further if the carry-over would prevent the next block
            # from fitting within chunk_size.
            overlap_blocks: list[str] = []
            overlap_count = 0
            for b in reversed(current_blocks):
                bwc = len(b.split())
                if overlap_count + bwc <= overlap:
                    overlap_blocks.insert(0, b)
                    overlap_count += bwc
                else:
                    break
            while overlap_blocks and overlap_count + block_words > chunk_size:
                overlap_count -= len(overlap_blocks.pop(0).split())
            current_blocks = overlap_blocks
            current_start_idx = i - len(overlap_blocks)
            current_word_count = overlap_count

        current_blocks.append(block)
        current_word_count += block_words

    if current_blocks:
        section = last_heading(blocks, current_start_idx)
        result.append(("\n\n".join(current_blocks), section))

    return result


def _normalize_ws(text: str) -> str:
    """Collapse all whitespace runs to a single space."""
    return " ".join(text.split())


_PAGE_MARKER_RE = re.compile(r"<!-- page \d+ -->")


def infer_page(chunk_text: str, full_text: str, _normalized_haystack: str | None = None) -> str:
    """Attempt to find the page number nearest to this chunk in the source.

    Chunks are built from *cleaned* text (page markers removed), so the
    haystack must also have markers stripped before matching; otherwise chunks
    that span a page boundary will never match.  ``full_text`` (with markers)
    is still used to scan backwards for the nearest ``<!-- page N -->`` tag.

    Pass a precomputed ``_normalized_haystack`` (marker-stripped + ws-normalised)
    to avoid re-running the O(n) normalisation on every call.
    """
    needle = _normalize_ws(chunk_text[:80])
    haystack = (
        _normalized_haystack
        if _normalized_haystack is not None
        else _normalize_ws(_PAGE_MARKER_RE.sub("", full_text))
    )
    idx = haystack.find(needle)
    if idx == -1:
        return ""
    # Recover approximate position in original text and scan back for page marker
    before = full_text[: int(idx * len(full_text) / max(len(haystack), 1))]
    pages = re.findall(r"<!-- page (\d+) -->", before)
    return pages[-1] if pages else ""


def main() -> None:
    cfg = get_settings()
    root = project_root()
    in_dir = root / cfg.ingest.cleaned_dir
    out_dir = root / cfg.ingest.chunks_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Also read the extracted dir to get page markers for provenance
    extracted_dir = root / cfg.ingest.extracted_dir

    files = sorted(in_dir.rglob("*.txt"), key=lambda p: p.relative_to(in_dir).as_posix())
    if not files:
        print("No cleaned files found. Run clean.py first.", file=sys.stderr)
        sys.exit(1)

    total_chunks = 0
    for f in files:
        text = f.read_text(encoding="utf-8")

        is_structured = text.startswith(DOCLING_MARKER)
        # Strip the marker line so it doesn't leak into chunk content or titles
        body = text[len(DOCLING_MARKER) :].lstrip("\n") if is_structured else text

        title = _extract_title(body, fallback=f.stem)
        rel = f.relative_to(in_dir)

        chunks: list[dict] = []

        if is_structured:
            # Structure-aware chunking: keeps tables, code fences, and headings intact.
            # page_or_section is derived from the nearest preceding Markdown heading.
            structured = chunk_structured_markdown(
                body, cfg.ingest.chunk_size, cfg.ingest.chunk_overlap
            )
            for i, (chunk_str, section) in enumerate(structured):
                content_hash = hashlib.sha256(chunk_str.encode()).hexdigest()[:16]
                meta = ChunkMetadata(
                    source_file=rel.as_posix(),
                    document_title=title,
                    page_or_section=f"§ {section}" if section else f"chunk {i + 1}",
                    topic_tags=[],
                    hash=content_hash,
                )
                chunks.append(
                    Chunk(metadata=meta, text=chunk_str).model_dump(exclude={"embedding"})
                )
        else:
            # Word-based chunking with page-marker provenance (.txt/.md/.html path)
            raw_path = extracted_dir / rel
            raw_text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else text
            raw_chunks = chunk_text(body, cfg.ingest.chunk_size, cfg.ingest.chunk_overlap)
            # Strip page markers before normalising so cleaned chunks match across page boundaries
            normalized_raw = _normalize_ws(_PAGE_MARKER_RE.sub("", raw_text))
            for i, chunk_str in enumerate(raw_chunks):
                page = infer_page(chunk_str, raw_text, normalized_raw)
                content_hash = hashlib.sha256(chunk_str.encode()).hexdigest()[:16]
                # Use relative path as source_file so same-named files in
                # different subdirectories remain distinguishable in metadata,
                # source_filter queries, and reporting.
                meta = ChunkMetadata(
                    source_file=rel.as_posix(),
                    document_title=title,
                    page_or_section=f"page {page}" if page else f"chunk {i + 1}",
                    topic_tags=[],
                    hash=content_hash,
                )
                chunks.append(
                    Chunk(metadata=meta, text=chunk_str).model_dump(exclude={"embedding"})
                )

        # Mirror subdirectory structure so same-stem files in different
        # subdirectories don't overwrite each other's chunk file.
        out_path = out_dir / rel.parent / (f.stem + ".chunks.jsonl")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            for c in chunks:
                fh.write(json.dumps(c) + "\n")

        total_chunks += len(chunks)
        print(f"Chunked: {rel} → {len(chunks)} chunks")

    print(f"Done. {total_chunks} total chunks written to {out_dir}")


if __name__ == "__main__":
    main()
