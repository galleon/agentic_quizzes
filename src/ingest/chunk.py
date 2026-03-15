"""Chunk cleaned documents into overlapping segments and save to data/chunks/."""

from __future__ import annotations

import hashlib
import json
import re
import sys

from src.common.config import get_settings, project_root
from src.common.models import Chunk, ChunkMetadata
from src.ingest.parse_docling import DOCLING_MARKER


def _extract_title(text: str, fallback: str) -> str:
    """Try to grab the first non-empty line as the document title."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:120]
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


def _split_into_blocks(text: str) -> list[str]:
    """Split Markdown text into semantic blocks preserving tables and code fences.

    Each returned block is one of:
    - a fenced code block (``` ... ```)
    - a contiguous run of table rows (| ... |)
    - a heading line followed by its body paragraph
    - a regular paragraph
    """
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    in_table = False

    for line in text.splitlines():
        stripped = line.strip()

        # ---- Code fence toggle ----
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if not in_fence:
                # Flush any pending paragraph before opening fence
                if current:
                    block = "\n".join(current).strip()
                    if block:
                        blocks.append(block)
                    current = []
                in_fence = True
            else:
                in_fence = False
            current.append(line)
            if not in_fence:
                # Closing fence — flush the complete code block
                blocks.append("\n".join(current))
                current = []
            continue

        if in_fence:
            current.append(line)
            continue

        # ---- Table detection (contiguous pipe-prefixed lines) ----
        is_table_row = stripped.startswith("|")
        if is_table_row and not in_table:
            # Flush pending paragraph before the table
            if current:
                block = "\n".join(current).strip()
                if block:
                    blocks.append(block)
                current = []
            in_table = True
        elif not is_table_row and in_table:
            # End of table — flush
            blocks.append("\n".join(current))
            current = []
            in_table = False

        if in_table:
            current.append(line)
            continue

        # ---- Heading: flush pending paragraph first ----
        if stripped.startswith("#") and current:
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)
            current = []

        # ---- Blank line: flush pending paragraph ----
        if not stripped:
            if current:
                block = "\n".join(current).strip()
                if block:
                    blocks.append(block)
                current = []
            continue

        current.append(line)

    # Flush remainder
    if current:
        if in_fence:
            # Unclosed fence — emit as-is
            blocks.append("\n".join(current))
        elif in_table:
            blocks.append("\n".join(current))
        else:
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)

    return [b for b in blocks if b.strip()]


def _last_heading(blocks: list[str], from_idx: int) -> str:
    """Return text of the nearest Markdown heading at or before *from_idx* in *blocks*.

    Searches backwards from *from_idx* (inclusive) so that a chunk whose first
    block IS a heading correctly reports that heading as its section.
    """
    for i in range(from_idx, -1, -1):
        first_line = blocks[i].splitlines()[0] if blocks[i] else ""
        if first_line.lstrip().startswith("#"):
            return first_line.lstrip("#").strip()[:80]
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

    blocks = _split_into_blocks(text)
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
                section = _last_heading(blocks, current_start_idx)
                result.append(("\n\n".join(current_blocks), section))
                current_blocks = []
                current_word_count = 0
            section = _last_heading(blocks, i)
            result.append((block, section))
            current_start_idx = i + 1
            continue

        # Adding this block would exceed chunk_size: flush accumulated first
        if current_blocks and current_word_count + block_words > chunk_size:
            section = _last_heading(blocks, current_start_idx)
            result.append(("\n\n".join(current_blocks), section))

            # Overlap: keep trailing blocks that fit within the overlap budget
            overlap_blocks: list[str] = []
            overlap_count = 0
            for b in reversed(current_blocks):
                bwc = len(b.split())
                if overlap_count + bwc <= overlap:
                    overlap_blocks.insert(0, b)
                    overlap_count += bwc
                else:
                    break
            current_blocks = overlap_blocks
            current_start_idx = i - len(overlap_blocks)
            current_word_count = overlap_count

        current_blocks.append(block)
        current_word_count += block_words

    if current_blocks:
        section = _last_heading(blocks, current_start_idx)
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
            # Word-based chunking with page-marker provenance (PyMuPDF path)
            raw_path = extracted_dir / f.relative_to(in_dir)
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
        rel = f.relative_to(in_dir)
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
