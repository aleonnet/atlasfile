"""Unit/integration tests: autenticação por API key + escopo de projeto."""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

import app.auth as auth_module
from app.auth import AuthContext, enforce_project_scope, resolve_api_key
from app.config import settings


@pytest.fixture()
def keys_file(tmp_path, monkeypatch):
    path = tmp_path / "api_keys.json"
    path.write_text(
        json.dumps(
            {
                "keys": [
                    {"key": "atlas_sk_mcp", "name": "mcp-server", "projects": ["*"]},
                    {"key": "atlas_sk_cliente", "name": "cliente-x", "projects": ["projeto-a"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "api_keys_config_path", str(path))
    monkeypatch.setattr(auth_module, "_KEYS_CACHE", {"path": None, "mtime": None, "entries": []})
    return path


def test_resolve_api_key_matches_and_builds_scope(keys_file) -> None:
    ctx = resolve_api_key("atlas_sk_cliente")

    assert ctx is not None
    assert ctx.name == "cliente-x"
    assert ctx.allowed_projects == ("projeto-a",)
    assert not ctx.unrestricted


def test_resolve_api_key_rejects_unknown_and_empty(keys_file) -> None:
    assert resolve_api_key("atlas_sk_errada") is None
    assert resolve_api_key("") is None


def test_enforce_project_scope_allows_wildcard_and_blocks_foreign_project(keys_file) -> None:
    wildcard = resolve_api_key("atlas_sk_mcp")
    scoped = resolve_api_key("atlas_sk_cliente")
    assert wildcard is not None and scoped is not None

    enforce_project_scope(wildcard, "qualquer-projeto")  # não levanta
    enforce_project_scope(scoped, "projeto-a")  # não levanta
    enforce_project_scope(scoped, None)  # sem projeto não bloqueia

    with pytest.raises(HTTPException) as excinfo:
        enforce_project_scope(scoped, "projeto-b")
    assert excinfo.value.status_code == 403


def test_auth_disabled_everything_passes(client) -> None:
    # api_auth_enabled default False
    response = client.get("/api/projects")
    assert response.status_code == 200


def test_auth_enabled_requires_key(client, keys_file, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)

    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects", headers={"Authorization": "Bearer atlas_sk_errada"}).status_code == 401
    assert client.get("/api/projects", headers={"Authorization": "Bearer atlas_sk_mcp"}).status_code == 200
    assert client.get("/api/projects", headers={"X-API-Key": "atlas_sk_mcp"}).status_code == 200
    # api_key via query param (EventSource/links de download)
    assert client.get("/api/projects", params={"api_key": "atlas_sk_mcp"}).status_code == 200


def test_auth_enabled_health_stays_open(client, keys_file, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)

    assert client.get("/health").status_code == 200


def test_auth_enabled_project_scope_403(client, keys_file, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)

    response = client.get(
        "/api/search",
        params={"q": "contrato", "project_id": "projeto-b", "mode": "lexical"},
        headers={"Authorization": "Bearer atlas_sk_cliente"},
    )
    assert response.status_code == 403


def test_search_without_project_filters_by_allowed_projects(client, keys_file, monkeypatch) -> None:
    from unittest.mock import patch

    monkeypatch.setattr(settings, "api_auth_enabled", True)
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
        response = client.get(
            "/api/search",
            params={"q": "contrato", "mode": "lexical"},
            headers={"Authorization": "Bearer atlas_sk_cliente"},
        )
    assert response.status_code == 200
    body = mock_os.search.call_args.kwargs["body"]
    filters = body["query"]["bool"]["filter"]
    assert {"terms": {"project_id": ["projeto-a"]}} in filters
