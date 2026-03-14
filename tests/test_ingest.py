"""Ingest unit tests — no LLM, no Qdrant, no network."""

import pytest

from src.ingest.chunk import chunk_text
from src.ingest.clean import clean_text

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
