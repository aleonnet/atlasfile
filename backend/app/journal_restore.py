"""Restauração dos índices efêmeros a partir do journal local (v0.53.0).

Chats e eventos de custo só existiam no OpenSearch — dois resets de volume em
2026-07-25 levaram o período inteiro embora. Com o journal em filesystem
(`event_journal.py`), o índice volta a ser uma projeção reconstruível.

Idempotência: cada evento vira um `_id` determinístico (sha256 do conteúdo
canônico), então rodar duas vezes não duplica nada; sessões usam o próprio id.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from opensearchpy import OpenSearch

from .config import settings
from .event_journal import EVENT_KINDS, read_events, read_sessions

logger = logging.getLogger(__name__)

# tipo de evento → índice que o consome
_EVENT_INDEX = {
    "chat_usage": lambda: settings.opensearch_chat_usage_index,
    "classification_usage": lambda: settings.opensearch_classification_usage_index,
    "training_usage": lambda: settings.opensearch_training_usage_index,
}


def _event_id(kind: str, doc: dict[str, Any]) -> str:
    """Id determinístico pelo conteúdo: reimportar o mesmo evento não duplica."""
    canonical = json.dumps(doc, sort_keys=True, ensure_ascii=False, default=str)
    return f"{kind}-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


def restore_from_journal(client: OpenSearch, *, only_if_empty: bool = True) -> dict[str, Any]:
    """Reindexa o que o journal tem e o índice não.

    `only_if_empty=True` (default do reconcile) age só quando o índice está
    vazio — o cenário de perda de volume. `False` força a reconciliação
    completa (útil após uma restauração parcial).
    """
    summary: dict[str, Any] = {"sessions_restored": 0, "events_restored": {}, "skipped_non_empty": []}

    for kind in EVENT_KINDS:
        index_name = _EVENT_INDEX[kind]()
        events = read_events(kind)
        if not events:
            continue
        if only_if_empty and _index_count(client, index_name) > 0:
            summary["skipped_non_empty"].append(kind)
            continue
        restored = 0
        for doc in events:
            try:
                client.index(index=index_name, id=_event_id(kind, doc), body=doc)
                restored += 1
            except Exception:
                logger.exception("Journal restore: falha ao reindexar evento de %s", kind)
        if restored:
            summary["events_restored"][kind] = restored

    sessions = read_sessions()
    if sessions:
        index_name = settings.opensearch_chat_sessions_index
        if only_if_empty and _index_count(client, index_name) > 0:
            summary["skipped_non_empty"].append("chat_sessions")
        else:
            for session_id, doc in sessions:
                try:
                    client.index(index=index_name, id=session_id, body=doc)
                    summary["sessions_restored"] += 1
                except Exception:
                    logger.exception("Journal restore: falha ao reindexar sessão %s", session_id)

    return summary


def _index_count(client: OpenSearch, index_name: str) -> int:
    try:
        return int(client.count(index=index_name).get("count", 0))
    except Exception:
        return 0  # índice ausente conta como vazio: é justamente o caso de restaurar
