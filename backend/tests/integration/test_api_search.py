"""Integration tests: /api/search and /api/search/suggest with mocked OpenSearch."""
from __future__ import annotations

from pathlib import Path
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
            "business_domain": "ativos",
            "document_type": "contrato",
            "original_filename": "file.pdf",
            "canonical_filename": "20260101__p__file__v01.pdf",
            "path": "proj1/02_AREAS/03_ativos/file.pdf",
            "content_chunks": [
                {"location": "page:1", "text": "hello world", "text_normalized": "hello world"},
                {"location": "page:2", "text": "more text", "text_normalized": "more text"},
            ],
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
                        {
                            "_source": {"location": "page:1", "text": "hello world"},
                            "highlight": {"content_chunks.text": ["<em>hello</em> world"]},
                        },
                        {
                            "_source": {"location": "page:2", "text": "more text"},
                            "highlight": {"content_chunks.text": ["more <em>text</em>"]},
                        },
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
    assert data["hits"][0]["document_type"] == "contrato"


def test_search_requires_min_length(client: TestClient) -> None:
    r = client.get("/api/search", params={"q": "a"})
    assert r.status_code == 422


def test_search_project_filter_uses_path_scope_for_legacy_project_ids(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = _make_search_result(total=1)
        with patch("app.main._resolve_project_root", return_value=Path("/projects/Kaidô")):
            with patch("app.main.load_project_profile", return_value={"project_id": "Kaidô"}):
                r = client.get("/api/search", params={"q": "ab", "project_id": "Kaidô"})

    assert r.status_code == 200
    body = mock_client.search.call_args.kwargs["body"]
    filters = body["query"]["bool"]["filter"]
    project_scope = filters[0]["bool"]["should"]
    assert {"term": {"project_id": "Kaidô"}} in project_scope
    assert {"prefix": {"path": "/projects/Kaidô/"}} in project_scope


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


def test_search_highlight_includes_max_analyzer_offset(client: TestClient) -> None:
    """max_analyzer_offset must be set in highlight to prevent 400 errors on large docs."""
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = _make_search_result(total=1)
        client.get("/api/search", params={"q": "ab"})
    body = mock_client.search.call_args.kwargs["body"]
    assert "highlight" in body
    assert body["highlight"]["max_analyzer_offset"] == 1_000_000


def test_search_query_uses_nested_content_chunks(client: TestClient) -> None:
    """Search query must use nested queries for content_chunks (no flat content fields)."""
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = _make_search_result(total=1)
        client.get("/api/search", params={"q": "hello"})
    body = mock_client.search.call_args.kwargs["body"]
    should = body["query"]["bool"]["should"]
    nested_found = False
    for clause in should:
        if "nested" in clause and clause["nested"].get("path") == "content_chunks":
            nested_found = True
            assert "inner_hits" in clause["nested"]
            break
    assert nested_found, "Expected a nested query on content_chunks"
    highlight_fields = list(body["highlight"]["fields"].keys())
    assert "content" not in highlight_fields
    assert "content_chunks_text" not in highlight_fields


def test_search_query_includes_ocr_folded_fields(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = _make_search_result(total=1)
        client.get("/api/search", params={"q": "contrato"})
    body = mock_client.search.call_args.kwargs["body"]
    should = body["query"]["bool"]["should"]
    assert any(
        clause.get("multi_match", {}).get("fields")
        and "title_ocr_folded^5" in clause["multi_match"]["fields"]
        for clause in should
    )
    nested = next(clause["nested"] for clause in should if "nested" in clause and clause["nested"].get("path") == "content_chunks")
    nested_should = nested["query"]["bool"]["should"]
    assert any(
        inner.get("multi_match", {}).get("fields")
        and "content_chunks.text_ocr_folded^4" in inner["multi_match"]["fields"]
        for inner in nested_should
    )


def test_search_prioritizes_exact_filename_over_more_content_evidences(client: TestClient) -> None:
    exact_filename = "Plano convenio bancario v3_2024.12.27.pdf"
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {
                        "_source": {
                            "doc_id": "doc-content-heavy",
                            "project_id": "proj1",
                            "area_key": "financeiro",
                            "business_domain": "financeiro",
                            "document_type": "relatorio",
                            "title": "Outro documento",
                            "original_filename": "outro_documento.pdf",
                            "canonical_filename": "20260101__outro_documento.pdf",
                            "path": "proj1/02_AREAS/financeiro/relatorio/outro_documento.pdf",
                        },
                        "_score": 99.0,
                        "highlight": {},
                        "inner_hits": {
                            "chunks": {
                                "hits": {
                                    "total": {"value": 8},
                                    "hits": [
                                        {
                                            "_source": {"location": "page:1", "text": "plano convenio bancario"},
                                            "highlight": {"content_chunks.text": ["<em>plano convenio bancario</em>"]},
                                        }
                                    ],
                                }
                            }
                        },
                    },
                    {
                        "_source": {
                            "doc_id": "doc-exact",
                            "project_id": "proj1",
                            "area_key": "financeiro",
                            "business_domain": "financeiro",
                            "document_type": "plano",
                            "title": "Plano convenio bancario v3_2024.12.27",
                            "original_filename": exact_filename,
                            "canonical_filename": "20241227__plano_convenio_bancario.pdf",
                            "path": f"proj1/02_AREAS/financeiro/plano/{exact_filename}",
                        },
                        "_score": 5.0,
                        "highlight": {"original_filename_text": [f"<em>{exact_filename}</em>"]},
                        "inner_hits": {
                            "chunks": {
                                "hits": {
                                    "total": {"value": 1},
                                    "hits": [],
                                }
                            }
                        },
                    },
                ],
            }
        }
        r = client.get("/api/search", params={"q": exact_filename})
    assert r.status_code == 200
    data = r.json()
    assert data["hits"][0]["doc_id"] == "doc-exact"
    assert data["hits"][0]["original_filename"] == exact_filename


def test_suggest_highlight_includes_max_analyzer_offset(client: TestClient) -> None:
    """max_analyzer_offset must be set in suggest highlight too."""
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = {
            "hits": {"total": {"value": 0}, "hits": []}
        }
        client.get("/api/search/suggest", params={"q": "doc"})
    body = mock_client.search.call_args.kwargs["body"]
    assert "highlight" in body
    assert body["highlight"]["max_analyzer_offset"] == 1_000_000


def test_suggest_query_includes_ocr_folded_fields(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
        client.get("/api/search/suggest", params={"q": "contrato"})
    body = mock_client.search.call_args.kwargs["body"]
    should = body["query"]["bool"]["should"]
    assert any(
        clause.get("multi_match", {}).get("fields")
        and "title_ocr_folded^3" in clause["multi_match"]["fields"]
        for clause in should
    )


def test_suggest_project_filter_uses_path_scope_for_legacy_project_ids(client: TestClient) -> None:
    with patch("app.main.os_client") as mock_client:
        mock_client.search.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {
                            "doc_id": "d1",
                            "project_id": "legacy_kaido",
                            "original_filename": "doc.pdf",
                            "canonical_filename": "doc.pdf",
                            "path": "/projects/Kaidô/_TRIAGE_REVIEW/pending/doc.pdf",
                        },
                        "highlight": {"title": ["<em>doc</em>"]},
                    }
                ],
            }
        }
        with patch("app.main._resolve_project_root", return_value=Path("/projects/Kaidô")):
            with patch("app.main.load_project_profile", return_value={"project_id": "Kaidô"}):
                r = client.get("/api/search/suggest", params={"q": "doc", "project_id": "Kaidô"})

    assert r.status_code == 200
    body = mock_client.search.call_args.kwargs["body"]
    filters = body["query"]["bool"]["filter"]
    project_scope = filters[0]["bool"]["should"]
    assert {"term": {"project_id": "Kaidô"}} in project_scope
    assert {"prefix": {"path": "/projects/Kaidô/"}} in project_scope
