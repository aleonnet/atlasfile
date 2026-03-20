"""Tests for GET /api/stats endpoint."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _mock_stats_response(total: int = 5) -> dict:
    return {
        "hits": {"total": {"value": total, "relation": "eq"}, "hits": []},
        "aggregations": {
            "by_doc_kind": {"buckets": [{"key": "pdf", "doc_count": 3}, {"key": "docx", "doc_count": 2}]},
            "by_business_domain": {"buckets": [{"key": "juridica", "doc_count": 4}, {"key": "financeiro", "doc_count": 1}]},
            "by_document_type": {"buckets": [{"key": "contrato", "doc_count": 3}]},
            "by_extension": {"buckets": [{"key": ".pdf", "doc_count": 3}, {"key": ".docx", "doc_count": 2}]},
            "by_tags": {"buckets": [{"key": "juridica", "doc_count": 4}]},
            "by_project_id": {"buckets": [{"key": "Kaido", "doc_count": 3}, {"key": "Teste", "doc_count": 2}]},
        },
    }


def test_stats_returns_aggregations(client):
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = _mock_stats_response(5)
        resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents"] == 5
    assert data["project_id"] is None
    assert len(data["by_doc_kind"]) == 2
    assert data["by_doc_kind"][0]["key"] == "pdf"
    assert data["by_doc_kind"][0]["count"] == 3
    assert len(data["by_business_domain"]) == 2
    assert len(data["by_document_type"]) == 1
    assert len(data["by_extension"]) == 2
    assert len(data["by_tags"]) == 1
    assert len(data["by_project_id"]) == 2
    assert data["by_project_id"][0]["key"] == "Kaido"
    assert data["by_project_id"][0]["count"] == 3


def test_stats_with_project_id(client):
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = _mock_stats_response(2)
        resp = client.get("/api/stats?project_id=Kaido")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == "Kaido"
    assert data["total_documents"] == 2

    call_args = mock_os.search.call_args
    body = call_args.kwargs.get("body") or call_args[1].get("body")
    query = body["query"]
    assert "bool" in query
    assert "filter" in query["bool"]


def test_stats_empty_index(client):
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = {
            "hits": {"total": {"value": 0, "relation": "eq"}, "hits": []},
            "aggregations": {
                "by_doc_kind": {"buckets": []},
                "by_business_domain": {"buckets": []},
                "by_document_type": {"buckets": []},
                "by_extension": {"buckets": []},
                "by_tags": {"buckets": []},
                "by_project_id": {"buckets": []},
            },
        }
        resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents"] == 0
    assert data["by_doc_kind"] == []
    assert data["by_business_domain"] == []
    assert data["by_project_id"] == []
