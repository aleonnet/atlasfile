"""Integration tests: /api/projects with mocked list_project_roots."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_projects_returns_list(client: TestClient) -> None:
    with patch("app.main.list_project_roots") as m:
        m.return_value = []
        r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_get_projects_with_mocked_project(client: TestClient) -> None:
    fake_root = Path("/fake/proj1")
    with patch("app.main.list_project_roots") as m_roots:
        with patch("app.main.load_project_profile") as m_profile:
            m_roots.return_value = [fake_root]
            m_profile.return_value = {
                "project_id": "proj1",
                "project_label": "Projeto 1",
            }
            r = client.get("/api/projects")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["project_id"] == "proj1"
    assert data[0]["project_label"] == "Projeto 1"
    assert data[0]["initialized"] is True
