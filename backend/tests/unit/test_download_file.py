"""GET /api/files/download — nomes acentuados não podem estourar o header latin-1."""
from __future__ import annotations

from unittest.mock import patch

from app.config import settings


def test_download_accented_filename_returns_200(client, tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "proj-1"
    project_dir.mkdir()
    accented = project_dir / "Procuração - rev.Jur. Societário.docx"
    accented.write_bytes(b"conteudo")
    monkeypatch.setattr(settings, "projects_root", str(tmp_path))

    response = client.get("/api/files/download", params={"path": str(accented)})

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert "filename*=UTF-8''Procura%C3%A7%C3%A3o" in disposition
    assert 'filename="Procuracao - rev.Jur. Societario.docx"' in disposition
    assert response.content == b"conteudo"


def test_download_outside_projects_root_403(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "projects_root", str(tmp_path / "projects"))
    with patch("app.main.os_client"):
        response = client.get("/api/files/download", params={"path": "/etc/hosts"})
    assert response.status_code == 403
