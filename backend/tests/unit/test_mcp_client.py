"""Unit tests: MCP client list_tools and call_tool (mocked)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp_client import call_tool, list_tools


def _make_fake_streamable_http(captured: dict | None = None):
    """Fake com a assinatura REAL do SDK (url, *, http_client=None,
    terminate_on_close=True) — o client passa http_client= quando há token,
    e um fake posicional-only mascararia a regressão com TypeError silencioso
    nos testes errados. Captura os kwargs para asserção."""

    @asynccontextmanager
    async def _fake(url: str, *, http_client=None, terminate_on_close: bool = True):
        if captured is not None:
            captured["url"] = url
            captured["http_client"] = http_client
        yield (MagicMock(), MagicMock(), lambda: None)

    return _fake


_fake_streamable_http = _make_fake_streamable_http()


def _session_mock_with(fake_session: AsyncMock) -> MagicMock:
    session_mock = MagicMock()
    session_mock.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    session_mock.return_value.__aexit__ = AsyncMock(return_value=None)
    return session_mock


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


def _fake_session_for_list_tools() -> AsyncMock:
    fake_tools_result = MagicMock()
    fake_tools_result.tools = []
    fake_session = AsyncMock()
    fake_session.initialize = AsyncMock()
    fake_session.list_tools = AsyncMock(return_value=fake_tools_result)
    return fake_session


@pytest.mark.asyncio
async def test_token_configurado_injeta_bearer_e_fecha_o_client(monkeypatch) -> None:
    """Fase 2: com auth ligado o /mcp exige key; o SDK não aceita headers= —
    o client fornece httpx.AsyncClient com Bearer e é responsável pelo aclose()
    (o SDK NÃO fecha client fornecido: sem isso, vaza 1 client por tool call)."""
    from app.config import settings

    monkeypatch.setattr(settings, "atlasfile_api_token", "tok-interno", raising=False)
    captured: dict = {}
    with patch(
        "app.mcp_client.client.streamable_http_client", _make_fake_streamable_http(captured)
    ), patch("app.mcp_client.client.ClientSession", _session_mock_with(_fake_session_for_list_tools())):
        await list_tools()
    http_client = captured["http_client"]
    assert http_client is not None
    assert http_client.headers["authorization"] == "Bearer tok-interno"
    assert http_client.is_closed  # aclose() no finally, não no SDK


@pytest.mark.asyncio
async def test_sem_token_nao_cria_http_client(monkeypatch) -> None:
    """Sem token o SDK cria e gerencia o client próprio (comportamento vigente)."""
    from app.config import settings

    monkeypatch.setattr(settings, "atlasfile_api_token", "", raising=False)
    captured: dict = {}
    with patch(
        "app.mcp_client.client.streamable_http_client", _make_fake_streamable_http(captured)
    ), patch("app.mcp_client.client.ClientSession", _session_mock_with(_fake_session_for_list_tools())):
        await list_tools()
    assert captured["http_client"] is None
