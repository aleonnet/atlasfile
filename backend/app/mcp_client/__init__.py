"""MCP client: connect to AtlasFile MCP server, list_tools and call_tool for the orchestrator."""

from .client import call_tool, list_tools

__all__ = ["list_tools", "call_tool"]
