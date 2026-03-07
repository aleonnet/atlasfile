"""Integration tests: /api/documents, /api/documents/{id}/tags, /api/documents/{id} PATCH, /api/tags with mocked OpenSearch."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_document_404(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.get.side_effect = Exception("not found")
        r = client.get("/api/documents/some-doc-id")
    assert r.status_code == 404
    assert "nao encontrado" in r.json().get("detail", "").lower()


def test_get_document_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.get.return_value = {
            "_source": {
                "doc_id": "doc1",
                "project_id": "p1",
                "area_key": "ativos",
                "title": "Doc title",
                "original_filename": "file.pdf",
                "path": "p1/_WORK/03_ativos/file.pdf",
                "content_chunks": [{"location": "page:1", "text": "chunk1"}],
                "tags": ["TAG1"],
                "document_type": "contrato",
                "ingested_at": "2025-01-01T00:00:00Z",
            }
        }
        r = client.get("/api/documents/doc1")
    assert r.status_code == 200
    data = r.json()
    assert data["doc_id"] == "doc1"
    assert data["area_key"] == "ativos"
    assert data["content"] == "chunk1"
    assert data["content_chunks"] == [{"location": "page:1", "text": "chunk1"}]
    assert data["tags"] == ["TAG1"]


def test_get_document_chunks_404(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.get.side_effect = Exception("not found")
        r = client.get("/api/documents/doc1/chunks", params={"locations": ["page:1"]})
    assert r.status_code == 404


def test_get_document_chunks_422_empty_locations(client: TestClient) -> None:
    r = client.get("/api/documents/doc1/chunks")
    assert r.status_code == 422


def test_get_document_chunks_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.get.return_value = {
            "_source": {
                "doc_id": "doc1",
                "project_id": "p1",
                "area_key": "ativos",
                "title": "Doc title",
                "original_filename": "file.pdf",
                "canonical_filename": "file.pdf",
                "path": "p1/_WORK/03_ativos/file.pdf",
                "content_chunks": [
                    {"location": "page:1", "text": "chunk1"},
                    {"location": "page:2", "text": "chunk2"},
                    {"location": "docx_page:24:paragraph:2", "text": "chunk24"},
                ],
                "tags": ["TAG1"],
                "document_type": "contrato",
                "ingested_at": "2025-01-01T00:00:00Z",
            }
        }
        r = client.get(
            "/api/documents/doc1/chunks",
            params={"locations": ["page:1", "docx_page:24:paragraph:2"]},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["doc_id"] == "doc1"
    assert data["title"] == "Doc title"
    assert data["_requested_locations"] == 2
    assert data["_returned_chunks"] == 2
    chunks = data["content_chunks"]
    locations = [c["location"] for c in chunks]
    assert "page:1" in locations
    assert "docx_page:24:paragraph:2" in locations
    assert "page:2" not in locations
    assert any(c["text"] == "chunk1" for c in chunks)
    assert any(c["text"] == "chunk24" for c in chunks)


def test_post_document_tags_404(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.get.side_effect = Exception("not found")
        r = client.post("/api/documents/doc1/tags", json={"add": ["TAG1"]})
    assert r.status_code == 404


def test_post_document_tags_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.get.return_value = {"_source": {"tags": ["A"]}}
        r = client.post(
            "/api/documents/doc1/tags",
            json={"add": ["B", "C"], "remove": []},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["doc_id"] == "doc1"
    assert "tags" in data
    mock_client.update.assert_called_once()


def test_patch_document_404(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.get.side_effect = Exception("not found")
        r = client.patch("/api/documents/doc1", json={"review_status": "needs_review"})
    assert r.status_code == 404


def test_patch_document_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.get.return_value = {"_source": {}}
        r = client.patch(
            "/api/documents/doc1",
            json={"document_type": "contrato", "review_status": "needs_review"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["doc_id"] == "doc1"
    mock_client.update.assert_called_once()
    call_body = mock_client.update.call_args[1]["body"]
    assert call_body["doc"]["document_type"] == "contrato"
    assert call_body["doc"]["review_status"] == "needs_review"


def test_get_tags_200(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = {
            "aggregations": {
                "tags": {
                    "buckets": [{"key": "A"}, {"key": "B"}],
                }
            }
        }
        r = client.get("/api/tags")
    assert r.status_code == 200
    data = r.json()
    assert data["tags"] == ["A", "B"]
