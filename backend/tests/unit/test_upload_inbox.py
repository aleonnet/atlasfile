from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture()
def _project(tmp_path: Path):
    """Create a minimal initialized project and patch settings."""
    from app.profile_store import create_default_profile, save_profile

    project_root = tmp_path / "proj"
    project_root.mkdir()
    profile = create_default_profile(project_root=project_root, project_id="proj", project_label="Proj")
    save_profile(project_root=project_root, profile=profile, updated_by="tests")
    profile_dict = profile.model_dump()
    inbox = project_root / profile_dict["paths"]["inbox"]
    inbox.mkdir(parents=True, exist_ok=True)

    with patch.object(main_module.settings, "projects_root", str(tmp_path)):
        yield project_root, profile_dict


@pytest.fixture()
def client():
    return TestClient(main_module.app)


def test_upload_single_file(client: TestClient, _project, tmp_path: Path):
    project_root, profile = _project
    inbox = project_root / profile["paths"]["inbox"]

    resp = client.post(
        "/api/ingest/upload/proj",
        files=[("files", ("doc.pdf", b"fake-pdf-content", "application/pdf"))],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["uploaded"]) == 1
    assert data["uploaded"][0]["filename"] == "doc.pdf"
    assert data["uploaded"][0]["saved_as"] == "doc.pdf"
    assert (inbox / "doc.pdf").exists()
    assert (inbox / "doc.pdf").read_bytes() == b"fake-pdf-content"


def test_upload_multiple_files(client: TestClient, _project, tmp_path: Path):
    project_root, profile = _project
    inbox = project_root / profile["paths"]["inbox"]

    resp = client.post(
        "/api/ingest/upload/proj",
        files=[
            ("files", ("a.pdf", b"content-a", "application/pdf")),
            ("files", ("b.docx", b"content-b", "application/octet-stream")),
            ("files", ("c.xlsx", b"content-c", "application/octet-stream")),
        ],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["uploaded"]) == 3
    assert (inbox / "a.pdf").exists()
    assert (inbox / "b.docx").exists()
    assert (inbox / "c.xlsx").exists()


def test_upload_duplicate_name_renames(client: TestClient, _project, tmp_path: Path):
    project_root, profile = _project
    inbox = project_root / profile["paths"]["inbox"]
    (inbox / "doc.pdf").write_bytes(b"existing")

    resp = client.post(
        "/api/ingest/upload/proj",
        files=[("files", ("doc.pdf", b"new-content", "application/pdf"))],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["uploaded"][0]["saved_as"] == "doc__2.pdf"
    assert (inbox / "doc__2.pdf").exists()
    assert (inbox / "doc__2.pdf").read_bytes() == b"new-content"
    # Original untouched
    assert (inbox / "doc.pdf").read_bytes() == b"existing"


def test_upload_nonexistent_project(client: TestClient, tmp_path: Path):
    with patch.object(main_module.settings, "projects_root", str(tmp_path)):
        resp = client.post(
            "/api/ingest/upload/nonexistent",
            files=[("files", ("doc.pdf", b"data", "application/pdf"))],
        )
        assert resp.status_code == 404


def test_upload_no_files(client: TestClient, _project):
    resp = client.post("/api/ingest/upload/proj")
    assert resp.status_code == 422


def test_upload_path_traversal_is_neutralized(client: TestClient, _project, tmp_path: Path):
    """Filename com ../ vindo do cliente nao pode escapar da inbox.

    Pre-existente desde a criacao do endpoint: `dest = inbox / original_name`
    com o filename cru — um multipart com filename `../../escapou.txt`
    escrevia FORA da inbox (flagado na Fase 3, corrigido aqui).
    """
    project_root, profile = _project
    inbox = project_root / profile["paths"]["inbox"]

    resp = client.post(
        "/api/ingest/upload/proj",
        files=[("files", ("../../escapou.txt", b"malicia", "text/plain"))],
    )
    assert resp.status_code == 200
    assert resp.json()["uploaded"][0]["saved_as"] == "escapou.txt"
    assert (inbox / "escapou.txt").read_bytes() == b"malicia"
    # nada escrito fora da inbox — nem na raiz do projeto, nem acima dela
    assert not (project_root / "escapou.txt").exists()
    assert not (tmp_path / "escapou.txt").exists()


def test_upload_absolute_path_is_neutralized(client: TestClient, _project, tmp_path: Path):
    project_root, profile = _project
    inbox = project_root / profile["paths"]["inbox"]

    alvo_fora = tmp_path / "abs_escapou.txt"
    resp = client.post(
        "/api/ingest/upload/proj",
        files=[("files", (str(alvo_fora), b"malicia", "text/plain"))],
    )
    assert resp.status_code == 200
    assert resp.json()["uploaded"][0]["saved_as"] == "abs_escapou.txt"
    assert (inbox / "abs_escapou.txt").exists()
    assert not alvo_fora.exists()


def test_upload_dot_dot_name_falls_back_to_unnamed(client: TestClient, _project):
    project_root, profile = _project
    inbox = project_root / profile["paths"]["inbox"]

    resp = client.post(
        "/api/ingest/upload/proj",
        files=[("files", ("..", b"x", "application/octet-stream"))],
    )
    assert resp.status_code == 200
    assert resp.json()["uploaded"][0]["saved_as"] == "unnamed"
    assert (inbox / "unnamed").exists()


def test_delete_inbox_file(client: TestClient, _project, tmp_path: Path):
    project_root, profile = _project
    inbox = project_root / profile["paths"]["inbox"]
    (inbox / "to_delete.pdf").write_bytes(b"content")

    resp = client.delete("/api/ingest/upload/proj/to_delete.pdf")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == "to_delete.pdf"
    assert not (inbox / "to_delete.pdf").exists()


def test_delete_inbox_file_not_found(client: TestClient, _project):
    resp = client.delete("/api/ingest/upload/proj/nonexistent.pdf")
    assert resp.status_code == 404
