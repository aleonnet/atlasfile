from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _healthy_projects_root(tmp_path, monkeypatch):
    """onboarding_suggested agora exige a raiz SAUDÁVEL (v0.38.0) — os testes
    apontam para um tmp existente em vez do default /projects (ausente no host)."""
    from app.config import settings

    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)


def _mock_root(name: str) -> Path:
    return Path(f"/tmp/projects/{name}")


def test_setup_status_no_projects(client: TestClient) -> None:
    with patch("app.main.list_project_roots", return_value=[]):
        r = client.get("/api/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert data["total_project_dirs"] == 0
    assert data["initialized_projects"] == 0
    assert data["onboarding_suggested"] is True


def test_setup_status_with_uninitialized_project(client: TestClient) -> None:
    roots = [_mock_root("proj_a")]
    with (
        patch("app.main.list_project_roots", return_value=roots),
        patch("app.main.load_project_profile", side_effect=Exception("no profile")),
    ):
        r = client.get("/api/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert data["total_project_dirs"] == 1
    assert data["initialized_projects"] == 0
    assert data["onboarding_suggested"] is True


def test_setup_status_with_initialized_project(client: TestClient) -> None:
    roots = [_mock_root("proj_a")]
    with (
        patch("app.main.list_project_roots", return_value=roots),
        patch("app.main.load_project_profile", return_value={"project_id": "proj_a"}),
    ):
        r = client.get("/api/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert data["total_project_dirs"] == 1
    assert data["initialized_projects"] == 1
    assert data["onboarding_suggested"] is False


def test_setup_status_mixed_projects(client: TestClient) -> None:
    roots = [_mock_root("proj_a"), _mock_root("proj_b")]

    def _load_profile(root: Path) -> dict:
        if root.name == "proj_a":
            return {"project_id": "proj_a"}
        raise Exception("not initialized")

    with (
        patch("app.main.list_project_roots", return_value=roots),
        patch("app.main.load_project_profile", side_effect=_load_profile),
    ):
        r = client.get("/api/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert data["total_project_dirs"] == 2
    assert data["initialized_projects"] == 1
    assert data["onboarding_suggested"] is False


def test_setup_status_returns_projects_root_and_app_env(client: TestClient) -> None:
    with patch("app.main.list_project_roots", return_value=[]):
        r = client.get("/api/setup/status")
    data = r.json()
    assert "projects_root" in data
    assert isinstance(data["projects_root"], str)
    assert "app_env" in data
    assert isinstance(data["app_env"], str)
