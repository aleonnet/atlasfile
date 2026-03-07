"""Integration tests for the /api/channels/* endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------- GET /api/channels/config ----------

def test_get_channel_config_default(client: TestClient) -> None:
    r = client.get("/api/channels/config")
    assert r.status_code == 200
    data = r.json()
    assert "channels_enabled" in data
    assert "telegram" in data
    assert "enabled" in data["telegram"]
    assert "bot_token" in data["telegram"]


# ---------- PUT /api/channels/config ----------

def test_update_channel_config(client: TestClient) -> None:
    payload = {
        "channels_enabled": False,
        "telegram": {"enabled": False, "bot_token": ""},
    }
    r = client.put("/api/channels/config", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["channels_enabled"] is False
    assert data["telegram"]["enabled"] is False


# ---------- GET /api/channels/status ----------

def test_get_channel_status_disabled(client: TestClient) -> None:
    r = client.get("/api/channels/status")
    assert r.status_code == 200
    data = r.json()
    assert "channels_enabled" in data
    assert "channels" in data
    assert isinstance(data["channels"], list)
    assert len(data["channels"]) >= 1
    tg = next((c for c in data["channels"] if c["channel_id"] == "telegram"), None)
    assert tg is not None
    assert tg["running"] is False


# ---------- POST /api/channels/test ----------

def test_test_channel_not_running(client: TestClient) -> None:
    r = client.post("/api/channels/test?channel_id=telegram")
    assert r.status_code == 400


def test_test_channel_unknown(client: TestClient) -> None:
    r = client.post("/api/channels/test?channel_id=nonexistent")
    assert r.status_code in (400, 404)
