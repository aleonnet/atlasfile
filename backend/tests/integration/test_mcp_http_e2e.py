"""E2E do /mcp com lifespan real: handshake streamable HTTP, duas vezes.

Prova as duas metades da armadilha do session manager num teste só:
- sem ``async with session_manager.run():`` no lifespan, o 1º handshake falha
  (Task group is not initialized);
- sem o reset ``_session_manager = None``, o 2º ciclo de lifespan no MESMO
  processo explode com RuntimeError — ``run()`` é single-use por instância.

O startup pesado (OpenSearch, watchers, catálogo) é neutralizado por
monkeypatch: o alvo aqui é exclusivamente o wiring do /mcp.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import app.main as main_module
from app.main import app

# Espelho de tests/unit/test_mcp.py::EXPECTED_TOOLS (tests/ não é pacote —
# duplicar é o custo de manter os dois testes independentes).
EXPECTED_TOOLS = {
    "apply_tags",
    "create_review_marker",
    "get_document",
    "get_document_chunks",
    "get_stats",
    "list_documents",
    "list_tags",
    "search_documents",
    "semantic_search_chunks",
    "set_metadata",
    "spreadsheet_query",
    "spreadsheet_schema",
    "submit_classification",
}

_STARTUP_HEAVY = [
    "ensure_root_marker",
    "start_dashboards_import_background",
    "ensure_index",
    "ensure_chat_sessions_index",
    "ensure_classification_usage_index",
    "ensure_chat_usage_index",
    "ensure_training_usage_index",
    "_backfill_channel_web",
    "backfill_search_fields",
    "_start_auto_reconcile_if_enabled",
    "_start_setup_reconcile_if_needed",
    "_start_auto_ingest_if_enabled",
    "_maybe_refresh_catalog_on_startup",
]

HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@pytest.fixture
def _light_startup(monkeypatch) -> None:
    for name in _STARTUP_HEAVY:
        monkeypatch.setattr(main_module, name, lambda *a, **k: None)


def _handshake_and_list_tools(client: TestClient) -> set[str]:
    init = client.post(
        "/mcp",
        headers=HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "bancada-atlasfile", "version": "0"},
            },
        },
    )
    assert init.status_code == 200, init.text
    session_id = init.headers.get("mcp-session-id")
    assert session_id, "initialize deve devolver mcp-session-id"
    proto = init.json()["result"]["protocolVersion"]
    session_headers = {**HEADERS, "mcp-session-id": session_id, "mcp-protocol-version": proto}

    notif = client.post(
        "/mcp",
        headers=session_headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert notif.status_code in (200, 202), notif.text

    tools = client.post(
        "/mcp",
        headers=session_headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert tools.status_code == 200, tools.text
    return {t["name"] for t in tools.json()["result"]["tools"]}


def test_mcp_handshake_real_e_lifespan_reentravel(_light_startup) -> None:
    with TestClient(app) as client:
        assert _handshake_and_list_tools(client) == EXPECTED_TOOLS

    # Segundo ciclo de lifespan no mesmo processo: sem o reset do manager no
    # startup, este bloco morre em "run() can only be called once per instance".
    with TestClient(app) as client:
        assert _handshake_and_list_tools(client) == EXPECTED_TOOLS
