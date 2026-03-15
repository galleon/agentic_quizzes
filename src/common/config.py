"""Load and expose nanoclaw/config/settings.yaml as a typed config object."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class OllamaOptions(BaseModel):
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 20
    num_predict: int = 4096
    repeat_penalty: float = 1.1
    think: bool = False


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    generation_model: str = "qwen2.5:instruct"
    embedding_model: str = "nomic-embed-text"
    generation_options: OllamaOptions = Field(default_factory=OllamaOptions)


class QdrantConfig(BaseModel):
    mode: Literal["local", "server"] = "local"
    local_path: str = "vectorstore/qdrant"
    server_url: str = "http://localhost:6333"
    collection: str = "quiz_rag"
    vector_size: int = 768


class IngestConfig(BaseModel):
    raw_dir: str = "data/raw"
    extracted_dir: str = "data/extracted"
    cleaned_dir: str = "data/cleaned"
    chunks_dir: str = "data/chunks"
    metadata_dir: str = "data/metadata"
    manifest_file: str = "data/metadata/manifest.jsonl"
    supported_extensions: list[str] = Field(
        default_factory=lambda: [".pdf", ".html", ".md", ".txt"]
    )
    chunk_size: int = 512
    chunk_overlap: int = 64


class QuizConfig(BaseModel):
    outputs_dir: str = "outputs"
    quizzes_dir: str = "outputs/quizzes"
    answer_keys_dir: str = "outputs/answer_keys"
    rationales_dir: str = "outputs/rationales"
    reports_dir: str = "outputs/reports"
    default_num_questions: int = 10
    default_difficulty: Literal["easy", "medium", "hard"] = "medium"
    default_question_types: list[Literal["mcq", "short_answer", "true_false"]] = Field(
        default_factory=lambda: ["mcq", "short_answer", "true_false"]
    )
    top_k_chunks: int = 6


class Settings(BaseModel):
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    quiz: QuizConfig = Field(default_factory=QuizConfig)


def _find_project_root() -> Path:
    """Walk up from CWD to find the directory containing nanoclaw/config/settings.yaml.

    The search can be bypassed by setting the ``NANOCLAW_ROOT`` environment
    variable to the absolute path of the project root.
    """
    env_root = os.environ.get("NANOCLAW_ROOT")
    if env_root:
        return Path(env_root)
    candidate = Path(os.getcwd())
    for _ in range(6):
        if (candidate / "nanoclaw" / "config" / "settings.yaml").exists():
            return candidate
        candidate = candidate.parent
    return Path(os.getcwd())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = _find_project_root()
    config_path = root / "nanoclaw" / "config" / "settings.yaml"
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return Settings.model_validate(data or {})
    import warnings

    warnings.warn(
        f"nanoclaw config not found at {config_path}; using built-in defaults. "
        "Set NANOCLAW_ROOT to the project root to fix this.",
        stacklevel=2,
    )
    return Settings()


def project_root() -> Path:
    return _find_project_root()
