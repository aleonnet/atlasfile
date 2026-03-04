"""Standalone tests for get_document_chunks (API and MCP). Run with: python -m pytest tests/unit/test_get_document_chunks_standalone.py -v
These tests mock the mcp_client import so they run even when mcp package has import issues."""
from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

# Allow app.main to load by providing a fake mcp_client (optional, only if import would fail)
def _ensure_app_importable():
    if "app.mcp_client" not in sys.modules:
        try:
            from app.main import app  # noqa: F401
        except ImportError:
            sys.modules["app.mcp_client"] = type(sys)("app.mcp_client")
            setattr(sys.modules["app.mcp_client"], "call_tool", lambda *a, **k: None)
            setattr(sys.modules["app.mcp_client"], "list_tools", lambda *a, **k: [])


def test_mcp_get_document_chunks_empty_locations() -> None:
    from app.mcp.server import get_document_chunks
    result = get_document_chunks("doc1", [])
    data = json.loads(result)
    assert "error" in data


def test_mcp_get_document_chunks_success() -> None:
    from app.mcp.server import get_document_chunks
    with patch("app.mcp.server.get") as mock_get:
        mock_get.return_value = {
            "doc_id": "doc1",
            "title": "Doc",
            "content_chunks": [{"location": "page:1", "text": "chunk1"}],
            "_returned_chunks": 1,
        }
        result = get_document_chunks("doc1", ["page:1"])
    data = json.loads(result)
    assert data["doc_id"] == "doc1"
    assert len(data["content_chunks"]) == 1
    assert data["content_chunks"][0]["location"] == "page:1"
    mock_get.assert_called_once()
    assert "/chunks" in mock_get.call_args[0][0]
    assert mock_get.call_args[1]["params"]["locations"] == ["page:1"]


def test_api_get_document_chunks_422_when_no_locations() -> None:
    _ensure_app_importable()
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/api/documents/doc1/chunks")
    assert r.status_code == 422


def test_api_get_document_chunks_404() -> None:
    _ensure_app_importable()
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    with patch("app.main.os_client") as mock:
        mock.get.side_effect = Exception("not found")
        r = client.get("/api/documents/doc1/chunks", params={"locations": ["page:1"]})
    assert r.status_code == 404


def test_api_get_document_chunks_200_filtered() -> None:
    _ensure_app_importable()
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    with patch("app.main.os_client") as mock:
        mock.get.return_value = {
            "_source": {
                "doc_id": "doc1",
                "project_id": "p1",
                "area_key": "a",
                "title": "T",
                "original_filename": "f",
                "canonical_filename": "f",
                "path": "p",
                "content_chunks": [
                    {"location": "page:1", "text": "c1"},
                    {"location": "page:2", "text": "c2"},
                    {"location": "docx_page:24:paragraph:2", "text": "c24"},
                ],
                "tags": [],
                "document_type": None,
                "correspondent": None,
                "review_status": None,
                "content_type": None,
                "ingested_at": None,
                "processed_at": None,
            }
        }
        r = client.get(
            "/api/documents/doc1/chunks",
            params={"locations": ["page:1", "docx_page:24:paragraph:2"]},
        )
    assert r.status_code == 200
    d = r.json()
    assert d["doc_id"] == "doc1"
    assert d["_returned_chunks"] == 2
    locs = [c["location"] for c in d["content_chunks"]]
    assert "page:1" in locs
    assert "docx_page:24:paragraph:2" in locs
    assert "page:2" not in locs
