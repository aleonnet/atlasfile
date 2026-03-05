"""Unit tests for app.reconcile (parse index, ignore)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.reconcile import _is_ignored_file, _parse_index_rows, _project_scope_query


def test_is_ignored_file() -> None:
    assert _is_ignored_file(Path(".git/config")) is True
    assert _is_ignored_file(Path("a/.x/file")) is True
    assert _is_ignored_file(Path("normal/path/file.pdf")) is False


def test_parse_index_rows_missing_file() -> None:
    assert _parse_index_rows(Path("/nonexistent/_INDEX.md")) == []


def test_parse_index_rows_empty() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("| doc_id | project_id | area | ...\n")
        f.write("|---|\n")
        path = Path(f.name)
    try:
        rows = _parse_index_rows(path)
        assert rows == []
    finally:
        path.unlink(missing_ok=True)


def test_parse_index_rows_valid_row() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        # Header with < 8 columns so it is skipped by parser (len(cols) < 8)
        f.write("| doc_id | project_id | area | orig | canon | decision | conf\n")
        f.write("|---|\n")
        f.write("| id1 | proj1 | ativos | f.pdf | 20260101__p__ativos__f__v01.pdf | auto | 0.95 | proj1/_WORK/03_ativos/f.pdf |\n")
        path = Path(f.name)
    try:
        rows = _parse_index_rows(path)
        assert len(rows) == 1
        assert rows[0]["doc_id"] == "id1"
        assert rows[0]["project_id"] == "proj1"
        assert rows[0]["path"] == "proj1/_WORK/03_ativos/f.pdf"
    finally:
        path.unlink(missing_ok=True)


def test_project_scope_query_includes_project_id_and_path_prefix() -> None:
    query = _project_scope_query("Kaidô", Path("/projects/Kaidô"))
    should = query["bool"]["should"]
    assert {"term": {"project_id": "Kaidô"}} in should
    assert {"prefix": {"path": "/projects/Kaidô/"}} in should
