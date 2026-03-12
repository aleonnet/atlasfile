"""Integration tests: GET/POST/PATCH/DELETE /api/chat/sessions with mocked OpenSearch."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_list_chat_sessions_empty(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
        r = client.get("/api/chat/sessions")
    assert r.status_code == 200
    assert r.json() == []


def test_list_chat_sessions_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "sess-1",
                        "_source": {
                            "title": "Minha sessão",
                            "messages": [{"role": "user", "content": "Oi", "timestamp": 1000}],
                            "model": "openai/gpt-4o-mini",
                            "createdAt": 1000,
                            "updatedAt": 2000,
                        },
                    }
                ],
                "total": {"value": 1},
            }
        }
        r = client.get("/api/chat/sessions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "sess-1"
    assert data[0]["title"] == "Minha sessão"
    assert data[0]["model"] == "openai/gpt-4o-mini"
    assert data[0]["messages"][0]["role"] == "user"
    assert data[0]["messages"][0]["content"] == "Oi"


def test_list_chat_sessions_with_query(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
        r = client.get("/api/chat/sessions", params={"q": "contrato"})
    assert r.status_code == 200
    mock_os.search.assert_called_once()
    call_body = mock_os.search.call_args[1]["body"]
    assert "query" in call_body
    must_clauses = call_body["query"]["bool"]["must"]
    sq = next(c for c in must_clauses if "simple_query_string" in c)
    assert sq["simple_query_string"]["query"] == "contrato"


def test_get_chat_session_404(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.get.side_effect = Exception("not found")
        r = client.get("/api/chat/sessions/inexistente")
    assert r.status_code == 404
    assert "sessão" in r.json().get("detail", "").lower()


def test_get_chat_session_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.get.return_value = {
            "_source": {
                "title": "Sessão única",
                "messages": [
                    {"role": "user", "content": "Olá", "timestamp": 1000},
                    {"role": "assistant", "content": "Oi!", "timestamp": 1001},
                ],
                "model": "anthropic/claude-sonnet-4-6",
                "createdAt": 1000,
                "updatedAt": 1001,
            }
        }
        r = client.get("/api/chat/sessions/sess-123")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "sess-123"
    assert data["title"] == "Sessão única"
    assert len(data["messages"]) == 2
    assert data["messages"][1]["content"] == "Oi!"


def test_create_chat_session_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        with patch("app.main.uuid") as mock_uuid:
            fake_uuid = MagicMock()
            fake_uuid.hex = "abc123def456"
            mock_uuid.uuid4.return_value = fake_uuid
            r = client.post(
                "/api/chat/sessions",
                json={
                    "title": "Nova conversa",
                    "messages": [
                        {"role": "user", "content": "Teste", "timestamp": 1000},
                    ],
                    "model": "openai/gpt-4o-mini",
                },
            )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "abc123def456"
    assert data["title"] == "Nova conversa"
    assert data["model"] == "openai/gpt-4o-mini"
    assert len(data["messages"]) == 1
    assert data["createdAt"] == data["updatedAt"]
    mock_os.index.assert_called_once()
    call_kw = mock_os.index.call_args[1]
    assert call_kw["id"] == "abc123def456"
    assert call_kw["body"]["title"] == "Nova conversa"


def test_update_chat_session_404(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.update.side_effect = Exception("not found")
        r = client.patch(
            "/api/chat/sessions/inexistente",
            json={"title": "Novo título"},
        )
    assert r.status_code == 404


def test_update_chat_session_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.update.return_value = {"result": "updated"}
        mock_os.get.return_value = {
            "_source": {
                "title": "Título atualizado",
                "messages": [{"role": "user", "content": "Oi"}],
                "model": "openai/gpt-4o-mini",
                "createdAt": 1000,
                "updatedAt": 2000,
            }
        }
        r = client.patch(
            "/api/chat/sessions/sess-1",
            json={"title": "Título atualizado"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Título atualizado"
    mock_os.update.assert_called_once()
    update_body = mock_os.update.call_args[1]["body"]["doc"]
    assert update_body["title"] == "Título atualizado"
    assert "updatedAt" in update_body


def test_delete_chat_session_404(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.delete.side_effect = Exception("not found")
        r = client.delete("/api/chat/sessions/inexistente")
    assert r.status_code == 404


def test_delete_chat_session_204(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        r = client.delete("/api/chat/sessions/sess-1")
    assert r.status_code == 204
    assert r.content == b""
    mock_os.delete.assert_called_once()
    assert mock_os.delete.call_args[1]["id"] == "sess-1"
