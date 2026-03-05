"""Ingest scan history — persisted in _PROFILE/ingest_history.json (FIFO, cap 50)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .profile_store import PROFILE_DIR

INGEST_HISTORY_FILE = "ingest_history.json"
MAX_ENTRIES = 50


def _history_path(project_root: Path) -> Path:
    return project_root / PROFILE_DIR / INGEST_HISTORY_FILE


def load_ingest_history(project_root: Path) -> list[dict[str, Any]]:
    path = _history_path(project_root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("entries", []))
    except Exception:
        return []


def append_ingest_entry(
    project_root: Path,
    *,
    scan_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Append a scan result to the history file (FIFO, newest first).

    Only records entries with at least one processed item or error.
    """
    items = scan_result.get("items", [])
    errors = scan_result.get("errors", [])
    if not items and not errors:
        return load_ingest_history(project_root)

    entries = load_ingest_history(project_root)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_id": scan_result.get("project_id", ""),
        "processed_count": scan_result.get("processed_count", 0),
        "failed_count": scan_result.get("failed_count", 0),
        "items": scan_result.get("items", []),
        "errors": scan_result.get("errors", []),
    }

    entries.insert(0, entry)
    if len(entries) > MAX_ENTRIES:
        entries = entries[:MAX_ENTRIES]

    path = _history_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"max_entries": MAX_ENTRIES, "entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return entries
