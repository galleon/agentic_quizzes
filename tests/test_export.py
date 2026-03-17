"""Unit tests for quiz export functions."""

from __future__ import annotations

from src.common.config import ExamInfoConfig
from src.common.models import Quiz, QuizItem
from src.quiz.export import to_gradio


def _make_item(**kwargs) -> QuizItem:
    defaults = dict(
        question_type="mcq",
        question="What is X?",
        choices=["Alpha", "Beta", "Gamma", "Delta"],
        answer_index=1,
        rationale="Because Beta.",
        supporting_chunk_ids=["c1"],
        source_files=["f.pdf"],
        confidence_flag="ok",
        grounding_verdict="supported",
    )
    defaults.update(kwargs)
    return QuizItem(**defaults)


def _make_quiz(*items: QuizItem, topic: str = "GPU Monitoring") -> Quiz:
    return Quiz(topic=topic, items=list(items))


def test_to_gradio_field_mapping():
    quiz = _make_quiz(_make_item())
    result = to_gradio(quiz)

    q = result["questions"][0]
    assert q["options"] == ["Alpha", "Beta", "Gamma", "Delta"]
    # answer_index=1 (0-based) → correct_answer=2 (1-based)
    assert q["correct_answer"] == 2
    assert q["explanation"] == "Because Beta."
    assert q["section"] == "GPU Monitoring"


def test_to_gradio_excludes_rejected():
    accepted = _make_item(question="Q1", answer_index=0, confidence_flag="ok")
    rejected = _make_item(question="Q2", answer_index=0, confidence_flag="rejected")
    result = to_gradio(_make_quiz(accepted, rejected))

    assert len(result["questions"]) == 1
    assert result["questions"][0]["question"] == "Q1"


def test_to_gradio_excludes_non_mcq():
    mcq = _make_item(question_type="mcq", question="MCQ?", answer_index=0)
    sa = QuizItem(
        question_type="short_answer",
        question="SA?",
        answer="yes",
        confidence_flag="ok",
    )
    result = to_gradio(_make_quiz(mcq, sa))

    assert len(result["questions"]) == 1
    assert result["questions"][0]["question"] == "MCQ?"


def test_to_gradio_excludes_out_of_bounds_answer_index():
    bad = _make_item(answer_index=10)  # out of bounds for 4-choice list
    result = to_gradio(_make_quiz(bad))

    assert result["questions"] == []


def test_to_gradio_exam_info_from_overrides():
    exam_cfg = ExamInfoConfig(
        title="My Exam",
        certifications=["CERT-X"],
        time_limit_minutes=45,
        passing_score=80,
    )
    quiz = _make_quiz(_make_item())
    result = to_gradio(quiz, exam_info_overrides=exam_cfg)

    info = result["exam_info"]
    assert info["title"] == "My Exam"
    assert info["certifications"] == ["CERT-X"]
    assert info["time_limit_minutes"] == 45
    assert info["passing_score"] == 80
    assert info["total_questions"] == 1


def test_to_gradio_ids_are_one_indexed():
    items = [_make_item(question=f"Q{i}", answer_index=0) for i in range(3)]
    result = to_gradio(_make_quiz(*items))

    ids = [q["id"] for q in result["questions"]]
    assert ids == [1, 2, 3]


def test_to_gradio_empty_quiz():
    result = to_gradio(_make_quiz())
    assert result["questions"] == []
    assert result["exam_info"]["total_questions"] == 0
