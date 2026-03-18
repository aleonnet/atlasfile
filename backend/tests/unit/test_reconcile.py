"""Unit tests for app.reconcile (parse index, ignore, migration)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from opensearchpy import OpenSearch

from app.reconcile import (
    _is_ignored_file,
    _parse_index_rows,
    _project_scope_query,
    _try_migrate_old_format,
    reconcile_project_index,
    sync_search_index_for_project,
)
from app.utils import sha256_file


def _minimal_profile(project_root: Path | None = None) -> dict[str, Any]:
    return {
        "project_id": "test_proj",
        "classification": {
            "work_areas": [
                {"key": "financeiro", "jd_number": 4, "aliases": []},
                {"key": "juridica", "jd_number": 2, "aliases": []},
            ],
        },
        "layout": {
            "mode": "para_jd",
            "roots": {
                "projects": "01_PROJECTS",
                "areas": "02_AREAS",
                "resources": "03_RESOURCES",
                "archive": "04_ARCHIVE",
            },
            "areas_root": "02_AREAS",
            "area_folders": [
                {"area_key": "financeiro", "folder": "04_financeiro"},
                {"area_key": "juridica", "folder": "02_juridica"},
            ],
        },
        "paths": {
            "inbox": "_INBOX_DROP",
            "triage": {
                "pending": "_TRIAGE_REVIEW/pending",
                "resolved": "_TRIAGE_REVIEW/resolved",
                "rejected": "_TRIAGE_REVIEW/rejected",
            },
        },
        "naming": {
            "canonical_pattern": "{date}__{project}__{original_name}",
            "date_format": "%Y%m%d",
        },
    }


def _two_level_profile() -> dict[str, Any]:
    return {
        "project_id": "test_proj",
        "business_domains": [
            {"key": "financeiro", "folder": "financeiro"},
        ],
        "classification": {
            "document_types": [
                {"key": "contrato", "folder": "contrato"},
            ],
        },
        "layout": {
            "roots": {
                "projects": "01_PROJECTS",
                "areas": "02_AREAS",
                "resources": "03_RESOURCES",
                "archive": "04_ARCHIVE",
            },
            "areas_root": "02_AREAS",
            "business_domain_folders": [
                {"business_domain": "financeiro", "folder": "financeiro"},
            ],
        },
        "paths": {
            "triage": {
                "pending": "_TRIAGE_REVIEW/pending",
                "resolved": "_TRIAGE_REVIEW/resolved",
                "rejected": "_TRIAGE_REVIEW/rejected",
            },
        },
        "naming": {
            "canonical_pattern": "{date}__{project}__{original_name}",
            "date_format": "%Y%m%d",
        },
    }


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
        f.write("| doc_id | project_id | area | orig | canon | decision | conf | path | naming_pattern |\n")
        f.write("|---|\n")
        f.write("| id1 | proj1 | ativos | f.pdf | 20260101__proj1__f__v01.pdf | auto | 0.95 | proj1/02_AREAS/03_ativos/f.pdf | {date}__{project}__{original_name} |\n")
        path = Path(f.name)
    try:
        rows = _parse_index_rows(path)
        assert len(rows) == 1
        assert rows[0]["doc_id"] == "id1"
        assert rows[0]["project_id"] == "proj1"
        assert rows[0]["path"] == "proj1/02_AREAS/03_ativos/f.pdf"
        assert rows[0]["naming_pattern"] == "{date}__{project}__{original_name}"
    finally:
        path.unlink(missing_ok=True)


def test_parse_index_rows_legacy_without_naming_pattern() -> None:
    """Legacy _INDEX.md rows without naming_pattern column get empty string fallback."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("| doc_id | project_id | area | orig | canon | decision | conf | path |\n")
        f.write("|---|\n")
        f.write("| id1 | proj1 | ativos | f.pdf | 20260101__proj1__f__v01.pdf | auto | 0.95 | some/path |\n")
        path = Path(f.name)
    try:
        rows = _parse_index_rows(path)
        assert len(rows) == 1
        assert rows[0]["naming_pattern"] == ""
    finally:
        path.unlink(missing_ok=True)


def test_project_scope_query_includes_project_id_and_path_prefix() -> None:
    query = _project_scope_query("Kaidô", Path("/projects/Kaidô"))
    should = query["bool"]["should"]
    assert {"term": {"project_id": "Kaidô"}} in should
    assert {"prefix": {"path": "/projects/Kaidô/"}} in should


# ── _try_migrate_old_format ──


def test_migrate_old_format_renames_file(tmp_path: Path) -> None:
    profile = _minimal_profile()
    old_name = "20260302__test_proj__financeiro__contrato__v01.pdf"
    old_file = tmp_path / old_name
    old_file.write_bytes(b"test")

    result = _try_migrate_old_format(old_file, profile)

    assert result is not None
    assert result.name == "20260302__test_proj__contrato__v01.pdf"
    assert result.exists()
    assert not old_file.exists()


def test_migrate_old_format_skips_new_format(tmp_path: Path) -> None:
    profile = _minimal_profile()
    new_name = "20260302__test_proj__contrato__v01.pdf"
    new_file = tmp_path / new_name
    new_file.write_bytes(b"test")

    result = _try_migrate_old_format(new_file, profile)
    assert result is None
    assert new_file.exists()


def test_migrate_old_format_skips_non_canonical(tmp_path: Path) -> None:
    profile = _minimal_profile()
    plain_file = tmp_path / "plain_document.pdf"
    plain_file.write_bytes(b"test")

    result = _try_migrate_old_format(plain_file, profile)
    assert result is None


def test_migrate_old_format_skips_unknown_area(tmp_path: Path) -> None:
    profile = _minimal_profile()
    old_name = "20260302__test_proj__unknown_area__doc__v01.pdf"
    old_file = tmp_path / old_name
    old_file.write_bytes(b"test")

    result = _try_migrate_old_format(old_file, profile)
    assert result is None
    assert old_file.exists()


def test_migrate_old_format_skips_collision(tmp_path: Path) -> None:
    profile = _minimal_profile()
    old_name = "20260302__test_proj__financeiro__doc__v01.pdf"
    old_file = tmp_path / old_name
    old_file.write_bytes(b"old")
    # Pre-create destination to trigger collision
    collision = tmp_path / "20260302__test_proj__doc__v01.pdf"
    collision.write_bytes(b"existing")

    result = _try_migrate_old_format(old_file, profile)
    assert result is None
    assert old_file.exists()
    assert collision.exists()


# ── reconcile original_filename reconstruction ──


def test_reconcile_reconstructs_original_filename(tmp_path: Path) -> None:
    """When no _INDEX.md prev exists, original_filename is extracted from canonical name."""
    profile = _minimal_profile(tmp_path)
    areas_dir = tmp_path / "02_AREAS" / "04_financeiro"
    areas_dir.mkdir(parents=True)
    canonical = "20260302__test_proj__DocuSign_Report__v01.pdf"
    (areas_dir / canonical).write_bytes(b"content")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        result = reconcile_project_index(tmp_path, profile)

    index_text = (tmp_path / "_INDEX.md").read_text(encoding="utf-8")
    assert "DocuSign_Report.pdf" in index_text


# ── PARA roots scan ──


def test_reconcile_scans_all_para_roots(tmp_path: Path) -> None:
    """Files in 01_PROJECTS, 03_RESOURCES, 04_ARCHIVE are included in _INDEX.md."""
    profile = _minimal_profile()

    for folder in ("01_PROJECTS", "02_AREAS/04_financeiro", "03_RESOURCES", "04_ARCHIVE"):
        (tmp_path / folder).mkdir(parents=True)

    (tmp_path / "01_PROJECTS" / "project_plan.pdf").write_bytes(b"p")
    (tmp_path / "02_AREAS" / "04_financeiro" / "invoice.pdf").write_bytes(b"i")
    (tmp_path / "03_RESOURCES" / "reference.pdf").write_bytes(b"r")
    (tmp_path / "04_ARCHIVE" / "old_report.pdf").write_bytes(b"a")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        reconcile_project_index(tmp_path, profile)

    index_text = (tmp_path / "_INDEX.md").read_text(encoding="utf-8")
    assert "project_plan.pdf" in index_text
    assert "invoice.pdf" in index_text
    assert "reference.pdf" in index_text
    assert "old_report.pdf" in index_text

    data_lines = [
        ln for ln in index_text.splitlines()
        if ln.startswith("| ") and "---" not in ln and "doc_id" not in ln
    ]
    assert len(data_lines) == 4


def test_reconcile_para_roots_area_key(tmp_path: Path) -> None:
    """Non-areas roots use their PARA category as area_key; areas root infers from subfolder."""
    profile = _minimal_profile()

    for folder in ("01_PROJECTS", "02_AREAS/04_financeiro", "03_RESOURCES", "04_ARCHIVE"):
        (tmp_path / folder).mkdir(parents=True)

    (tmp_path / "01_PROJECTS" / "plan.pdf").write_bytes(b"p")
    (tmp_path / "02_AREAS" / "04_financeiro" / "nf.pdf").write_bytes(b"i")
    (tmp_path / "03_RESOURCES" / "ref.pdf").write_bytes(b"r")
    (tmp_path / "04_ARCHIVE" / "old.pdf").write_bytes(b"a")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        reconcile_project_index(tmp_path, profile)

    index_text = (tmp_path / "_INDEX.md").read_text(encoding="utf-8")
    for line in index_text.splitlines():
        if "plan.pdf" in line:
            assert "| projects |" in line
        elif "nf.pdf" in line:
            assert "| financeiro |" in line
        elif "ref.pdf" in line:
            assert "| resources |" in line
        elif "old.pdf" in line:
            assert "| archive |" in line


def test_reconcile_no_legacy_work_scan(tmp_path: Path) -> None:
    """_WORK/ folder is no longer scanned (legacy fallback removed)."""
    profile = _minimal_profile()
    (tmp_path / "02_AREAS").mkdir(parents=True)
    legacy = tmp_path / "_WORK"
    legacy.mkdir(parents=True)
    (legacy / "ghost.pdf").write_bytes(b"should not appear")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        reconcile_project_index(tmp_path, profile)

    index_text = (tmp_path / "_INDEX.md").read_text(encoding="utf-8")
    assert "ghost.pdf" not in index_text


# ── naming_pattern per-file ──


def test_reconcile_writes_naming_pattern_column(tmp_path: Path) -> None:
    """Each row in _INDEX.md includes the naming_pattern used to generate the file."""
    profile = _minimal_profile()
    areas_dir = tmp_path / "02_AREAS" / "04_financeiro"
    areas_dir.mkdir(parents=True)
    (areas_dir / "20260302__test_proj__relatorio__v01.pdf").write_bytes(b"x")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        reconcile_project_index(tmp_path, profile)

    index_text = (tmp_path / "_INDEX.md").read_text(encoding="utf-8")
    assert "| naming_pattern |" in index_text
    data_lines = [
        ln for ln in index_text.splitlines()
        if ln.startswith("| ") and "---" not in ln and "doc_id" not in ln
    ]
    assert len(data_lines) == 1
    cols = [c.strip() for c in data_lines[0].strip().strip("|").split("|")]
    assert len(cols) >= 9
    assert cols[8] == "{date}__{project}__{original_name}"


def test_reconcile_preserves_old_naming_pattern_on_rerun(tmp_path: Path) -> None:
    """When profile pattern changes, existing rows keep their original naming_pattern."""
    profile = _minimal_profile()
    areas_dir = tmp_path / "02_AREAS" / "04_financeiro"
    areas_dir.mkdir(parents=True)
    (areas_dir / "20260302__test_proj__relatorio__v01.pdf").write_bytes(b"x")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        reconcile_project_index(tmp_path, profile)

    # Change the profile naming pattern
    profile["naming"]["canonical_pattern"] = "{date}__{original_name}"

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        reconcile_project_index(tmp_path, profile)

    index_text = (tmp_path / "_INDEX.md").read_text(encoding="utf-8")
    data_lines = [
        ln for ln in index_text.splitlines()
        if ln.startswith("| ") and "---" not in ln and "doc_id" not in ln
    ]
    assert len(data_lines) == 1
    cols = [c.strip() for c in data_lines[0].strip().strip("|").split("|")]
    # Should preserve the original pattern, not the new one
    assert cols[8] == "{date}__{project}__{original_name}"


def test_reconcile_mixed_patterns_correct_original_filename(tmp_path: Path) -> None:
    """Files generated with different patterns are parsed correctly using per-file pattern."""
    profile = _minimal_profile()
    areas_dir = tmp_path / "02_AREAS" / "04_financeiro"
    areas_dir.mkdir(parents=True)

    # File 1: generated with default pattern {date}__{project}__{original_name}
    (areas_dir / "20260302__test_proj__relatorio__v01.pdf").write_bytes(b"x")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        reconcile_project_index(tmp_path, profile)

    # Change pattern and add a new file with the new pattern
    profile["naming"]["canonical_pattern"] = "{date}__{original_name}"
    (areas_dir / "20260303__contrato_final__v01.pdf").write_bytes(b"y")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        reconcile_project_index(tmp_path, profile)

    index_text = (tmp_path / "_INDEX.md").read_text(encoding="utf-8")
    data_lines = [
        ln for ln in index_text.splitlines()
        if ln.startswith("| ") and "---" not in ln and "doc_id" not in ln
    ]
    assert len(data_lines) == 2
    by_canonical = {}
    for ln in data_lines:
        cols = [c.strip() for c in ln.strip().strip("|").split("|")]
        by_canonical[cols[4]] = {
            "original_filename": cols[3],
            "naming_pattern": cols[8] if len(cols) > 8 else "",
        }

    # File 1: parsed with its stored pattern
    f1 = by_canonical["20260302__test_proj__relatorio__v01.pdf"]
    assert f1["original_filename"] == "relatorio.pdf"
    assert f1["naming_pattern"] == "{date}__{project}__{original_name}"

    # File 2: parsed with the new pattern
    f2 = by_canonical["20260303__contrato_final__v01.pdf"]
    assert f2["original_filename"] == "contrato_final.pdf"
    assert f2["naming_pattern"] == "{date}__{original_name}"


def test_sync_search_reindexes_same_sha_when_document_type_missing(tmp_path: Path) -> None:
    profile = _two_level_profile()
    contract_dir = tmp_path / "02_AREAS" / "financeiro" / "contrato"
    contract_dir.mkdir(parents=True)
    file_path = contract_dir / "20260302__test_proj__Contrato TI__v01.pdf"
    file_path.write_bytes(b"contract")

    (tmp_path / "_INDEX.md").write_text(
        "\n".join(
            [
                "# _INDEX",
                "",
                "| doc_id | project_id | area | original_filename | canonical_filename | decision | confidence | path | naming_pattern |",
                "|---|---|---|---|---|---|---:|---|---|",
                f"| doc-1 | test_proj | financeiro | Contrato TI.pdf | {file_path.name} | auto | 0.90 | {file_path} | {{date}}__{{project}}__{{original_name}} |",
                "",
            ]
        ),
        encoding="utf-8",
    )

    current_sha = sha256_file(file_path)
    client = MagicMock()
    client.search.return_value = {"hits": {"hits": [{"_id": "doc-1"}]}}
    client.get.return_value = {
        "_source": {
            "sha256": current_sha,
            "project_id": "test_proj",
            "business_domain": "financeiro",
            "document_type": "",
        }
    }

    with (
        patch("app.reconcile.ensure_index"),
        patch("app.reconcile.index_document") as mock_index_document,
    ):
        report = sync_search_index_for_project(
            client,
            tmp_path,
            "test_proj",
            profile=profile,
        )

    assert report["indexed_docs"] == 1
    assert report["skipped_docs"] == 0
    payload = mock_index_document.call_args.args[1]
    assert payload["business_domain"] == "financeiro"
    assert payload["document_type"] == "contrato"
    assert payload["tags"] == ["financeiro", "contrato"]


# ── cleanup_orphans flag in run_reconcile ──


def test_per_project_reconcile_does_not_cleanup_orphans() -> None:
    """When cleanup_orphans=False, cleanup_orphan_projects must NOT be called.

    This prevents single-project reconciliation from deleting docs of other projects.
    """
    from threading import Lock
    from unittest.mock import MagicMock

    from app.services.reconcile_service import run_reconcile

    mock_client = MagicMock()
    mock_client.indices.exists.return_value = True
    mock_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    status: dict[str, Any] = {}

    with (
        patch("app.services.reconcile_service.load_project_profile", return_value=_minimal_profile()),
        patch("app.services.reconcile_service.ensure_project_structure"),
        patch("app.services.reconcile_service.reconcile_project_index", return_value={"rows_written": 0, "added_rows": 0, "removed_rows": 0, "adjustments_applied": 0}),
        patch("app.services.reconcile_service.sync_search_index_for_project", return_value={"indexed_docs": 0, "deleted_docs": 0, "skipped_docs": 0, "failed_docs": 0}),
        patch("app.services.reconcile_service.cleanup_orphan_projects") as mock_cleanup,
    ):
        run_reconcile(
            project_roots=[Path("/fake/project_a")],
            reindex_search=True,
            reindex_mode="incremental",
            status=status,
            lock=Lock(),
            os_client=mock_client,
            cleanup_orphans=False,
        )

    mock_cleanup.assert_not_called()


def test_full_reconcile_runs_cleanup_orphans() -> None:
    """When cleanup_orphans=True (default), cleanup_orphan_projects IS called."""
    from threading import Lock
    from unittest.mock import MagicMock

    from app.services.reconcile_service import run_reconcile

    mock_client = MagicMock()
    mock_client.indices.exists.return_value = True
    mock_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    status: dict[str, Any] = {}

    with (
        patch("app.services.reconcile_service.load_project_profile", return_value=_minimal_profile()),
        patch("app.services.reconcile_service.ensure_project_structure"),
        patch("app.services.reconcile_service.reconcile_project_index", return_value={"rows_written": 0, "added_rows": 0, "removed_rows": 0, "adjustments_applied": 0}),
        patch("app.services.reconcile_service.sync_search_index_for_project", return_value={"indexed_docs": 0, "deleted_docs": 0, "skipped_docs": 0, "failed_docs": 0}),
        patch("app.services.reconcile_service.cleanup_orphan_projects", return_value={"orphan_projects_found": 0, "orphan_docs_deleted": 0}) as mock_cleanup,
    ):
        run_reconcile(
            project_roots=[Path("/fake/project_a"), Path("/fake/project_b")],
            reindex_search=True,
            reindex_mode="incremental",
            status=status,
            lock=Lock(),
            os_client=mock_client,
            cleanup_orphans=True,
        )

    mock_cleanup.assert_called_once()
