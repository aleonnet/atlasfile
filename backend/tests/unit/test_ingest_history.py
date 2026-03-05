"""Tests for ingest_history module — FIFO persistence in _PROFILE/ingest_history.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingest_history import (
    INGEST_HISTORY_FILE,
    MAX_ENTRIES,
    append_ingest_entry,
    load_ingest_history,
)
from app.profile_store import PROFILE_DIR


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    (tmp_path / PROFILE_DIR).mkdir()
    return tmp_path


def _make_result(project_id: str = "p1", items_count: int = 1) -> dict:
    return {
        "project_id": project_id,
        "processed_count": items_count,
        "failed_count": 0,
        "items": [{"doc_id": f"d{i}"} for i in range(items_count)],
        "errors": [],
    }


def _make_empty_result(project_id: str = "p1") -> dict:
    return {
        "project_id": project_id,
        "processed_count": 0,
        "failed_count": 0,
        "items": [],
        "errors": [],
    }


def test_load_empty(project_root: Path) -> None:
    entries = load_ingest_history(project_root)
    assert entries == []


def test_append_and_load(project_root: Path) -> None:
    result = _make_result(items_count=2)
    entries = append_ingest_entry(project_root, scan_result=result)
    assert len(entries) == 1
    assert entries[0]["processed_count"] == 2
    assert "timestamp" in entries[0]

    loaded = load_ingest_history(project_root)
    assert len(loaded) == 1
    assert loaded[0]["processed_count"] == 2


def test_empty_scan_not_persisted(project_root: Path) -> None:
    entries = append_ingest_entry(project_root, scan_result=_make_empty_result())
    assert len(entries) == 0

    path = project_root / PROFILE_DIR / INGEST_HISTORY_FILE
    assert not path.exists()


def test_fifo_ordering(project_root: Path) -> None:
    for i in range(1, 4):
        append_ingest_entry(project_root, scan_result=_make_result(items_count=i))

    entries = load_ingest_history(project_root)
    assert len(entries) == 3
    assert entries[0]["processed_count"] == 3
    assert entries[1]["processed_count"] == 2
    assert entries[2]["processed_count"] == 1


def test_fifo_cap(project_root: Path) -> None:
    for i in range(MAX_ENTRIES + 5):
        append_ingest_entry(project_root, scan_result=_make_result(items_count=i + 1))

    entries = load_ingest_history(project_root)
    assert len(entries) == MAX_ENTRIES
    assert entries[0]["processed_count"] == MAX_ENTRIES + 5


def test_file_written_to_profile_dir(project_root: Path) -> None:
    append_ingest_entry(project_root, scan_result=_make_result(items_count=1))
    path = project_root / PROFILE_DIR / INGEST_HISTORY_FILE
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["max_entries"] == MAX_ENTRIES
    assert len(data["entries"]) == 1


def test_corrupted_file_returns_empty(project_root: Path) -> None:
    path = project_root / PROFILE_DIR / INGEST_HISTORY_FILE
    path.write_text("not valid json", encoding="utf-8")
    entries = load_ingest_history(project_root)
    assert entries == []


def test_error_only_scan_is_persisted(project_root: Path) -> None:
    result = {
        "project_id": "p1",
        "processed_count": 0,
        "failed_count": 1,
        "items": [],
        "errors": [{"filename": "bad.pdf", "path": "/tmp/bad.pdf", "error": "parse error"}],
    }
    entries = append_ingest_entry(project_root, scan_result=result)
    assert len(entries) == 1
    assert entries[0]["failed_count"] == 1
