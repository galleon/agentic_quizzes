"""Shared Pydantic models for chunks, quiz items, and manifests."""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChunkMetadata(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str
    document_title: str
    page_or_section: str = ""
    document_date: str = ""
    topic_tags: list[str] = Field(default_factory=list)
    language: str = "en"
    hash: str = ""


class Chunk(BaseModel):
    metadata: ChunkMetadata
    text: str
    embedding: Optional[list[float]] = None


class QuizItem(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question_type: Literal["mcq", "short_answer", "true_false"]
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    question: str
    choices: Optional[list[str]] = None  # MCQ only; 4 options
    answer_index: Optional[int] = None  # MCQ: 0-3
    answer: Optional[str] = None  # short_answer / true_false
    rationale: str = ""
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    grounding_verdict: Literal["supported", "partial", "hallucinated", "unverified"] = "unverified"
    confidence_flag: Literal["ok", "low", "rejected"] = "low"


class Quiz(BaseModel):
    quiz_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    source_scope: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    items: list[QuizItem] = Field(default_factory=list)
    generated_at: str = ""
    model: str = ""
