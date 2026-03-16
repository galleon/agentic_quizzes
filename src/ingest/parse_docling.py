"""Structured PDF extraction using local docling (tables, code blocks, headings)."""

from __future__ import annotations

import sys
from pathlib import Path

from docling.document_converter import DocumentConverter

# Marker prepended to all docling-extracted files so downstream stages can
# detect and apply structure-aware processing (e.g. chunk_structured_markdown).
DOCLING_MARKER = "<!-- docling-structured-md -->"


def parse_pdf_docling(pdf_path: Path) -> str:
    """Extract PDF to structured Markdown using docling.

    Returns Markdown prefixed with DOCLING_MARKER on success.
    Returns an empty string on conversion failure so the caller can skip
    the file without crashing the ingest pipeline.
    """
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
