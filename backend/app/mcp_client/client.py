"""MCP client: connect to AtlasFile MCP server via streamable HTTP, list_tools and call_tool."""
from __future__ import annotations

from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from app.config import settings


async def list_tools() -> list[dict[str, Any]]:
    """Connect to MCP server, list tools. Returns list of dicts with name, description, inputSchema."""
    url = settings.mcp_server_url
    result: list[dict[str, Any]] = []
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            for t in tools_response.tools:
                result.append({
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": getattr(t, "inputSchema", {}),
                })
    return result


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> str:
    """Connect to MCP server, call tool by name with arguments. Returns result as text."""
    url = settings.mcp_server_url
    args = arguments or {}
    async with streamable_http_client(url) as (read_stream, write_stream, _):
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
