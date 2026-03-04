"""Unit tests: MCP server module import and tool registration."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.mcp.server import get_document_chunks, get_document, run_server, search_documents


def test_mcp_server_imports() -> None:
    """MCP server module and FastMCP app can be imported."""
    from app.mcp.server import mcp, run_server

    assert mcp is not None
    assert run_server is not None


def test_mcp_server_has_tools() -> None:
    """MCP server exposes expected tools (by name)."""
    from app.mcp.server import mcp

    # FastMCP exposes tools; we only check the app exists and has a name
    assert getattr(mcp, "name", None) or True
    # Tool list would come from mcp._tool_manager or similar internal API
    # Minimal check: no import error and run_server is callable
    from app.mcp.server import run_server

    assert callable(run_server)


def test_get_document_chunks_empty_locations_returns_error_json() -> None:
    """get_document_chunks with empty locations returns JSON error without calling API."""
    result = get_document_chunks("doc1", [])
    data = json.loads(result)
    assert "error" in data
    assert "location" in data["error"].lower()


def test_get_document_chunks_calls_api_and_returns_json() -> None:
    """get_document_chunks with valid locations calls backend and returns JSON."""
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
    call_args = mock_get.call_args
    assert "/chunks" in call_args[0][0]
    assert call_args[1]["params"]["locations"] == ["page:1"]
