"""Journal local-first de chats e eventos de custo (v0.53.0).

Motivo (incidente real de 2026-07-25): documentos, profiles e histórico de
ingestão sobrevivem a qualquer perda de índice porque moram no filesystem —
mas **chats e eventos de custo LLM viviam só no OpenSearch**. Dois resets de
volume levaram o período inteiro embora, sem origem para reconstruir.

Desenho:
- **Eventos** (chat_usage, classification_usage, training_usage) são
  append-only: um NDJSON por tipo e por mês em `_ATLASFILE/journal/`. Append é
  barato, resistente a corte de energia e trivial de reler.
- **Sessões de chat** são mutáveis (mensagens vão sendo acrescentadas): cada
  save grava o documento inteiro em `journal/chat_sessions/<id>.json` por
  escrita atômica. Chats são pequenos; simplicidade vence event-sourcing.
- Falha de escrita **nunca** derruba a operação — o journal é rede de
  segurança, não caminho crítico (mesmo princípio do cache de excerpt).

A restauração vive em `journal_restore.py` e é acionada pelo reconcile.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

# Tipos de evento append-only → índice que os consome na restauração
EVENT_KINDS = ("chat_usage", "classification_usage", "training_usage")
SESSIONS_KIND = "chat_sessions"

_write_lock = threading.Lock()


def journal_root() -> Path:
    return Path(settings.projects_root) / "_ATLASFILE" / "journal"


def _event_file(kind: str, when: datetime) -> Path:
    return journal_root() / f"{kind}-{when:%Y%m}.ndjson"


def append_event(kind: str, doc: dict[str, Any]) -> None:
    """Acrescenta um evento ao journal do mês. Nunca levanta."""
    if kind not in EVENT_KINDS:
        logger.warning("Journal: tipo de evento desconhecido %s", kind)
        return
    try:
        path = _event_file(kind, datetime.now(timezone.utc))
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(doc, ensure_ascii=False, default=str)
        with _write_lock, path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        logger.exception("Journal: falha ao gravar evento %s", kind)


def save_session(session_id: str, doc: dict[str, Any]) -> None:
    """Grava o snapshot completo de uma sessão de chat (escrita atômica)."""
    session_id = str(session_id or "").strip()
    if not session_id:
        return
    try:
        path = journal_root() / SESSIONS_KIND / f"{session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, path)  # atômico: leitor nunca vê arquivo pela metade
    except Exception:
        logger.exception("Journal: falha ao gravar sessão %s", session_id)


def delete_session(session_id: str) -> None:
    """Remove o snapshot quando a sessão é apagada de propósito — senão a
    restauração ressuscitaria o que o usuário excluiu."""
    session_id = str(session_id or "").strip()
    if not session_id:
        return
    try:
        (journal_root() / SESSIONS_KIND / f"{session_id}.json").unlink(missing_ok=True)
    except Exception:
        logger.exception("Journal: falha ao remover sessão %s", session_id)


def read_events(kind: str) -> list[dict[str, Any]]:
    """Todos os eventos de um tipo, de todos os meses. Linha corrompida é
    pulada (um append interrompido não pode inutilizar o journal inteiro)."""
    out: list[dict[str, Any]] = []
    root = journal_root()
    if not root.exists():
        return out
    for path in sorted(root.glob(f"{kind}-*.ndjson")):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            logger.exception("Journal: falha ao ler %s", path)
    return out


def read_sessions() -> list[tuple[str, dict[str, Any]]]:
    """(session_id, doc) de todos os snapshots gravados."""
    out: list[tuple[str, dict[str, Any]]] = []
    root = journal_root() / SESSIONS_KIND
    if not root.exists():
        return out
    for path in sorted(root.glob("*.json")):
        try:
            out.append((path.stem, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return out
