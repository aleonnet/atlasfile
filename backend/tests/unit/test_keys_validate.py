"""Unit tests do POST /api/keys/validate — validação não-impeditiva de key."""
from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException

import app.main as main_module
from app.auth import AuthContext


class _FakeAuthError(Exception):
    pass


def _fake_sdk(bad_key: str):
    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self._key = api_key

        @property
        def models(self):
            key = self._key

            class Models:
                def list(self):
                    if key == bad_key:
                        raise _FakeAuthError()
                    return []

            return Models()

    return types.SimpleNamespace(OpenAI=FakeClient, Anthropic=FakeClient, AuthenticationError=_FakeAuthError)


def test_key_valida_e_invalida_sao_resultados_nao_erros(monkeypatch) -> None:
    fake = _fake_sdk(bad_key="sk-bad")
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    auth = AuthContext(name="t", allowed_projects=("*",))

    ok = main_module.validate_provider_key(
        main_module.KeyValidateRequest(provider="openai"),
        x_openai_api_key="sk-good",
        x_anthropic_api_key=None,
        auth=auth,
    )
    assert ok == {"valid": True, "detail": "Chave OpenAI válida"}

    # Key inválida é o resultado esperado do wizard — valid False, sem exceção
    bad = main_module.validate_provider_key(
        main_module.KeyValidateRequest(provider="openai"),
        x_openai_api_key="sk-bad",
        x_anthropic_api_key=None,
        auth=auth,
    )
    assert bad["valid"] is False

    ok_ant = main_module.validate_provider_key(
        main_module.KeyValidateRequest(provider="anthropic"),
        x_openai_api_key=None,
        x_anthropic_api_key="sk-ant-good",
        auth=auth,
    )
    assert ok_ant["valid"] is True


def _fake_sdk_with_base_url(bad_key: str, seen: dict):
    """Fake que captura base_url — providers OpenAI-compatíveis (moonshot/ollama)."""
    class FakeClient:
        def __init__(self, api_key: str, base_url: str | None = None) -> None:
            self._key = api_key
            seen["api_key"] = api_key
            seen["base_url"] = base_url

        @property
        def models(self):
            key = self._key

            class Models:
                def list(self):
                    if key == bad_key:
                        raise _FakeAuthError()
                    return []

            return Models()

    return types.SimpleNamespace(OpenAI=FakeClient, Anthropic=FakeClient, AuthenticationError=_FakeAuthError)


def test_moonshot_valida_com_base_url_e_exige_header(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setitem(sys.modules, "openai", _fake_sdk_with_base_url(bad_key="sk-bad", seen=seen))
    auth = AuthContext(name="t", allowed_projects=("*",))

    ok = main_module.validate_provider_key(
        main_module.KeyValidateRequest(provider="moonshot"),
        x_openai_api_key=None,
        x_anthropic_api_key=None,
        x_moonshot_api_key="sk-moon",
        auth=auth,
    )
    assert ok == {"valid": True, "detail": "Chave Moonshot válida"}
    assert seen["api_key"] == "sk-moon"
    assert seen["base_url"] == "https://api.moonshot.ai/v1"

    bad = main_module.validate_provider_key(
        main_module.KeyValidateRequest(provider="moonshot"),
        x_openai_api_key=None,
        x_anthropic_api_key=None,
        x_moonshot_api_key="sk-bad",
        auth=auth,
    )
    assert bad["valid"] is False

    with pytest.raises(HTTPException) as exc:
        main_module.validate_provider_key(
            main_module.KeyValidateRequest(provider="moonshot"),
            x_openai_api_key=None,
            x_anthropic_api_key=None,
            x_moonshot_api_key=None,
            auth=auth,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "MOONSHOT_KEY_HEADER_REQUIRED"


def test_ollama_valida_sem_chave_com_base_url_local(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "openai", _fake_sdk_with_base_url(bad_key="never", seen=seen))
    auth = AuthContext(name="t", allowed_projects=("*",))

    ok = main_module.validate_provider_key(
        main_module.KeyValidateRequest(provider="ollama"),
        x_openai_api_key=None,
        x_anthropic_api_key=None,
        x_moonshot_api_key=None,
        auth=auth,
    )
    assert ok["valid"] is True
    # SDK openai exige api_key não-vazia mesmo sem auth no servidor
    assert seen["api_key"] == "ollama"
    assert seen["base_url"] == "http://localhost:11434/v1"


def test_sem_key_ou_provedor_desconhecido_da_400(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", _fake_sdk(bad_key="x"))
    auth = AuthContext(name="t", allowed_projects=("*",))
    with pytest.raises(HTTPException) as exc:
        main_module.validate_provider_key(
            main_module.KeyValidateRequest(provider="openai"),
            x_openai_api_key=None,
            x_anthropic_api_key=None,
            auth=auth,
        )
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        main_module.validate_provider_key(
            main_module.KeyValidateRequest(provider="cohere"),
            x_openai_api_key=None,
            x_anthropic_api_key=None,
            auth=auth,
        )
    assert exc.value.status_code == 400
