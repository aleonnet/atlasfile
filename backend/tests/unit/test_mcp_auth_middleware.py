"""MCPAuthMiddleware isolado.

Route/Mount não herdam o ``dependencies=[Depends(require_auth)]`` do FastAPI —
o middleware é a única guarda do /mcp. Aqui ele roda na frente de um inner
ASGI fake: cada caso afirma também se o inner foi tocado, para matar tanto o
mutante "sempre passa" quanto o "sempre 401".
"""
from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import app.auth as auth_module
from app.auth import AuthContext, MCPAuthMiddleware


class _InnerApp:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        await PlainTextResponse("inner-ok")(scope, receive, send)


def _client(inner: _InnerApp) -> TestClient:
    app = Starlette(routes=[Route("/mcp", endpoint=MCPAuthMiddleware(inner))])
    return TestClient(app)


@pytest.fixture
def _auth_on(monkeypatch) -> None:
    monkeypatch.setattr(auth_module.settings, "api_auth_enabled", True, raising=False)
    monkeypatch.setattr(
        auth_module,
        "resolve_api_key",
        lambda raw: AuthContext(name="t", allowed_projects=("*",)) if raw == "atlas_sk_ok" else None,
    )


def test_auth_desligado_passa_direto(monkeypatch) -> None:
    monkeypatch.setattr(auth_module.settings, "api_auth_enabled", False, raising=False)
    inner = _InnerApp()
    r = _client(inner).post("/mcp")
    assert r.status_code == 200
    assert inner.called is True


def test_sem_key_401_e_inner_nao_e_tocado(_auth_on) -> None:
    inner = _InnerApp()
    r = _client(inner).post("/mcp")
    assert r.status_code == 401
    assert inner.called is False


def test_key_invalida_401(_auth_on) -> None:
    inner = _InnerApp()
    r = _client(inner).post("/mcp", headers={"Authorization": "Bearer atlas_sk_errada"})
    assert r.status_code == 401
    assert inner.called is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"headers": {"Authorization": "Bearer atlas_sk_ok"}},
        {"headers": {"X-API-Key": "atlas_sk_ok"}},
        {"params": {"api_key": "atlas_sk_ok"}},
    ],
    ids=["bearer", "x-api-key", "query-param"],
)
def test_key_valida_passa_pelos_tres_canais(_auth_on, kwargs) -> None:
    inner = _InnerApp()
    r = _client(inner).post("/mcp", **kwargs)
    assert r.status_code == 200
    assert inner.called is True


def test_options_passa_sem_key(_auth_on) -> None:
    # Preflight CORS nunca leva key — mesmo contrato do require_auth.
    inner = _InnerApp()
    r = _client(inner).request("OPTIONS", "/mcp")
    assert r.status_code == 200
    assert inner.called is True
