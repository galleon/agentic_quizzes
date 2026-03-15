"""Pydantic model round-trip tests — no I/O, no LLM."""

import json

from src.common.models import Chunk, ChunkMetadata, Quiz, QuizItem


def make_chunk(**kwargs) -> Chunk:
    meta = ChunkMetadata(
        source_file="unit1.txt",
        document_title="Unit 1",
        **kwargs,
    )
    return Chunk(metadata=meta, text="Some chunk text.")


def test_chunk_metadata_required_fields():
    meta = ChunkMetadata(source_file="f.txt", document_title="T")
    assert meta.chunk_id  # uuid assigned
    assert meta.hash == ""
    assert meta.language == "en"


def test_chunk_round_trip():
    chunk = make_chunk(page_or_section="page 1", hash="abc123")
    data = chunk.model_dump()
    restored = Chunk.model_validate(data)
    assert restored.metadata.chunk_id == chunk.metadata.chunk_id
    assert restored.text == chunk.text


def test_chunk_json_round_trip():
    chunk = make_chunk()
    restored = Chunk.model_validate_json(chunk.model_dump_json())
    assert restored.metadata.source_file == "unit1.txt"


def test_chunk_embedding_optional():
    chunk = make_chunk()
    assert chunk.embedding is None
    chunk.embedding = [0.1, 0.2, 0.3]
    assert len(chunk.embedding) == 3


def make_mcq(**kwargs) -> QuizItem:
    defaults: dict = dict(
        question_type="mcq",
        question="What is X?",
        choices=["A", "B", "C", "D"],
        answer_index=0,
        rationale="Because A.",
        supporting_chunk_ids=["chunk-1"],
        source_files=["unit1.txt"],
    )
    defaults.update(kwargs)
    return QuizItem(**defaults)


def test_quiz_item_defaults():
    item = make_mcq()
    assert item.question_id  # uuid assigned
    assert item.difficulty == "medium"
    assert item.grounding_verdict == "unverified"
    assert item.confidence_flag == "low"


def test_quiz_item_round_trip():
    item = make_mcq(difficulty="hard")
    restored = QuizItem.model_validate_json(item.model_dump_json())
    assert restored.question == item.question
    assert restored.answer_index == 0
    assert restored.difficulty == "hard"


def test_quiz_round_trip():
    quiz = Quiz(
        topic="GPU monitoring",
        difficulty="medium",
        items=[make_mcq(), make_mcq(question="What is Y?")],
        model="qwen3",
    )
    data = json.loads(quiz.model_dump_json())
    assert data["topic"] == "GPU monitoring"
    assert len(data["items"]) == 2

    restored = Quiz.model_validate(data)
    assert restored.items[1].answer_index == 0


def test_true_false_item():
    item = QuizItem(
        question_type="true_false",
        question="GPUs have memory.",
        answer="True",
        rationale="They do.",
        supporting_chunk_ids=[],
        source_files=[],
    )
    assert item.choices is None
    assert item.answer_index is None
    assert item.answer == "True"
