"""Integration tests: GET /api/models, POST /api/chat, POST /api/classify (mocked orchestrator)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_models_200(client: TestClient) -> None:
    """GET /api/models returns list of provider/model options."""
    r = client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    for item in data:
        assert "provider" in item and "model" in item and "label" in item


def test_post_chat_200_with_mock(client: TestClient) -> None:
    """POST /api/chat returns content when run_chat_loop is mocked."""
    async def fake_run_chat_loop(*args, **kwargs):
        return {"content": "Mocked reply", "tool_calls_used": []}

    with patch("app.main.run_chat_loop", new_callable=AsyncMock, side_effect=fake_run_chat_loop):
        r = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["content"] == "Mocked reply"
    assert data["tool_calls_used"] == []


def test_post_chat_passes_project_id_to_orchestrator(client: TestClient) -> None:
    async def fake_run_chat_loop(*args, **kwargs):
        assert kwargs["project_id"] == "proj-chat"
        return {"content": "Scoped reply", "tool_calls_used": []}

    with patch("app.main.run_chat_loop", new_callable=AsyncMock, side_effect=fake_run_chat_loop):
        r = client.post(
            "/api/chat",
            json={"project_id": "proj-chat", "messages": [{"role": "user", "content": "Hello"}]},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["content"] == "Scoped reply"


def test_post_classify_200_with_mock(client: TestClient) -> None:
    """POST /api/classify returns document_type, tags, confidence when classify_with_llm is mocked."""
    async def fake_classify(*args, **kwargs):
        return {"document_type": "contrato", "tags": ["TAG1"], "confidence": 0.9}

    with patch("app.main.classify_with_llm", new_callable=AsyncMock, side_effect=fake_classify):
        r = client.post(
            "/api/classify",
            json={"doc_id": "doc1", "text_excerpt": "Contrato de prestação de serviços.", "filename": "doc.pdf"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["document_type"] == "contrato"
    assert data["tags"] == ["TAG1"]
    assert data["confidence"] == 0.9
