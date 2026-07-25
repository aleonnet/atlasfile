"""Journal local de chats e custos + restauração (v0.53.0).

Incidente que originou: dois resets de volume em 2026-07-25 apagaram chats e
eventos de custo para sempre — eram os únicos dados sem origem em filesystem.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import event_journal as journal
from app.journal_restore import restore_from_journal


@pytest.fixture(autouse=True)
def journal_root(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(journal.settings, "projects_root", str(tmp_path))
    return tmp_path / "_ATLASFILE" / "journal"


def test_evento_vira_linha_ndjson_no_arquivo_do_mes(journal_root: Path) -> None:
    journal.append_event("chat_usage", {"model": "gpt-5", "estimated_cost_usd": 0.01})
    journal.append_event("chat_usage", {"model": "gpt-5", "estimated_cost_usd": 0.02})

    arquivos = list(journal_root.glob("chat_usage-*.ndjson"))
    assert len(arquivos) == 1, "um arquivo por tipo e mês"
    linhas = arquivos[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2
    assert json.loads(linhas[1])["estimated_cost_usd"] == 0.02


def test_tipo_desconhecido_nao_grava_nem_estoura(journal_root: Path) -> None:
    journal.append_event("inventado", {"a": 1})
    assert not list(journal_root.glob("inventado-*.ndjson"))


def test_falha_de_escrita_nunca_derruba_a_operacao(monkeypatch) -> None:
    """O journal é rede de segurança, não caminho crítico."""
    monkeypatch.setattr(journal.settings, "projects_root", "/caminho/que/nao/existe/e/nao/da/pra/criar\0")
    journal.append_event("chat_usage", {"a": 1})   # não pode levantar
    journal.save_session("s1", {"title": "x"})     # idem


def test_sessao_snapshot_atomico_e_delete(journal_root: Path) -> None:
    journal.save_session("s1", {"title": "Primeira", "messages": [1]})
    journal.save_session("s1", {"title": "Primeira", "messages": [1, 2]})

    doc = json.loads((journal_root / "chat_sessions" / "s1.json").read_text(encoding="utf-8"))
    assert doc["messages"] == [1, 2], "snapshot sobrescreve com o estado atual"
    assert not list((journal_root / "chat_sessions").glob("*.tmp")), "temporário não pode sobrar"

    journal.delete_session("s1")
    assert not (journal_root / "chat_sessions" / "s1.json").exists()


def test_linha_corrompida_nao_inutiliza_o_journal(journal_root: Path) -> None:
    journal.append_event("chat_usage", {"ok": 1})
    arquivo = next(journal_root.glob("chat_usage-*.ndjson"))
    with arquivo.open("a", encoding="utf-8") as handle:
        handle.write('{"metade": \n')  # append interrompido (queda de energia)
    journal.append_event("chat_usage", {"ok": 2})

    eventos = journal.read_events("chat_usage")
    assert [e["ok"] for e in eventos] == [1, 2]


# ── Restauração ──────────────────────────────────────────────────────────────


def _client(counts: dict[str, int] | None = None) -> MagicMock:
    client = MagicMock()
    counts = counts or {}
    client.count.side_effect = lambda index: {"count": counts.get(index, 0)}
    return client


def test_restaura_eventos_e_sessoes_quando_o_indice_esta_vazio(journal_root: Path) -> None:
    journal.append_event("chat_usage", {"model": "gpt-5"})
    journal.append_event("classification_usage", {"doc_id": "d1"})
    journal.save_session("s1", {"title": "Chat"})
    client = _client()

    resumo = restore_from_journal(client, only_if_empty=True)

    assert resumo["events_restored"] == {"chat_usage": 1, "classification_usage": 1}
    assert resumo["sessions_restored"] == 1
    assert client.index.call_count == 3


def test_indice_com_dado_vivo_nunca_e_sobrescrito(journal_root: Path, monkeypatch) -> None:
    """Restauração é para volume perdido — não pode atropelar índice em uso."""
    journal.append_event("chat_usage", {"model": "gpt-5"})
    client = _client({journal.settings.opensearch_chat_usage_index: 42})

    resumo = restore_from_journal(client, only_if_empty=True)

    assert "chat_usage" in resumo["skipped_non_empty"]
    assert client.index.call_count == 0


def test_reimportar_o_mesmo_evento_nao_duplica(journal_root: Path) -> None:
    """Id determinístico por conteúdo: rodar duas vezes é idempotente."""
    journal.append_event("chat_usage", {"model": "gpt-5", "estimated_cost_usd": 0.01})
    client = _client()

    restore_from_journal(client, only_if_empty=False)
    primeiro_id = client.index.call_args.kwargs["id"]
    client.index.reset_mock()
    restore_from_journal(client, only_if_empty=False)

    assert client.index.call_args.kwargs["id"] == primeiro_id
