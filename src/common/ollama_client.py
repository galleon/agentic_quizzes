"""Thin wrapper around the Ollama Python client with verbosity controls."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

import ollama

from src.common.config import get_settings


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks that Qwen3 may emit even with think=False."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


@lru_cache(maxsize=1)
def _client() -> ollama.Client:
    """Return a cached Ollama client pointed at the configured base_url."""
    return ollama.Client(host=get_settings().ollama.base_url)


def generate(
    prompt: str,
    system: str = "",
    model: str | None = None,
    extra_options: dict[str, Any] | None = None,
) -> str:
    """Call the Ollama generation model and return cleaned response text."""
    cfg = get_settings().ollama
    model = model or cfg.generation_model
    opts = cfg.generation_options.model_dump()
    if extra_options:
        opts.update(extra_options)

    # `think` is a top-level Ollama API parameter for Qwen3, not inside options.
    # Remove it from options and pass separately so both Qwen2.5 and Qwen3 work.
    think = opts.pop("think", False)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    call_kwargs: dict[str, Any] = dict(model=model, messages=messages, options=opts)
    # Only pass `think` for Qwen3 models — Qwen2.5 ignores unknown kwargs gracefully,
    # but some Ollama versions may error. Guard by checking model name.
    if "qwen3" in model.lower():
        call_kwargs["think"] = think

    try:
        response = _client().chat(**call_kwargs)
    except TypeError as exc:
        # Older ollama clients (< 0.4.4) don't accept the `think` kwarg.
        # Only swallow the error when `think` was actually passed and the
        # message points to an unexpected keyword argument; re-raise otherwise
        # so genuine programming errors are not masked.
        if "think" not in call_kwargs or "unexpected keyword argument" not in str(exc):
            raise
        call_kwargs.pop("think")
        response = _client().chat(**call_kwargs)
    content = response["message"]["content"]
    return _strip_think_tags(content)


def embed(text: str, model: str | None = None) -> list[float]:
    """Compute an embedding vector for the given text."""
    cfg = get_settings().ollama
    model = model or cfg.embedding_model
    response = _client().embeddings(model=model, prompt=text)
    return response["embedding"]


def embed_batch(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Compute embeddings for a list of texts."""
    return [embed(t, model=model) for t in texts]


def parse_json_response(raw: str) -> Any:
    """Extract the first JSON object or array from a model response."""
    raw = _strip_think_tags(raw)
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try to find JSON block inside markdown fences
    fence_match = re.search(r"```(?:json)?\s*([\[\{].*?)```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: use raw_decode to extract the first JSON value even with trailing text
    decoder = json.JSONDecoder()
    for start_char in ("[", "{"):
        idx = raw.find(start_char)
        if idx != -1:
            try:
                obj, _ = decoder.raw_decode(raw, idx)
                return obj
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Could not parse JSON from model response:\n{raw[:400]}")
