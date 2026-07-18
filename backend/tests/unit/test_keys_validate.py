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
