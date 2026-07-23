"""Unit tests do POST /api/models/validate — cobre os 4 providers do registro.
Lacuna pré-existente: o endpoint não tinha teste algum (branches NotFound/Auth/rede)."""
from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException

import app.main as main_module
from app.auth import AuthContext

AUTH = AuthContext(name="t", allowed_projects=("*",))


class _FakeAuthError(Exception):
    pass


class _FakeNotFoundError(Exception):
    pass


def _fake_sdk(*, bad_key: str = "sk-bad", missing_model: str = "no-such-model", seen: dict | None = None):
    captured = seen if seen is not None else {}

    class FakeClient:
        def __init__(self, api_key: str, base_url: str | None = None) -> None:
            self._key = api_key
            captured["api_key"] = api_key
            captured["base_url"] = base_url

        @property
        def models(self):
            key = self._key

            class Models:
                def retrieve(self, model: str):
                    if key == bad_key:
                        raise _FakeAuthError()
                    if model == missing_model:
                        raise _FakeNotFoundError()
                    return {"id": model}

            return Models()

    return types.SimpleNamespace(
        OpenAI=FakeClient,
        Anthropic=FakeClient,
        AuthenticationError=_FakeAuthError,
        NotFoundError=_FakeNotFoundError,
    )


def _call(provider: str, model: str, *, openai_key=None, anthropic_key=None, moonshot_key=None):
    return main_module.validate_model(
        main_module.ModelValidateRequest(provider=provider, model=model),
        x_openai_api_key=openai_key,
        x_anthropic_api_key=anthropic_key,
        x_moonshot_api_key=moonshot_key,
        auth=AUTH,
    )


def test_openai_modelo_existente_inexistente_e_chave_invalida(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", _fake_sdk())

    ok = _call("openai", "gpt-4o-mini", openai_key="sk-good")
    assert ok == {"valid": True, "detail": "Modelo 'gpt-4o-mini' disponível na OpenAI"}

    missing = _call("openai", "no-such-model", openai_key="sk-good")
    assert missing["valid"] is False

    with pytest.raises(HTTPException) as exc:
        _call("openai", "gpt-4o-mini", openai_key="sk-bad")
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "OPENAI_KEY_INVALID"


def test_sem_chave_da_400_com_codigo_do_provider(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", _fake_sdk())
    with pytest.raises(HTTPException) as exc:
        _call("openai", "gpt-4o-mini")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "OPENAI_KEY_NOT_CONFIGURED"

    with pytest.raises(HTTPException) as exc:
        _call("moonshot", "kimi-k3")
    assert exc.value.detail["code"] == "MOONSHOT_KEY_NOT_CONFIGURED"


def test_moonshot_usa_base_url_e_valida_modelo(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setitem(sys.modules, "openai", _fake_sdk(seen=seen))
    ok = _call("moonshot", "kimi-k3", moonshot_key="sk-moon")
    assert ok["valid"] is True
    assert seen["base_url"] == "https://api.moonshot.ai/v1"

    with pytest.raises(HTTPException) as exc:
        _call("moonshot", "kimi-k3", moonshot_key="sk-bad")
    assert exc.value.detail["code"] == "MOONSHOT_KEY_INVALID"


def test_ollama_valida_modelo_local_sem_chave(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "openai", _fake_sdk(seen=seen))

    ok = _call("ollama", "gemma4:12b")
    assert ok["valid"] is True
    assert seen["api_key"] == "ollama"
    assert seen["base_url"] == "http://localhost:11434/v1"

    missing = _call("ollama", "no-such-model")
    assert missing["valid"] is False


def test_provider_desconhecido_e_modelo_vazio(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", _fake_sdk())
    with pytest.raises(HTTPException) as exc:
        _call("cohere", "command-r")
    assert exc.value.detail["code"] == "PROVIDER_UNSUPPORTED"
    with pytest.raises(HTTPException) as exc:
        _call("openai", "   ", openai_key="sk-good")
    assert exc.value.detail["code"] == "MODEL_NAME_REQUIRED"
