"""Shared Pydantic models for chunks, quiz items, and manifests."""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


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
    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question_type: str  # mcq | short_answer | true_false
    difficulty: str = "medium"
    question: str
    choices: Optional[list[str]] = None  # MCQ only; 4 options
    answer_index: Optional[int] = None  # MCQ: 0-3
    answer: Optional[str] = None  # short_answer / true_false
    rationale: str = ""
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    grounding_verdict: str = "unverified"  # supported | partial | hallucinated | unverified
    confidence_flag: str = "ok"  # ok | low | rejected


class Quiz(BaseModel):
    quiz_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    source_scope: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    items: list[QuizItem] = Field(default_factory=list)
    generated_at: str = ""
    model: str = ""
