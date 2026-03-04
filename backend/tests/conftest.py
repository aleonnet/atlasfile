"""Pytest fixtures: FastAPI app, TestClient, and OpenSearch mock."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# If mcp client fails to import (e.g. incompatible mcp package version), inject stub so app loads
try:
    from app.main import app
except ImportError as e:
    if "streamable_http" not in str(e):
        raise
    _stub = type(sys)("app.mcp_client")
    _stub.call_tool = lambda *a, **k: None
    _stub.list_tools = lambda *a, **k: []
    sys.modules["app.mcp_client"] = _stub
    from app.main import app


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient for integration tests."""
    return TestClient(app)


@pytest.fixture
def mock_os_search():
    """Return a dict that mimics OpenSearch search() result for hits/total."""
    def _make_result(hits: list[dict] | None = None, total: int = 0):
        hits = hits or []
        return {
            "hits": {
                "total": {"value": total},
                "hits": hits,
            }
        }
    return _make_result
