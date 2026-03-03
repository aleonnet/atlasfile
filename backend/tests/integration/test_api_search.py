"""Integration tests: /api/search and /api/search/suggest with mocked OpenSearch."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _make_search_result(total: int = 1, with_inner_hits: bool = True) -> dict:
    hit = {
        "_source": {
            "doc_id": "doc1",
            "project_id": "proj1",
            "area_key": "ativos",
            "original_filename": "file.pdf",
            "canonical_filename": "20260101__p__ativos__file__v01.pdf",
            "path": "proj1/_WORK/03_ativos/file.pdf",
            "content_chunks_text": "some text",
        },
        "_score": 1.5,
        "highlight": {"title": ["<em>file</em> title"]},
        "inner_hits": {},
    }
    if with_inner_hits:
        hit["inner_hits"] = {
            "chunks": {
                "hits": {
                    "total": {"value": 2},
                    "hits": [
                        {"_source": {"location": "page:1", "text": "hello world"}},
                        {"_source": {"location": "page:2", "text": "more text"}},
                    ],
                }
            }
        }
    return {
        "hits": {
            "total": {"value": total},
            "hits": [hit],
        }
    }


def test_search_returns_200_with_mock(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = _make_search_result(total=1)
        r = client.get("/api/search", params={"q": "ab"})
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert data["total"] == 1
    assert "hits" in data
    assert len(data["hits"]) == 1
    assert data["hits"][0]["doc_id"] == "doc1"


def test_search_requires_min_length(client: TestClient) -> None:
    r = client.get("/api/search", params={"q": "a"})
    assert r.status_code == 422


def test_suggest_returns_200_with_mock(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {
                            "doc_id": "d1",
                            "project_id": "p1",
                            "original_filename": "doc.pdf",
                            "canonical_filename": "doc.pdf",
                            "path": "p1/_WORK/doc.pdf",
                        },
                        "highlight": {"title": ["<em>doc</em>"]},
                    }
                ],
            }
        }
        r = client.get("/api/search/suggest", params={"q": "doc"})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data


def test_suggest_requires_min_length(client: TestClient) -> None:
    r = client.get("/api/search/suggest", params={"q": "ab"})
    assert r.status_code == 422
