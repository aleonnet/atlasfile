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


def test_ollama_usa_janela_real_do_api_show(monkeypatch):
    """v0.47.0: custom Ollama consulta /api/show (fato medido: gemma4:12b tem
    262144 — o dobro do fallback de 128k que o medidor usava)."""
    from app import llm_catalog

    monkeypatch.setitem(llm_catalog._OLLAMA_CONTEXT_CACHE, "gemma4:12b", 262144)
    assert get_context_tokens("ollama", "gemma4:12b") == 262144


def test_ollama_fora_do_ar_cai_no_fallback_e_cacheia_a_falha(monkeypatch):
    from app import llm_catalog

    llm_catalog._OLLAMA_CONTEXT_CACHE.clear()
    calls = {"n": 0}

    class _Boom:
        @staticmethod
        def post(*_a, **_k):
            calls["n"] += 1
            raise ConnectionError("down")

    monkeypatch.setattr("httpx.post", _Boom.post)
    assert get_context_tokens("ollama", "modelo-x") == _FALLBACK_CONTEXT_TOKENS
    assert get_context_tokens("ollama", "modelo-x") == _FALLBACK_CONTEXT_TOKENS
    assert calls["n"] == 1  # falha cacheada: sem tempestade de consultas
    llm_catalog._OLLAMA_CONTEXT_CACHE.clear()
