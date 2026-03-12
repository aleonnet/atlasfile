"""Unit tests for get_context_tokens from llm_catalog."""
from __future__ import annotations

from app.llm_catalog import get_context_tokens, _FALLBACK_CONTEXT_TOKENS


def test_known_openai_model():
    assert get_context_tokens("openai", "gpt-4o-mini") == 128_000


def test_known_openai_large_model():
    assert get_context_tokens("openai", "gpt-4.1") == 1_047_576


def test_known_anthropic_model():
    assert get_context_tokens("anthropic", "claude-haiku-4-5") == 200_000


def test_unknown_model_returns_fallback():
    assert get_context_tokens("openai", "nonexistent-model") == _FALLBACK_CONTEXT_TOKENS


def test_unknown_provider_returns_fallback():
    assert get_context_tokens("unknown", "gpt-4o-mini") == _FALLBACK_CONTEXT_TOKENS
