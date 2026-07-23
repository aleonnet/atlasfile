"""Unit tests do registro central de providers (llm_providers.py)."""
from __future__ import annotations

from unittest.mock import patch

from app.config import settings
from app.llm_providers import PROVIDERS, get_provider, make_async_client, resolve_api_key, resolve_base_url


def test_registro_tem_os_quatro_providers_com_sdk_correto() -> None:
    assert set(PROVIDERS) == {"openai", "anthropic", "moonshot", "ollama"}
    assert PROVIDERS["anthropic"].sdk_flavor == "anthropic"
    assert all(PROVIDERS[p].sdk_flavor == "openai" for p in ("openai", "moonshot", "ollama"))
    assert PROVIDERS["ollama"].requires_key is False
    assert get_provider("MoonShot ") is PROVIDERS["moonshot"]
    assert get_provider("cohere") is None


def test_openai_anthropic_sem_base_url_e_chave_transiente_ou_none() -> None:
    # Contrato histórico: sem base_url; sem transiente → None (SDK cai no env)
    assert resolve_base_url(PROVIDERS["openai"]) is None
    assert resolve_base_url(PROVIDERS["anthropic"]) is None
    assert resolve_api_key(PROVIDERS["openai"], "sk-x") == "sk-x"
    assert resolve_api_key(PROVIDERS["openai"], None) is None


def test_factory_openai_nao_passa_base_url() -> None:
    with patch("openai.AsyncOpenAI") as mock_client:
        make_async_client("openai", "sk-x")
    mock_client.assert_called_once_with(api_key="sk-x")


def test_factory_moonshot_passa_base_url_de_settings(monkeypatch) -> None:
    with patch("openai.AsyncOpenAI") as mock_client:
        make_async_client("moonshot", "sk-moon")
    mock_client.assert_called_once_with(api_key="sk-moon", base_url="https://api.moonshot.ai/v1")

    monkeypatch.setattr(settings, "moonshot_base_url", "https://proxy.example/v1")
    with patch("openai.AsyncOpenAI") as mock_client:
        make_async_client("moonshot", "sk-moon")
    mock_client.assert_called_once_with(api_key="sk-moon", base_url="https://proxy.example/v1")


def test_factory_ollama_sem_chave_usa_placeholder_e_base_local(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    with patch("openai.AsyncOpenAI") as mock_client:
        make_async_client("ollama", None)
    mock_client.assert_called_once_with(api_key="ollama", base_url="http://localhost:11434/v1")


def test_resolve_api_key_prioriza_transiente_depois_env(monkeypatch) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-env")
    assert resolve_api_key(PROVIDERS["moonshot"], "sk-header") == "sk-header"
    assert resolve_api_key(PROVIDERS["moonshot"], None) == "sk-env"
    monkeypatch.delenv("MOONSHOT_API_KEY")
    assert resolve_api_key(PROVIDERS["moonshot"], None) is None
