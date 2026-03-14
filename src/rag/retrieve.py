"""Query Qdrant for top-k chunks relevant to a topic."""

from __future__ import annotations

from src.common.config import get_settings
from src.common.ollama_client import embed
from src.rag.index import get_client


def retrieve(
    query: str,
    top_k: int | None = None,
    source_filter: list[str] | None = None,
) -> list[dict]:
    """Return top-k payload dicts (including 'text') for a query string."""
    cfg = get_settings()
    top_k = top_k or cfg.quiz.top_k_chunks
    client = get_client(cfg)

    query_vec = embed(query)

    search_filter = None
    if source_filter:
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        search_filter = Filter(
            must=[
                FieldCondition(
                    key="source_file",
                    match=MatchAny(any=source_filter),
                )
            ]
        )

    response = client.query_points(
        collection_name=cfg.qdrant.collection,
        query=query_vec,
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    )

    return [{**r.payload, "score": r.score} for r in response.points]
