"""Pytest fixtures: FastAPI app, TestClient, and OpenSearch mock."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Import app after we can patch; tests that need OS mock will patch app.main.os_client
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
