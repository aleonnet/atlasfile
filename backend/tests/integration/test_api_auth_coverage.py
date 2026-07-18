"""Cobertura de autenticação: com API_AUTH_ENABLED, endpoints exigem key
(header Bearer ou ?api_key= para streams); /health permanece público."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

import app.auth as auth_module
from app.auth import AuthContext
from app.main import app


@pytest.fixture
def authed_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(auth_module.settings, "api_auth_enabled", True, raising=False)
    monkeypatch.setattr(
        auth_module,
        "resolve_api_key",
        lambda raw: AuthContext(name="teste", allowed_projects=("*",)) if raw == "atlas_sk_teste" else None,
    )
    return TestClient(app)


def test_health_stays_public(authed_client: TestClient) -> None:
    assert authed_client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/setup/status"),
        ("GET", "/api/projects"),
        ("GET", "/api/templates"),
        ("GET", "/api/models"),
        ("GET", "/api/models/detail"),
        ("GET", "/api/models/catalog-config"),
        ("GET", "/api/classifier/datasets/readiness"),
        ("GET", "/api/classifier/cycle/status"),
        ("GET", "/api/chat/sessions"),
        ("GET", "/api/usage/summary"),
        ("GET", "/api/tags"),
        ("POST", "/api/classifier/cycle"),
        ("POST", "/api/reconcile"),
    ],
)
def test_endpoints_require_key(authed_client: TestClient, method: str, path: str) -> None:
    response = authed_client.request(method, path)
    assert response.status_code == 401, f"{method} {path} deveria exigir key"


def test_setup_status_accepts_valid_key(authed_client: TestClient) -> None:
    with patch("app.main.list_project_roots", return_value=[]):
        ok = authed_client.get("/api/setup/status", headers={"Authorization": "Bearer atlas_sk_teste"})
    assert ok.status_code == 200
    bad = authed_client.get("/api/setup/status", headers={"Authorization": "Bearer atlas_sk_errada"})
    assert bad.status_code == 401


def test_stream_endpoint_accepts_api_key_query_param(authed_client: TestClient) -> None:
    # EventSource não envia headers — streams autenticam via ?api_key=
    no_key = authed_client.get("/api/ingest/status")
    assert no_key.status_code == 401
    with_param = authed_client.get("/api/ingest/status?api_key=atlas_sk_teste")
    assert with_param.status_code == 200
