"""Dashboards de observabilidade: integridade do ndjson gerado e auto-import."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.dashboards_setup import (
    NDJSON_PATH,
    import_dashboards_once,
    start_dashboards_import_background,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT / "scripts"))
from build_dashboards_ndjson import OUTPUTS, render_ndjson  # noqa: E402


def test_ndjson_gerado_e_integro_e_artefatos_commitados_em_sincronia():
    content = render_ndjson()
    lines = [ln for ln in content.splitlines() if ln.strip()]
    objs = [json.loads(ln) for ln in lines]

    ids = [o["id"] for o in objs]
    assert len(ids) == len(set(ids)), "ids duplicados"

    by_type: dict[str, list[dict]] = {}
    for o in objs:
        by_type.setdefault(o["type"], []).append(o)
    assert len(by_type["index-pattern"]) == 3
    assert len(by_type["dashboard"]) == 1
    assert len(by_type["visualization"]) >= 15

    # referências do dashboard e das visualizações apontam para objetos existentes
    known = set(ids)
    dashboard = by_type["dashboard"][0]
    panel_refs = {r["id"] for r in dashboard["references"]}
    assert panel_refs <= known
    assert len(panel_refs) == len(by_type["visualization"]), "painel órfão ou visualização fora do dashboard"
    for viz in by_type["visualization"]:
        for ref in viz["references"]:
            assert ref["id"] in known

    # artefatos commitados (embarcado + import manual) idênticos ao gerador
    for out in OUTPUTS:
        assert out.read_text(encoding="utf-8") == content, f"desatualizado: {out} — rode scripts/build_dashboards_ndjson.py"
    assert NDJSON_PATH in OUTPUTS


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _fake_httpx(status_code: int, import_payload: dict | None = None) -> tuple[ModuleType, MagicMock]:
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.return_value = _FakeResponse(status_code)
    client.post.return_value = _FakeResponse(200, import_payload or {"success": True, "successCount": 22})
    module = ModuleType("httpx")
    module.Client = MagicMock(return_value=client)  # type: ignore[attr-defined]
    return module, client


def test_import_posta_ndjson_com_headers_e_auth(monkeypatch):
    module, client = _fake_httpx(200)
    monkeypatch.setitem(sys.modules, "httpx", module)
    monkeypatch.setattr(settings, "dashboards_url", "http://dash:5601", raising=False)

    result = import_dashboards_once()
    assert result == {"success": True, "successCount": 22}
    module.Client.assert_called_once()
    assert module.Client.call_args.kwargs["auth"] == (settings.opensearch_user, settings.opensearch_password)
    client.get.assert_called_once_with("http://dash:5601/api/status")
    post = client.post.call_args
    assert post.args[0] == "http://dash:5601/api/saved_objects/_import"
    assert post.kwargs["params"] == {"overwrite": "true"}
    assert post.kwargs["headers"] == {"osd-xsrf": "true"}
    name, payload, mime = post.kwargs["files"]["file"]
    assert name == "dashboards.ndjson"
    assert payload == NDJSON_PATH.read_bytes()
    assert mime == "application/ndjson"


def test_dashboards_fora_do_ar_retorna_none_sem_postar(monkeypatch):
    module, client = _fake_httpx(503)
    monkeypatch.setitem(sys.modules, "httpx", module)
    assert import_dashboards_once() is None
    client.post.assert_not_called()


def test_background_desiste_em_silencio_e_respeita_o_toggle(monkeypatch):
    monkeypatch.setattr(settings, "dashboards_auto_import", False, raising=False)
    assert start_dashboards_import_background() is None

    monkeypatch.setattr(settings, "dashboards_auto_import", True, raising=False)
    monkeypatch.setattr("app.dashboards_setup.IMPORT_ATTEMPTS", 2)
    monkeypatch.setattr("app.dashboards_setup.IMPORT_DELAY_SECONDS", 0.0)
    calls = {"n": 0}

    def _boom():
        calls["n"] += 1
        raise ConnectionError("dashboards reiniciando")

    monkeypatch.setattr("app.dashboards_setup.import_dashboards_once", _boom)
    thread = start_dashboards_import_background()
    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert calls["n"] == 2  # tentou, desistiu, não explodiu


def test_background_para_no_primeiro_sucesso(monkeypatch):
    monkeypatch.setattr(settings, "dashboards_auto_import", True, raising=False)
    monkeypatch.setattr("app.dashboards_setup.IMPORT_ATTEMPTS", 5)
    monkeypatch.setattr("app.dashboards_setup.IMPORT_DELAY_SECONDS", 0.0)
    calls = {"n": 0}

    def _ok():
        calls["n"] += 1
        return {"successCount": 22}

    monkeypatch.setattr("app.dashboards_setup.import_dashboards_once", _ok)
    thread = start_dashboards_import_background()
    assert thread is not None
    thread.join(timeout=5)
    assert calls["n"] == 1
