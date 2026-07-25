from __future__ import annotations

from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class InboxEventHandler(FileSystemEventHandler):
    """Sinaliza atividade na inbox para o auto-ingest.

    Escuta AMPLA (qualquer evento de arquivo), não `on_created`: fato medido em
    2026-07-25 — no bind mount VirtioFS do Docker Desktop, a criação de arquivo
    feita no host chega ao container só como `modified`. O handler não decide
    nada; apenas marca o projeto como "sujo" e o manager aplica quiescência +
    guarda de estabilidade antes de disparar o scan.
    """

    def __init__(self, callback: Callable[[], None]):
        self._callback = callback

    def on_any_event(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        self._callback()


def schedule_inbox_watch(observer: Observer, inbox_dir: Path, callback: Callable[[], None]):
    """Registra um watch de inbox num Observer compartilhado; retorna o handle
    (usado para desregistrar quando o projeto some)."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    return observer.schedule(InboxEventHandler(callback), str(inbox_dir), recursive=False)
