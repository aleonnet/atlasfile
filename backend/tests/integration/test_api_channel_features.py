"""Integration tests for new channel/usage features added in the usage+channel plan."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.channels.base import ChannelMessage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/chat/sessions?channel=...
# ---------------------------------------------------------------------------

def test_list_sessions_channel_filter_adds_term(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
        r = client.get("/api/chat/sessions", params={"channel": "telegram"})
    assert r.status_code == 200
    call_body = mock_os.search.call_args[1]["body"]
    must_clauses = call_body["query"]["bool"]["must"]
    term_clause = next(c for c in must_clauses if "term" in c)
    assert term_clause["term"]["channel"] == "telegram"


def test_list_sessions_no_channel_uses_match_all(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
        r = client.get("/api/chat/sessions")
    assert r.status_code == 200
    call_body = mock_os.search.call_args[1]["body"]
    assert "match_all" in call_body["query"]


# ---------------------------------------------------------------------------
# POST /api/chat/sessions with channel fields
# ---------------------------------------------------------------------------

def test_create_session_with_channel(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os, \
         patch("app.main.uuid") as mock_uuid:
        fake_uuid = MagicMock()
        fake_uuid.hex = "chan123"
        mock_uuid.uuid4.return_value = fake_uuid
        r = client.post(
            "/api/chat/sessions",
            json={
                "title": "Sessao Telegram",
                "messages": [{"role": "user", "content": "Oi", "timestamp": 1000}],
                "model": "openai/gpt-4o-mini",
                "channel": "telegram",
                "channel_chat_id": "tg-456",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data["channel"] == "telegram"
    assert data["channel_chat_id"] == "tg-456"
    indexed_body = mock_os.index.call_args[1]["body"]
    assert indexed_body["channel"] == "telegram"
    assert indexed_body["channel_chat_id"] == "tg-456"


def test_create_session_defaults_to_web(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os, \
         patch("app.main.uuid") as mock_uuid:
        fake_uuid = MagicMock()
        fake_uuid.hex = "web123"
        mock_uuid.uuid4.return_value = fake_uuid
        r = client.post(
            "/api/chat/sessions",
            json={
                "title": "Sessao Web",
                "messages": [{"role": "user", "content": "Hello", "timestamp": 2000}],
                "model": "openai/gpt-4o-mini",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data["channel"] == "web"
    assert data.get("channel_chat_id") is None


@pytest.mark.asyncio
async def test_handle_channel_message_uses_explicit_project_scope() -> None:
    from app.main import _clear_channel_project_scope, _handle_channel_message, _set_channel_project_scope

    message = ChannelMessage(
        channel_id="telegram",
        sender_id="user-1",
        sender_name="User",
        chat_id="tg-123",
        text="Buscar documento",
    )
    _set_channel_project_scope("telegram", "tg-123", "proj-scope")
    try:
        with patch("app.main.get_llm_config", return_value=("openai", "gpt-4o-mini")), \
             patch("app.main._find_active_channel_session", return_value=None), \
             patch("app.main.run_chat_loop", new_callable=AsyncMock, return_value={"content": "ok", "usage": {}}) as mock_loop, \
             patch("app.main.os_client") as mock_os:
            reply = await _handle_channel_message(message)
    finally:
        _clear_channel_project_scope("telegram", "tg-123")

    assert reply == "ok"
    assert mock_loop.await_args.kwargs["project_id"] == "proj-scope"
    indexed_body = mock_os.index.call_args.kwargs["body"]
    assert indexed_body["project_id"] == "proj-scope"


# ---------------------------------------------------------------------------
# GET /api/chat/sessions returns channel fields
# ---------------------------------------------------------------------------

def test_list_sessions_returns_channel_fields(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "sess-tg-1",
                        "_source": {
                            "title": "Via Telegram",
                            "messages": [{"role": "user", "content": "Oi", "timestamp": 1000}],
                            "model": "openai/gpt-4o-mini",
                            "createdAt": 1000,
                            "updatedAt": 2000,
                            "channel": "telegram",
                            "channel_chat_id": "tg-789",
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
    assert data[0]["channel"] == "telegram"
    assert data[0]["channel_chat_id"] == "tg-789"


def test_list_sessions_missing_channel_returns_none(client: TestClient) -> None:
    """Sessions without channel field return null (not masked as 'web')."""
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "sess-old-1",
                        "_source": {
                            "title": "Legacy session",
                            "messages": [],
                            "model": "openai/gpt-4o-mini",
                            "createdAt": 500,
                            "updatedAt": 600,
                        },
                    }
                ],
                "total": {"value": 1},
            }
        }
        r = client.get("/api/chat/sessions")
    data = r.json()
    assert data[0]["channel"] is None
    assert data[0].get("channel_chat_id") is None


# ---------------------------------------------------------------------------
# GET /api/usage/sessions?channel=...
# ---------------------------------------------------------------------------

def test_usage_sessions_channel_filter(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
        r = client.get(
            "/api/usage/sessions",
            params={"start_date": "2025-01-01", "end_date": "2025-12-31", "channel": "web"},
        )
    assert r.status_code == 200
    call_body = mock_os.search.call_args[1]["body"]
    must = call_body["query"]["bool"]["must"]
    term = next(c for c in must if "term" in c)
    assert term["term"]["channel"] == "web"


def test_usage_sessions_returns_channel(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "s1",
                        "_source": {
                            "title": "Tg session",
                            "model": "openai/gpt-4o-mini",
                            "updatedAt": 1700000000000,
                            "channel": "telegram",
                        },
                    }
                ],
                "total": {"value": 1},
            }
        }
        r = client.get(
            "/api/usage/sessions",
            params={"start_date": "2020-01-01", "end_date": "2030-12-31"},
        )
    data = r.json()
    assert data[0]["channel"] == "telegram"


# ---------------------------------------------------------------------------
# GET /api/usage/summary?channel=...
# ---------------------------------------------------------------------------

def test_usage_summary_channel_filter(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
        r = client.get(
            "/api/usage/summary",
            params={"start_date": "2025-01-01", "end_date": "2025-12-31", "channel": "telegram"},
        )
    assert r.status_code == 200
    call_body = mock_os.search.call_args[1]["body"]
    must = call_body["query"]["bool"]["must"]
    term = next(c for c in must if "term" in c)
    assert term["term"]["channel"] == "telegram"


# ---------------------------------------------------------------------------
# GET /api/usage/classification
# ---------------------------------------------------------------------------

def test_classification_usage_endpoint_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {
            "aggregations": {
                "total_calls": {"value": 5},
                "total_input": {"value": 10000},
                "total_output": {"value": 2000},
                "total_cost": {"value": 0.05},
                "by_model": {
                    "buckets": [
                        {
                            "key": "gpt-4o-mini",
                            "doc_count": 3,
                            "input_tokens": {"value": 6000},
                            "output_tokens": {"value": 1200},
                            "cost": {"value": 0.03},
                        },
                        {
                            "key": "claude-haiku-4-5",
                            "doc_count": 2,
                            "input_tokens": {"value": 4000},
                            "output_tokens": {"value": 800},
                            "cost": {"value": 0.02},
                        },
                    ]
                },
            }
        }
        r = client.get(
            "/api/usage/classification",
            params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["total_calls"] == 5
    assert data["total_input_tokens"] == 10000
    assert data["total_output_tokens"] == 2000
    assert data["estimated_cost_usd"] == 0.05
    assert len(data["by_model"]) == 2
    gpt = next(m for m in data["by_model"] if m["model"] == "gpt-4o-mini")
    assert gpt["call_count"] == 3
    assert gpt["input_tokens"] == 6000


def test_classification_usage_with_project_filter(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {
            "aggregations": {
                "total_calls": {"value": 0},
                "total_input": {"value": 0},
                "total_output": {"value": 0},
                "total_cost": {"value": 0},
                "by_model": {"buckets": []},
            }
        }
        r = client.get(
            "/api/usage/classification",
            params={"start_date": "2025-01-01", "end_date": "2025-12-31", "project_id": "proj-x"},
        )
    assert r.status_code == 200
    call_body = mock_os.search.call_args[1]["body"]
    must = call_body["query"]["bool"]["must"]
    term = next(c for c in must if "term" in c)
    assert term["term"]["project_id"] == "proj-x"


def test_classification_usage_invalid_dates(client: TestClient) -> None:
    r = client.get(
        "/api/usage/classification",
        params={"start_date": "not-a-date", "end_date": "2025-12-31"},
    )
    assert r.status_code == 400


def test_classification_usage_empty(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {
            "aggregations": {
                "total_calls": {"value": 0},
                "total_input": {"value": 0},
                "total_output": {"value": 0},
                "total_cost": {"value": 0},
                "by_model": {"buckets": []},
            }
        }
        r = client.get(
            "/api/usage/classification",
            params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
        )
    data = r.json()
    assert data["total_calls"] == 0
    assert data["by_model"] == []
