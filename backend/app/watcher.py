from __future__ import annotations

from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class InboxCreatedHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[Path], None]):
        self._callback = callback

    def on_created(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        self._callback(Path(event.src_path))


def start_inbox_watcher(inbox_dir: Path, callback: Callable[[Path], None]) -> Observer:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(InboxCreatedHandler(callback), str(inbox_dir), recursive=False)
    observer.start()
    return observer
