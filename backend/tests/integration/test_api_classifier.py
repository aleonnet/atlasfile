from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _setup_project(tmp_root: Path, project_name: str = "proj_classifier") -> Path:
    project_root = tmp_root / project_name
    project_root.mkdir(parents=True, exist_ok=True)
    return project_root


def test_classifier_override_endpoint_persists_project_override(client: TestClient, tmp_path: Path) -> None:
    project_root = _setup_project(tmp_path)
    with (
        patch("app.main.settings.projects_root", str(tmp_path)),
        patch("app.api.profile.settings.projects_root", str(tmp_path)),
        patch("app.api.layout.settings.projects_root", str(tmp_path)),
    ):
        init_resp = client.post(f"/api/projects/{project_root.name}/initialize")
        assert init_resp.status_code == 200

        override_resp = client.put(
            f"/api/classifier/override/{project_root.name}",
            json={"override_mode": "sparse_logreg"},
        )
        assert override_resp.status_code == 200
        assert override_resp.json()["override_mode"] == "sparse_logreg"
        assert override_resp.json()["effective_mode"] == "sparse_logreg"

        profile_resp = client.get(f"/api/projects/{project_root.name}/profile")
        assert profile_resp.status_code == 200
        profile = profile_resp.json()["profile"]
        assert profile["classification"]["operational"]["override_mode"] == "sparse_logreg"
