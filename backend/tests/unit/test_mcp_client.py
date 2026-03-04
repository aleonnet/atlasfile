"""Unit tests: MCP client list_tools and call_tool (mocked)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp_client import call_tool, list_tools


@asynccontextmanager
async def _fake_streamable_http(url: str):
    """Fake streamable_http_client(url) returning (read, write, get_id)."""
    yield (MagicMock(), MagicMock(), lambda: None)


@pytest.mark.asyncio
async def test_list_tools_returns_tools_from_mcp() -> None:
    """list_tools connects to MCP and returns list of tool dicts."""
    fake_tools_result = MagicMock()
    t1 = MagicMock()
    t1.name = "search_documents"
    t1.description = "Search docs"
    t1.inputSchema = {"type": "object"}
    t2 = MagicMock()
    t2.name = "get_document"
    t2.description = "Get doc"
    t2.inputSchema = {"type": "object"}
    fake_tools_result.tools = [t1, t2]
    fake_session = AsyncMock()
    fake_session.initialize = AsyncMock()
    fake_session.list_tools = AsyncMock(return_value=fake_tools_result)

    session_mock = MagicMock()
    session_mock.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    session_mock.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.mcp_client.client.streamable_http_client", _fake_streamable_http), patch(
        "app.mcp_client.client.ClientSession", session_mock
    ):
        out = await list_tools()
    assert len(out) == 2
    assert out[0]["name"] == "search_documents"
    assert out[1]["name"] == "get_document"


@pytest.mark.asyncio
async def test_call_tool_returns_text_from_mcp() -> None:
    """call_tool connects to MCP, calls tool, returns concatenated text content."""
    from mcp.types import TextContent

    fake_result = MagicMock()
    fake_result.content = [
        TextContent(type="text", text="result line 1"),
        TextContent(type="text", text="result line 2"),
    ]
    fake_result.structuredContent = None

    fake_session = AsyncMock()
    fake_session.initialize = AsyncMock()
    fake_session.call_tool = AsyncMock(return_value=fake_result)

    session_mock = MagicMock()
    session_mock.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    session_mock.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.mcp_client.client.streamable_http_client", _fake_streamable_http), patch(
        "app.mcp_client.client.ClientSession", session_mock
    ):
        out = await call_tool("get_document", {"doc_id": "abc"})
    assert "result line 1" in out
    assert "result line 2" in out
    fake_session.call_tool.assert_called_once_with("get_document", arguments={"doc_id": "abc"})
