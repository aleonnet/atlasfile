"""_mount_static: o bundle do frontend só monta quando o diretório existe.

Dev e CI rodam sem dist (a UI vem do vite dev) — montar diretório ausente
quebraria o boot; nunca montar deixaria a imagem consolidada sem UI.
"""
from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.main import _mount_static


def test_monta_e_serve_quando_dir_existe(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<html>atlasfile</html>", encoding="utf-8")
    app = FastAPI()
    assert _mount_static(app, str(tmp_path)) is True
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "atlasfile" in r.text


def test_dir_ausente_nao_monta(tmp_path) -> None:
    app = FastAPI()
    assert _mount_static(app, str(tmp_path / "nao-existe")) is False
    assert TestClient(app).get("/").status_code == 404
