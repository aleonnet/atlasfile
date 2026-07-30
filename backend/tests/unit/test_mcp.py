"""Unit tests: MCP server module import and tool registration."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.mcp.server import (
    get_document,
    get_document_chunks,
    list_documents,
    search_documents,
    spreadsheet_query,
    spreadsheet_schema,
)

EXPECTED_TOOLS = {
    "apply_tags",
    "create_review_marker",
    "get_document",
    "get_document_chunks",
    "get_stats",
    "list_documents",
    "list_tags",
    "search_documents",
    "semantic_search_chunks",
    "set_metadata",
    "spreadsheet_query",
    "spreadsheet_schema",
    "submit_classification",
}


async def test_mcp_server_registra_as_13_tools() -> None:
    """As 13 tools registradas, por nome — o contrato que o /mcp expõe."""
    from app.mcp.server import mcp

    tools = await mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_toda_tool_registrada_e_assincrona() -> None:
    """O SDK (mcp==1.26.0, func_metadata.py:92-95) executa função sync INLINE
    no event loop. No processo consolidado isso é DEADLOCK: a tool bloqueia o
    loop e o loopback HTTP dela para o próprio servidor nunca é atendido
    (medido na stack real: 60s por call, servidor inteiro surdo). Toda tool
    tem de ser registrada via o wrapper @tool() que despacha ao threadpool."""
    import inspect

    from app.mcp.server import mcp

    for registered in mcp._tool_manager.list_tools():
        assert inspect.iscoroutinefunction(registered.fn), (
            f"tool '{registered.name}' registrada como função síncrona — no app "
            "consolidado ela rodaria no event loop e deadlockaria o processo; "
            "use o decorator @tool() de app/mcp/server.py"
        )


def test_dns_rebinding_protection_explicitamente_desligada() -> None:
    """Sem transport_security explícito, o default host=127.0.0.1 auto-liga a
    proteção DNS-rebinding do SDK (allowlist localhost:*) e /mcp responde 421
    fora de localhost — TestClient e acesso via IP de LAN inclusive. O controle
    de acesso do /mcp é o MCPAuthMiddleware, não o Host header."""
    from app.mcp.server import mcp

    security = mcp.settings.transport_security
    assert security is not None
    assert security.enable_dns_rebinding_protection is False


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


def test_list_documents_tool_calls_api() -> None:
    """list_documents calls GET /api/documents with correct params."""
    with patch("app.mcp.server.get") as mock_get:
        mock_get.return_value = {"total": 1, "page": 1, "page_size": 10, "items": []}
        result = list_documents(project_id="proj_a", doc_kind="pdf", page=2, size=10)
    data = json.loads(result)
    assert data["total"] == 1
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[0][0] == "/api/documents"
    params = call_args[1].get("params") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["params"]
    assert params["project_id"] == "proj_a"
    assert params["doc_kind"] == "pdf"
    assert params["page"] == 2
    assert params["size"] == 10


def test_search_documents_short_query_returns_error() -> None:
    """search_documents with query < 2 chars returns JSON error without calling API."""
    result = search_documents(query="*")
    data = json.loads(result)
    assert "error" in data
    assert "2 characters" in data["error"]


def test_search_documents_empty_query_returns_error() -> None:
    """search_documents with empty/whitespace query returns JSON error."""
    result = search_documents(query="  ")
    data = json.loads(result)
    assert "error" in data
    assert "list_documents" in data["error"]


def test_spreadsheet_schema_calls_api() -> None:
    """spreadsheet_schema delega ao endpoint REST de schema."""
    with patch("app.mcp.server.get") as mock_get:
        mock_get.return_value = {"file": "cmdb.xlsx", "tables": [{"table": "aba", "columns": ["empresa"]}]}
        result = spreadsheet_schema(doc_id="doc-1")
    data = json.loads(result)
    assert data["tables"][0]["table"] == "aba"
    mock_get.assert_called_once_with("/api/documents/doc-1/spreadsheet/schema")


def test_spreadsheet_query_calls_api_with_sql() -> None:
    """spreadsheet_query envia o SELECT ao endpoint REST."""
    with patch("app.mcp.server.post") as mock_post:
        mock_post.return_value = {"columns": ["empresa", "qtde"], "rows": [["OI SA", 2]], "truncated": False}
        result = spreadsheet_query(doc_id="doc-1", sql="SELECT empresa, COUNT(*) AS qtde FROM aba GROUP BY 1")
    data = json.loads(result)
    assert data["rows"] == [["OI SA", 2]]
    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == "/api/documents/doc-1/spreadsheet/query"
    assert "SELECT" in mock_post.call_args[1]["json"]["sql"]


def test_spreadsheet_query_rejects_non_select_client_side() -> None:
    """Guard no cliente: não-SELECT nem chega na API."""
    with patch("app.mcp.server.post") as mock_post:
        result = spreadsheet_query(doc_id="doc-1", sql="DROP TABLE aba")
    data = json.loads(result)
    assert "error" in data
    mock_post.assert_not_called()
