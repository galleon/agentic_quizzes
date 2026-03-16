"""Structured PDF extraction using local docling (tables, code blocks, headings)."""

from __future__ import annotations

import sys
from pathlib import Path

# Marker prepended to all docling-extracted files so downstream stages can
# detect and apply structure-aware processing (e.g. chunk_structured_markdown).
DOCLING_MARKER = "<!-- docling-structured-md -->"


def parse_pdf_docling(pdf_path: Path) -> str:
    """Extract PDF to structured Markdown using docling.

    Returns Markdown prefixed with DOCLING_MARKER on success.
    Returns an empty string when docling is not installed or on any
    conversion failure, so the caller can skip the file without crashing
    the ingest pipeline.  Install docling with: ``uv sync --group docling``
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        print(
            "  [docling] package not installed — skipping PDF."
            " Install with: uv sync --group docling",
            file=sys.stderr,
        )
        return ""

    try:
        converter = DocumentConverter()
        result = converter.convert(pdf_path)
        md = result.document.export_to_markdown()
    except Exception as exc:
        print(
            f"  [docling error] {pdf_path.name}: {exc}",
            file=sys.stderr,
        )
        return ""

    if not md.strip():
        print(
            f"  [docling warning] {pdf_path.name}: empty markdown output",
            file=sys.stderr,
        )
        return ""

    return DOCLING_MARKER + "\n" + md
