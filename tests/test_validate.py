"""Unit tests for validate_quiz confidence-flag mapping — no LLM, no Qdrant."""

from __future__ import annotations

from unittest.mock import patch

from src.common.models import Quiz, QuizItem


def _make_item(**kwargs) -> QuizItem:
    defaults = dict(
        question_type="mcq",
        question="What is X?",
        choices=["A", "B", "C", "D"],
        answer_index=0,
        rationale="Because A.",
        supporting_chunk_ids=["c1"],
        source_files=["f.txt"],
    )
    defaults.update(kwargs)
    return QuizItem(**defaults)


def _make_quiz(*items: QuizItem) -> Quiz:
    return Quiz(topic="test", difficulty="medium", items=list(items), model="test-model")


def _run_validate(quiz: Quiz, verdict_json: str) -> Quiz:
    """Run validate_quiz with mocked retrieve() and generate()."""
    with (
        patch("src.quiz.validate.retrieve", return_value=[{"chunk_id": "c1", "text": "ctx"}]),
        patch("src.quiz.validate.generate", return_value=verdict_json),
    ):
        from src.quiz.validate import validate_quiz

        return validate_quiz(quiz)


# ---------------------------------------------------------------------------
# Expected verdicts
# ---------------------------------------------------------------------------


def test_supported_sets_ok():
    quiz = _run_validate(_make_quiz(_make_item()), '{"verdict": "supported"}')
    assert quiz.items[0].grounding_verdict == "supported"
    assert quiz.items[0].confidence_flag == "ok"


def test_partial_sets_low():
    quiz = _run_validate(_make_quiz(_make_item()), '{"verdict": "partial"}')
    assert quiz.items[0].grounding_verdict == "partial"
    assert quiz.items[0].confidence_flag == "low"


def test_hallucinated_sets_rejected():
    quiz = _run_validate(_make_quiz(_make_item()), '{"verdict": "hallucinated"}')
    assert quiz.items[0].grounding_verdict == "hallucinated"
    assert quiz.items[0].confidence_flag == "rejected"


# ---------------------------------------------------------------------------
# Verdict normalisation
# ---------------------------------------------------------------------------


def test_verdict_case_insensitive():
    """Mixed-case verdict from LLM should still map correctly."""
    quiz = _run_validate(_make_quiz(_make_item()), '{"verdict": "Supported"}')
    assert quiz.items[0].grounding_verdict == "supported"
    assert quiz.items[0].confidence_flag == "ok"


def test_verdict_strips_whitespace():
    quiz = _run_validate(_make_quiz(_make_item()), '{"verdict": "  partial  "}')
    assert quiz.items[0].grounding_verdict == "partial"
    assert quiz.items[0].confidence_flag == "low"


def test_unknown_verdict_treated_as_unverified():
    quiz = _run_validate(_make_quiz(_make_item()), '{"verdict": "maybe"}')
    assert quiz.items[0].grounding_verdict == "unverified"
    assert quiz.items[0].confidence_flag == "low"


# ---------------------------------------------------------------------------
# JSON parse failures
# ---------------------------------------------------------------------------


def test_parse_failure_sets_unverified():
    quiz = _run_validate(_make_quiz(_make_item()), "not json at all")
    assert quiz.items[0].grounding_verdict == "unverified"
    assert quiz.items[0].confidence_flag == "low"


def test_missing_verdict_key_sets_unverified():
    quiz = _run_validate(_make_quiz(_make_item()), '{"reason": "looks fine"}')
    assert quiz.items[0].grounding_verdict == "unverified"
    assert quiz.items[0].confidence_flag == "low"
