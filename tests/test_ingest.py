"""Ingest unit tests — no LLM, no Qdrant, no network."""

import pytest

from src.ingest.chunk import (
    chunk_structured_markdown,
    chunk_text,
    last_heading,
    split_into_blocks,
)
from src.ingest.clean import clean_text
from src.ingest.parse_docling import DOCLING_MARKER

# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


def test_clean_removes_page_markers():
    raw = "<!-- page 1 -->\nSome text.\n<!-- page 2 -->\nMore text."
    result = clean_text(raw)
    assert "<!-- page" not in result
    assert "Some text." in result
    assert "More text." in result


def test_clean_collapses_blank_lines():
    raw = "line1\n\n\n\n\nline2"
    result = clean_text(raw)
    assert "\n\n\n" not in result


def test_clean_collapses_spaces():
    raw = "word1   word2\t\tword3"
    result = clean_text(raw)
    assert "  " not in result


def test_clean_strips_trailing_whitespace():
    raw = "line with trailing spaces   \nanother line  "
    for line in clean_text(raw).splitlines():
        assert line == line.rstrip()


def test_clean_empty_input():
    assert clean_text("") == ""


def test_clean_preserves_content():
    raw = "NVIDIA DGX systems use DCGM for GPU health monitoring."
    assert clean_text(raw) == raw


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------


def test_chunk_basic():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_text(text, chunk_size=20, overlap=5)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)


def test_chunk_size_respected():
    text = " ".join(f"word{i}" for i in range(200))
    chunks = chunk_text(text, chunk_size=30, overlap=5)
    for chunk in chunks:
        assert len(chunk.split()) <= 30


def test_chunk_overlap():
    text = " ".join(str(i) for i in range(50))
    chunks = chunk_text(text, chunk_size=10, overlap=3)
    # Last word of chunk N should appear near the start of chunk N+1
    if len(chunks) >= 2:
        last_words = set(chunks[0].split()[-3:])
        first_words = set(chunks[1].split()[:3])
        assert last_words & first_words, "Expected overlap between consecutive chunks"


def test_chunk_short_text_is_single_chunk():
    text = "short text"
    chunks = chunk_text(text, chunk_size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0] == "short text"


def test_chunk_empty_text():
    assert chunk_text("", chunk_size=50, overlap=5) == []


def test_chunk_no_empty_chunks():
    text = " ".join(f"w{i}" for i in range(300))
    for chunk in chunk_text(text, chunk_size=50, overlap=10):
        assert chunk.strip() != ""


# ---------------------------------------------------------------------------
# split_into_blocks
# ---------------------------------------------------------------------------


def test_split_paragraphs():
    text = "Para one.\n\nPara two.\n\nPara three."
    blocks = split_into_blocks(text)
    assert len(blocks) == 3
    assert blocks[0] == "Para one."
    assert blocks[2] == "Para three."


def test_split_heading_starts_new_block():
    text = "Some intro text.\n## Section A\nSection body."
    blocks = split_into_blocks(text)
    assert any("## Section A" in b for b in blocks)
    assert any("Some intro text." in b for b in blocks)


def test_split_heading_attaches_to_following_paragraph():
    # A heading separated from its body by a blank line must not become an
    # isolated heading-only block — the heading and body should be one block.
    text = "## GPU Monitoring\n\nThis section covers GPU health."
    blocks = split_into_blocks(text)
    assert len(blocks) == 1
    assert "## GPU Monitoring" in blocks[0]
    assert "This section covers GPU health." in blocks[0]


def test_split_heading_only_chunk_section_metadata():
    # last_heading must still work when a heading is part of a merged block.
    # Build the body so each "## Section" heading is on its own line.
    body = "## Section\n\n" + " ".join(f"word{i}" for i in range(100))
    chunks = chunk_structured_markdown(body, chunk_size=20, overlap=2)
    assert all(section == "Section" for _, section in chunks)


def test_split_table_is_single_block():
    rows = "| Col A | Col B |\n|-------|-------|\n| val 1 | val 2 |\n| val 3 | val 4 |"
    text = f"Intro.\n\n{rows}\n\nOutro."
    blocks = split_into_blocks(text)
    table_blocks = [b for b in blocks if b.startswith("|")]
    assert len(table_blocks) == 1, "Table should be a single block"
    assert "val 3" in table_blocks[0]
    assert "val 1" in table_blocks[0]


def test_split_code_fence_is_single_block():
    text = "Intro.\n\n```python\ndef foo():\n    return 42\n```\n\nOutro."
    blocks = split_into_blocks(text)
    fence_blocks = [b for b in blocks if b.startswith("```")]
    assert len(fence_blocks) == 1
    assert "def foo():" in fence_blocks[0]
    assert "return 42" in fence_blocks[0]


def test_split_tilde_fence():
    text = "~~~bash\necho hello\n~~~"
    blocks = split_into_blocks(text)
    assert any("echo hello" in b for b in blocks)


def test_split_fence_info_string_not_treated_as_closer():
    # A line like ```python inside a ~~~-opened fence must NOT close it.
    text = "~~~\nsome code\n```python\nmore code\n~~~"
    blocks = split_into_blocks(text)
    fence_blocks = [b for b in blocks if b.startswith("~~~")]
    assert len(fence_blocks) == 1, "Opening info-string line must not close the fence"
    assert "```python" in fence_blocks[0]
    assert "more code" in fence_blocks[0]


def test_split_consecutive_headings_no_isolated_block():
    # Consecutive headings must accumulate and attach to the following content,
    # preserving hierarchical context. Neither heading should be emitted alone.
    text = "## Section A\n\n## Section B\n\nContent here."
    blocks = split_into_blocks(text)
    isolated = [b for b in blocks if b.strip() in ("## Section A", "## Section B")]
    assert not isolated, "Neither heading should be emitted as an isolated block"
    # Both headings and the content must end up in a single block.
    combined = [
        b for b in blocks if "## Section A" in b and "## Section B" in b and "Content here" in b
    ]  # noqa: E501
    assert len(combined) == 1


def test_split_longer_fence_not_closed_by_shorter():
    # A 4-backtick fence must not be closed by a 3-backtick line inside it.
    text = "````\nsome content\n```\nmore content\n````"
    blocks = split_into_blocks(text)
    fence_blocks = [b for b in blocks if b.startswith("````")]
    assert len(fence_blocks) == 1
    assert "```" in fence_blocks[0]
    assert "more content" in fence_blocks[0]


def test_clean_fence_info_string_not_treated_as_closer():
    # ```python inside a ~~~-opened fence must NOT close the fence early.
    raw = "~~~\n    indented code\n```python\n    more indented\n~~~\noutside   spaces"
    result = clean_text(raw)
    assert "    indented code" in result
    assert "    more indented" in result
    # Outside the fence, spaces should still be collapsed
    assert "outside spaces" in result


def test_split_empty_input():
    assert split_into_blocks("") == []


# ---------------------------------------------------------------------------
# last_heading
# ---------------------------------------------------------------------------


def test_last_heading_found():
    blocks = ["## GPU Monitoring", "Some paragraph.", "More text."]
    assert last_heading(blocks, 2) == "GPU Monitoring"


def test_last_heading_none():
    blocks = ["Just a paragraph.", "Another paragraph."]
    assert last_heading(blocks, 1) == ""


def test_last_heading_merged_block_returns_innermost():
    # When consecutive headings are merged into one block, last_heading must
    # return the most specific (last) heading, not the outermost one.
    blocks = ["# Title\n## Section\n\nSome content."]
    assert last_heading(blocks, 0) == "Section"


def test_last_heading_ignores_headings_inside_fence():
    # A '# comment' line inside a fenced code block must not be reported as
    # a section heading.
    blocks = ["## Real Heading\n\n```python\n# not a heading\n```"]
    assert last_heading(blocks, 0) == "Real Heading"


# ---------------------------------------------------------------------------
# chunk_structured_markdown
# ---------------------------------------------------------------------------


def test_chunk_structured_basic():
    body = "## Section\n\n" + " ".join(f"word{i}" for i in range(30))
    chunks = chunk_structured_markdown(body, chunk_size=20, overlap=3)
    assert len(chunks) >= 1
    for text, section in chunks:
        assert text.strip()


def test_chunk_structured_section_heading():
    body = "## GPU Health\n\n" + " ".join(f"w{i}" for i in range(10))
    chunks = chunk_structured_markdown(body, chunk_size=50, overlap=5)
    # All chunks should report the heading as their section
    for _, section in chunks:
        assert section == "GPU Health"


def test_chunk_structured_table_not_split():
    table = "\n".join(f"| col{i} | val{i} |" for i in range(20))
    body = f"## Commands\n\n{table}"
    chunks = chunk_structured_markdown(body, chunk_size=10, overlap=2)
    # The table block (20+ rows) exceeds chunk_size=10 and must still be emitted whole.
    # The preceding heading is merged with the table block (no isolated heading).
    assert len(chunks) == 1
    chunk_body = chunks[0][0]
    assert "col0" in chunk_body
    assert "col19" in chunk_body


def test_chunk_structured_oversized_block_emitted():
    oversized = " ".join(f"w{i}" for i in range(200))
    chunks = chunk_structured_markdown(oversized, chunk_size=50, overlap=5)
    assert len(chunks) == 1
    assert len(chunks[0][0].split()) == 200


def test_chunk_structured_code_fence_not_split():
    code_lines = "\n".join(f"    line_{i} = {i}" for i in range(30))
    body = f"```python\n{code_lines}\n```"
    chunks = chunk_structured_markdown(body, chunk_size=10, overlap=2)
    fence_chunks = [t for t, _ in chunks if t.startswith("```")]
    assert len(fence_chunks) == 1


def test_chunk_structured_overlap_never_exceeds_chunk_size():
    # chunk_size=50, overlap=40: without the trim guard, overlap_count=40
    # plus a 20-word next block gives 60 words — exceeding chunk_size.
    words = " ".join(f"w{i}" for i in range(20))  # 20-word block
    body = f"{words}\n\n{words}\n\n{words}\n\n{words}"
    chunks = chunk_structured_markdown(body, chunk_size=50, overlap=40)
    for text, _ in chunks:
        assert len(text.split()) <= 50, f"chunk exceeded chunk_size: {len(text.split())} words"


def test_chunk_structured_validation_errors():
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_structured_markdown("text", chunk_size=0, overlap=0)
    with pytest.raises(ValueError, match="overlap"):
        chunk_structured_markdown("text", chunk_size=10, overlap=-1)
    with pytest.raises(ValueError, match="overlap"):
        chunk_structured_markdown("text", chunk_size=10, overlap=10)


def test_chunk_structured_empty_input():
    assert chunk_structured_markdown("", chunk_size=50, overlap=5) == []


# ---------------------------------------------------------------------------
# clean_text — code fence preservation
# ---------------------------------------------------------------------------


def test_clean_preserves_code_fence_indentation():
    raw = "```python\ndef foo():\n    return 42\n```"
    result = clean_text(raw)
    assert "    return 42" in result, "4-space indentation inside code fence should be preserved"


def test_clean_still_collapses_spaces_outside_fence():
    raw = "outside   the   fence\n```\ncode  here\n```\nafter   fence"
    result = clean_text(raw)
    lines = result.splitlines()
    # First and last lines (outside fence) should have spaces collapsed
    assert "  " not in lines[0]
    assert "  " not in lines[-1]


def test_clean_preserves_blank_lines_inside_fence():
    # Multiple blank lines inside a code fence must not be collapsed.
    raw = "```\nline1\n\n\n\nline2\n```"
    result = clean_text(raw)
    assert "\n\n\n" in result, "blank lines inside a fence should be preserved verbatim"


def test_clean_collapses_blank_lines_outside_fence_only():
    # Three or more blank lines outside a fence collapse to one.
    raw = "para1\n\n\n\npara2"
    result = clean_text(raw)
    assert "\n\n\n" not in result
    assert "para1" in result and "para2" in result


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------


def test_parse_file_pdf_calls_docling(tmp_path, monkeypatch):
    """parse_file routes .pdf to parse_pdf_docling."""
    import src.ingest.parse as parse_module

    monkeypatch.setitem(parse_module._PARSERS, ".pdf", lambda _p: "docling output")
    fake_pdf = tmp_path / "doc.pdf"
    fake_pdf.write_bytes(b"")
    assert parse_module.parse_file(fake_pdf) == "docling output"


def test_parse_file_unsupported_extension(tmp_path, capsys):
    """parse_file returns '' and warns for unknown extensions."""
    import src.ingest.parse as parse_module

    f = tmp_path / "doc.docx"
    f.write_bytes(b"")
    result = parse_module.parse_file(f)
    assert result == ""
    assert "unsupported extension" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# parse_pdf_docling failure branches
# ---------------------------------------------------------------------------


def test_parse_pdf_docling_conversion_error(tmp_path, monkeypatch, capsys):
    """Conversion exception returns '' and prints a docling-error message."""
    import src.ingest.parse_docling as pd_module

    class _FailConverter:
        def convert(self, _path: object) -> None:
            raise RuntimeError("bad pdf")

    monkeypatch.setattr("docling.document_converter.DocumentConverter", _FailConverter)
    fake_pdf = tmp_path / "doc.pdf"
    fake_pdf.write_bytes(b"")

    assert pd_module.parse_pdf_docling(fake_pdf) == ""
    assert "docling error" in capsys.readouterr().err


def test_parse_pdf_docling_empty_output(tmp_path, monkeypatch, capsys):
    """Empty markdown output returns '' and prints a docling-warning message."""
    import src.ingest.parse_docling as pd_module

    class _Doc:
        def export_to_markdown(self) -> str:
            return "   "

    class _EmptyConverter:
        def convert(self, _path: object) -> object:
            return type("R", (), {"document": _Doc()})()

    monkeypatch.setattr("docling.document_converter.DocumentConverter", _EmptyConverter)
    fake_pdf = tmp_path / "doc.pdf"
    fake_pdf.write_bytes(b"")

    assert pd_module.parse_pdf_docling(fake_pdf) == ""
    assert "docling warning" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# DOCLING_MARKER constant sanity check
# ---------------------------------------------------------------------------


def test_docling_marker_not_page_marker():
    """The docling marker must not match the page-marker regex used in clean/chunk."""
    import re

    page_marker_re = re.compile(r"<!-- page \d+ -->")
    assert not page_marker_re.fullmatch(DOCLING_MARKER)


# ---------------------------------------------------------------------------
# ollama_client helpers (pure, no network)
# ---------------------------------------------------------------------------


def test_strip_think_tags():
    from src.common.ollama_client import _strip_think_tags

    assert _strip_think_tags("<think>reasoning</think>answer") == "answer"
    assert _strip_think_tags("no tags here") == "no tags here"
    assert _strip_think_tags("<think>multi\nline\n</think>result") == "result"


def test_parse_json_response_direct():
    from src.common.ollama_client import parse_json_response

    assert parse_json_response('{"verdict": "supported"}') == {"verdict": "supported"}
    assert parse_json_response("[1, 2, 3]") == [1, 2, 3]


def test_parse_json_response_fenced():
    from src.common.ollama_client import parse_json_response

    raw = '```json\n{"key": "value"}\n```'
    assert parse_json_response(raw) == {"key": "value"}


def test_parse_json_response_with_preamble():
    from src.common.ollama_client import parse_json_response

    raw = 'Here is the JSON:\n{"answer": 42}'
    assert parse_json_response(raw) == {"answer": 42}


def test_parse_json_response_with_trailing_text():
    from src.common.ollama_client import parse_json_response

    raw = '{"verdict": "supported"} some trailing explanation the model added'
    assert parse_json_response(raw) == {"verdict": "supported"}


def test_parse_json_response_invalid_raises():
    from src.common.ollama_client import parse_json_response

    with pytest.raises(ValueError, match="Could not parse JSON"):
        parse_json_response("this is not json at all")
