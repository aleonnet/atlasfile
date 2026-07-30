"""MCP client: connect to AtlasFile MCP server via streamable HTTP, list_tools and call_tool."""
from __future__ import annotations

from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from app.config import settings


def _authed_http_client() -> httpx.AsyncClient | None:
    """Com auth ligado o /mcp exige API key, e streamable_http_client não
    aceita headers= — a via é fornecer o httpx.AsyncClient inteiro. O SDK não
    fecha nem configura client fornecido: aclose() e os defaults dele
    (follow_redirects, timeout 30s/read 300s) ficam por nossa conta."""
    token = (settings.atlasfile_api_token or "").strip()
    if not token:
        return None  # sem token, o SDK cria e gerencia o client próprio
    return httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=True,
        timeout=httpx.Timeout(30.0, read=300.0),
    )


async def list_tools() -> list[dict[str, Any]]:
    """Connect to MCP server, list tools. Returns list of dicts with name, description, inputSchema."""
    url = settings.mcp_server_url
    result: list[dict[str, Any]] = []
    http_client = _authed_http_client()
    try:
        kwargs: dict[str, Any] = {"http_client": http_client} if http_client else {}
        async with streamable_http_client(url, **kwargs) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_response = await session.list_tools()
                for t in tools_response.tools:
                    result.append({
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": getattr(t, "inputSchema", {}),
                    })
    finally:
        if http_client is not None:
            await http_client.aclose()
    return result


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> str:
    """Connect to MCP server, call tool by name with arguments. Returns result as text."""
    url = settings.mcp_server_url
    args = arguments or {}
    http_client = _authed_http_client()
    try:
        kwargs: dict[str, Any] = {"http_client": http_client} if http_client else {}
        async with streamable_http_client(url, **kwargs) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                call_result = await session.call_tool(name, arguments=args)
                parts: list[str] = []
                for block in call_result.content:
                    if isinstance(block, TextContent):
                        parts.append(block.text)
                if call_result.structuredContent and not parts:
                    import json
                    parts.append(json.dumps(call_result.structuredContent, ensure_ascii=False))
                return "\n".join(parts) if parts else ""
    finally:
        if http_client is not None:
            await http_client.aclose()
