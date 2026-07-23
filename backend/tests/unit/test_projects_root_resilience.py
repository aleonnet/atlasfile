"""Resiliência à perda da raiz de projetos: sonda de saúde, guard da limpeza de
órfãos, código estável PROJECTS_ROOT_UNAVAILABLE e templates que nunca somem."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.projects_root import projects_root_health
from app.template_store import list_templates


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_sonda_raiz_saudavel_mesmo_vazia(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)
    health = projects_root_health()
    assert health["ok"] is True
    assert health["error"] is None


def test_sonda_raiz_ausente_ou_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "projects_root", str(tmp_path / "nao_existe"), raising=False)
    health = projects_root_health()
    assert health["ok"] is False
    assert health["error"] == "projects_root_missing"

    f = tmp_path / "arquivo.txt"
    f.write_text("x")
    monkeypatch.setattr(settings, "projects_root", str(f), raising=False)
    assert projects_root_health()["error"] == "projects_root_not_a_directory"


def test_cleanup_de_orfaos_roda_com_raiz_saudavel_e_vazia(tmp_path, monkeypatch):
    """A correção do guard: raiz saudável SEM projetos limpa o índice órfão
    (antes o `valid_projects` vazio pulava a limpeza para sempre)."""
    from app.services.reconcile_service import run_reconcile
    import threading

    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)
    os_client = MagicMock()
    with patch("app.services.reconcile_service.cleanup_orphan_projects") as mock_cleanup, \
         patch("app.services.reconcile_service.rebuild_search_index", return_value={"indexed_docs": 0}):
        mock_cleanup.return_value = {"orphan_projects_found": 1, "orphan_docs_deleted": 7}
        report = run_reconcile(
            project_roots=[],
            reindex_search=True,
            reindex_mode="full",
            status={},
            lock=threading.Lock(),
            os_client=os_client,
        )
    mock_cleanup.assert_called_once_with(os_client, set(), [])
    assert report["summary"]["orphan_docs_deleted"] == 7


def test_cleanup_e_pulado_com_raiz_indisponivel(tmp_path, monkeypatch):
    from app.services.reconcile_service import run_reconcile
    import threading

    monkeypatch.setattr(settings, "projects_root", str(tmp_path / "sumiu"), raising=False)
    with patch("app.services.reconcile_service.cleanup_orphan_projects") as mock_cleanup, \
         patch("app.services.reconcile_service.rebuild_search_index", return_value={"indexed_docs": 0}):
        report = run_reconcile(
            project_roots=[],
            reindex_search=True,
            reindex_mode="full",
            status={},
            lock=threading.Lock(),
            os_client=MagicMock(),
        )
    mock_cleanup.assert_not_called()
    assert report["orphan_cleanup"]["skipped_reason"] == "projects_root_missing"


def test_setup_status_expoe_saude_da_raiz(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)
    body = client.get("/api/setup/status").json()
    assert body["projects_root_ok"] is True

    monkeypatch.setattr(settings, "projects_root", str(tmp_path / "sumiu"), raising=False)
    body = client.get("/api/setup/status").json()
    assert body["projects_root_ok"] is False
    assert body["projects_root_error"] == "projects_root_missing"
    # wizard não deve ser sugerido com a raiz quebrada (não é instância nova)
    assert body["onboarding_suggested"] is False


def test_oserror_vira_codigo_estavel_quando_raiz_indisponivel(tmp_path, monkeypatch):
    """O handler global mapeia PermissionError → 503 PROJECTS_ROOT_UNAVAILABLE
    quando a sonda reprova a raiz (mount quebrado), e 500 genérico caso contrário."""
    import asyncio
    import json as _json

    from app.main import _oserror_handler

    monkeypatch.setattr(settings, "projects_root", str(tmp_path / "sumiu"), raising=False)
    resp = asyncio.run(_oserror_handler(None, PermissionError(1, "Operation not permitted")))
    assert resp.status_code == 503
    assert _json.loads(resp.body)["detail"]["code"] == "PROJECTS_ROOT_UNAVAILABLE"

    # raiz saudável: OSError alheio à raiz segue como 500 genérico
    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)
    resp2 = asyncio.run(_oserror_handler(None, OSError("disco cheio")))
    assert resp2.status_code == 500
    assert _json.loads(resp2.body)["detail"]["code"] == "INTERNAL_ERROR"


def test_estado_emptied_exige_marcador_ausente_e_vida_anterior(tmp_path, monkeypatch):
    """v0.40: raiz saudável sem marcador só é `emptied` com evidência de vida
    anterior (índice com docs). Instância nova → `ok`; marcador presente → `ok`."""
    from app.projects_root import ensure_root_marker, projects_root_state

    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)
    # instância nova: sem marcador, sem dados anteriores → ok
    assert projects_root_state(has_prior_data=False)["state"] == "ok"
    # mount fantasma: sem marcador, índice com docs → emptied
    assert projects_root_state(has_prior_data=True)["state"] == "emptied"
    # startup grava o marcador → volta a ok mesmo com dados no índice
    assert ensure_root_marker() is True
    assert projects_root_state(has_prior_data=True)["state"] == "ok"
    # raiz indisponível prevalece sobre tudo
    monkeypatch.setattr(settings, "projects_root", str(tmp_path / "sumiu"), raising=False)
    assert projects_root_state(has_prior_data=True)["state"] == "unavailable"
    assert ensure_root_marker() is False


def test_setup_status_expoe_estado_emptied_e_bloqueia_onboarding(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)
    with patch("app.main._index_has_documents", return_value=True):
        body = client.get("/api/setup/status").json()
    assert body["projects_root_state"] == "emptied"
    # wizard não pode abrir sobre mount fantasma (escreveria no limbo)
    assert body["onboarding_suggested"] is False
    assert body["projects_root_ok"] is True  # sonda básica segue ok (dir existe)


def test_escritas_bloqueadas_com_raiz_esvaziada(client, tmp_path, monkeypatch):
    """Guard anti-limbo: upload/scan/initialize retornam 503 PROJECTS_ROOT_EMPTIED."""
    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)
    with patch("app.main._index_has_documents", return_value=True):
        r1 = client.post("/api/projects/novo_projeto/initialize")
        r2 = client.post("/api/ingest/scan/qualquer")
        r3 = client.post("/api/ingest/upload/qualquer", files={"files": ("a.txt", b"x")})
    for r in (r1, r2, r3):
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "PROJECTS_ROOT_EMPTIED"


def test_setup_status_nunca_503_com_mount_quebrado(client, tmp_path, monkeypatch):
    """v0.40.1 (achado em campo): com EPERM no listdir (mount quebrado de verdade,
    não fantasma), o setup/status respondia 503 via handler de OSError — e o modal
    de recuperação nunca aparecia. O endpoint de diagnóstico não pode falhar."""
    monkeypatch.setattr(settings, "projects_root", str(tmp_path / "sumiu"), raising=False)
    with patch("app.main.list_project_roots", side_effect=PermissionError(1, "Operation not permitted")):
        r = client.get("/api/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert body["projects_root_state"] == "unavailable"
    assert body["projects_root_ok"] is False
    assert body["onboarding_suggested"] is False


def test_restart_endpoint_agenda_saida_graciosa(client):
    with patch("app.main.threading.Timer") as mock_timer:
        r = client.post("/api/system/restart")
    assert r.status_code == 200
    assert r.json()["status"] == "restarting"
    mock_timer.assert_called_once()
    delay, fn = mock_timer.call_args[0]
    assert delay == 0.5
    mock_timer.return_value.start.assert_called_once()
    # a função agendada envia SIGTERM ao próprio processo (shutdown gracioso)
    with patch("app.main.os.kill") as mock_kill:
        fn()
    mock_kill.assert_called_once()
    import signal as _signal

    assert mock_kill.call_args[0][1] == _signal.SIGTERM


def test_templates_builtin_sobrevivem_a_raiz_quebrada(tmp_path, monkeypatch):
    # raiz aponta para um ARQUIVO: glob no dir user levanta OSError → só builtin
    f = tmp_path / "arquivo.txt"
    f.write_text("x")
    monkeypatch.setattr(settings, "projects_root", str(f), raising=False)
    slugs = {t["slug"] for t in list_templates()}
    assert "default" in slugs  # builtin nunca some
