"""Tests for GET /api/documents endpoint (list/browse documents)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _os_hit(doc_id: str, project_id: str = "proj_a", doc_kind: str = "pdf") -> dict:
    return {
        "_id": doc_id,
        "_source": {
            "project_id": project_id,
            "title": f"Title {doc_id}",
            "original_filename": f"{doc_id}.pdf",
            "path": f"/data/{project_id}/{doc_id}.pdf",
            "doc_kind": doc_kind,
            "document_type": "contrato",
            "business_domain": "juridica",
            "tags": ["important"],
            "ingested_at": "2026-03-01T00:00:00Z",
        },
    }


def _os_response(hits: list[dict], total: int | None = None) -> dict:
    return {
        "hits": {
            "total": {"value": total if total is not None else len(hits)},
            "hits": hits,
        },
    }


def test_list_documents_no_filters(client):
    hits = [_os_hit("doc1"), _os_hit("doc2")]
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = _os_response(hits)
        resp = client.get("/api/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 2
    assert data["items"][0]["doc_id"] == "doc1"
    assert data["items"][0]["title"] == "Title doc1"
    assert data["items"][0]["tags"] == ["important"]

    body = mock_os.search.call_args.kwargs.get("body") or mock_os.search.call_args[1].get("body")
    assert "match_all" in body["query"]


def test_list_documents_with_project_id(client):
    hits = [_os_hit("doc1", project_id="kaido_teste")]
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = _os_response(hits)
        resp = client.get("/api/documents?project_id=kaido_teste")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["project_id"] == "kaido_teste"

    body = mock_os.search.call_args.kwargs.get("body") or mock_os.search.call_args[1].get("body")
    query = body["query"]
    assert "bool" in query
    assert "filter" in query["bool"]


def test_list_documents_with_doc_kind(client):
    hits = [_os_hit("doc1", doc_kind="xlsx")]
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = _os_response(hits)
        resp = client.get("/api/documents?doc_kind=xlsx")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["doc_kind"] == "xlsx"


def test_list_documents_pagination(client):
    hits = [_os_hit("doc3")]
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = _os_response(hits, total=5)
        resp = client.get("/api/documents?page=2&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert data["page"] == 2
    assert data["page_size"] == 2

    body = mock_os.search.call_args.kwargs.get("body") or mock_os.search.call_args[1].get("body")
    assert body["from"] == 2
    assert body["size"] == 2
