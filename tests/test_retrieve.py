"""Unit tests for src/rag/retrieve.py.

All Qdrant and embedding calls are mocked — no running services required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.rag.retrieve import retrieve


def _make_point(chunk_id: str, text: str, source_file: str = "doc.txt", score: float = 0.9):
    """Build a fake Qdrant ScoredPoint-like object."""
    return SimpleNamespace(
        payload={
            "chunk_id": chunk_id,
            "text": text,
            "source_file": source_file,
            "page_or_section": "chunk 1",
        },
        score=score,
    )


def _make_empty_point():
    """A point with no payload (simulates corrupt/missing data)."""
    return SimpleNamespace(payload=None, score=0.5)


def _make_textless_point():
    """A point whose payload exists but has no text."""
    return SimpleNamespace(payload={"chunk_id": "x", "source_file": "f"}, score=0.4)


@pytest.fixture(autouse=True)
def _clear_lru(monkeypatch):
    """Clear the cached client between tests."""
    from src.rag import retrieve as retrieve_mod

    retrieve_mod._cached_client.cache_clear()
    yield
    retrieve_mod._cached_client.cache_clear()


@patch("src.rag.retrieve.embed", return_value=[0.1, 0.2, 0.3])
@patch("src.rag.retrieve._cached_client")
def test_retrieve_returns_matching_results(mock_client_fn, mock_embed):
    """retrieve() returns payloads enriched with 'score'."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.query_points.return_value = SimpleNamespace(points=[_make_point("c1", "some text")])

    results = retrieve("my query", top_k=3)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"
    assert results[0]["text"] == "some text"
    assert results[0]["score"] == pytest.approx(0.9)


@patch("src.rag.retrieve.embed", return_value=[0.1, 0.2, 0.3])
@patch("src.rag.retrieve._cached_client")
def test_retrieve_skips_points_with_missing_payload(mock_client_fn, mock_embed):
    """Points with None payload or empty text are excluded from results."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.query_points.return_value = SimpleNamespace(
        points=[
            _make_empty_point(),
            _make_textless_point(),
            _make_point("c2", "valid text"),
        ]
    )

    results = retrieve("query", top_k=5)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "c2"


@patch("src.rag.retrieve.embed", return_value=[0.0])
@patch("src.rag.retrieve._cached_client")
def test_retrieve_no_source_filter_passes_none(mock_client_fn, mock_embed):
    """When source_filter is None, query_filter is not passed."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.query_points.return_value = SimpleNamespace(points=[])

    retrieve("query", top_k=3, source_filter=None)

    call_kwargs = mock_client.query_points.call_args.kwargs
    assert call_kwargs["query_filter"] is None


@patch("src.rag.retrieve.embed", return_value=[0.0])
@patch("src.rag.retrieve._cached_client")
def test_retrieve_source_filter_builds_correct_filter(mock_client_fn, mock_embed):
    """When source_filter is provided, a FieldCondition/MatchAny filter is built."""
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.query_points.return_value = SimpleNamespace(points=[])

    retrieve("query", top_k=3, source_filter=["doc_a.txt", "doc_b.txt"])

    call_kwargs = mock_client.query_points.call_args.kwargs
    f = call_kwargs["query_filter"]
    assert isinstance(f, Filter)
    assert len(f.must) == 1
    condition = f.must[0]
    assert isinstance(condition, FieldCondition)
    assert condition.key == "source_file"
    assert isinstance(condition.match, MatchAny)
    assert set(condition.match.any) == {"doc_a.txt", "doc_b.txt"}


@patch("src.rag.retrieve.embed", return_value=[0.0])
@patch("src.rag.retrieve._cached_client")
def test_retrieve_empty_source_filter_passes_none(mock_client_fn, mock_embed):
    """An empty list source_filter is treated the same as None (no filter)."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.query_points.return_value = SimpleNamespace(points=[])

    retrieve("query", top_k=3, source_filter=[])

    call_kwargs = mock_client.query_points.call_args.kwargs
    assert call_kwargs["query_filter"] is None
