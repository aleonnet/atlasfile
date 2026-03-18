"""Integration tests: /api/projects with mocked list_project_roots."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.profile_store import load_profile
from app.template_store import save_template


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


def test_initialize_project_uses_same_template_store_resolution(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    user_templates = tmp_path / "_ATLASFILE" / "templates"
    monkeypatch.setattr("app.template_store._user_dir", lambda: user_templates)
    save_template(
        "custom_init",
        {
            "profile_version": 2,
            "project_id": "__PROJECT_ID__",
            "project_label": "__PROJECT_LABEL__",
            "project_root": "__PROJECT_ROOT__",
            "paths": {
                "inbox": "_INBOX_DROP",
                "triage": {
                    "pending": "_TRIAGE_REVIEW/pending",
                    "resolved": "_TRIAGE_REVIEW/resolved",
                    "rejected": "_TRIAGE_REVIEW/rejected",
                },
            },
            "layout": {
                "mode": "para_jd",
                "roots": {
                    "projects": "01_PROJECTS",
                    "areas": "02_AREAS",
                    "resources": "03_RESOURCES",
                    "archive": "04_ARCHIVE",
                },
                "areas_root": "02_AREAS",
                "business_domain_folders": [{"business_domain": "juridico", "folder": "juridico_custom"}],
            },
            "classification": {
                "business_domains": [{"key": "juridico", "label": "Jurídico", "aliases": ["legal"]}],
                "document_types": [
                    {
                        "key": "relatorio",
                        "label": "Relatório",
                        "aliases": ["relatorio"],
                        "extensions": [".pdf"],
                        "folder": "relatorio",
                    }
                ],
                "entity_catalog": [],
            },
            "naming": {"canonical_pattern": "{date}__{project}__{original_name}", "date_format": "%Y%m%d"},
            "indexing": {
                "topics_path": "config/topics_v1.yaml",
                "extraction_max_chars": 50000,
                "extraction_mode": "all",
            },
            "version": 1,
        },
    )

    with patch("app.main.settings.projects_root", str(tmp_path)):
        response = client.post("/api/projects/proj_custom/initialize?template=custom_init")

    assert response.status_code == 200
    profile = load_profile(tmp_path / "proj_custom")
    assert profile.layout.folder_for_business_domain("juridico") == "juridico_custom"


def test_initialize_project_default_template_persists_current_contract(
    client: TestClient,
    tmp_path: Path,
) -> None:
    with patch("app.main.settings.projects_root", str(tmp_path)):
        response = client.post("/api/projects/proj_default/initialize?template=default")

    assert response.status_code == 200
    profile = load_profile(tmp_path / "proj_default")
    assert profile.paths.inbox == "_INBOX_DROP"
    assert profile.layout.areas_root == "02_AREAS"
    assert {item.key for item in profile.classification.business_domains} >= {
        "societario",
        "juridico",
        "ativos",
        "financeiro",
        "fiscal",
        "pessoas",
        "ti",
        "operacoes",
        "regulatorio",
        "compliance",
        "suprimentos",
    }
    assert {item.key for item in profile.classification.document_types} >= {
        "contrato",
        "aditivo",
        "fato_relevante",
        "relatorio",
        "apresentacao",
        "planilha",
        "email",
        "edital",
        "plano",
    }
