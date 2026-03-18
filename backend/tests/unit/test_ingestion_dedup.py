"""Unit tests for early duplicate detection in ingestion."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion import (
    _find_original_in_search_index,
    _find_original_in_triage,
    process_inbox_file,
)


def _minimal_profile(project_root: Path) -> dict[str, Any]:
    return {
        "project_id": "test_dedup",
        "work_areas": [{"key": "juridica"}],
        "layout": {
            "mode": "para_jd",
            "para_roots": {"projects": "01_PROJECTS", "areas": "02_AREAS", "resources": "03_RESOURCES", "archive": "04_ARCHIVE"},
            "areas_root": "02_AREAS",
            "area_folders": [{"area_key": "juridica", "folder": "juridica"}],
            "business_domain_folders": [{"business_domain": "juridica", "folder": "juridica"}],
        },
        "paths": {
            "inbox": "_INBOX_DROP",
            "triage": {"pending": "_TRIAGE_REVIEW/pending", "resolved": "_TRIAGE_REVIEW/resolved", "rejected": "_TRIAGE_REVIEW/rejected"},
            "profile_dir": "_PROFILE",
        },
        "classification": {
            "business_domains": [{"key": "juridica", "aliases": ["juridica"], "folder": "juridica"}],
            "document_types": [{"key": "contrato", "aliases": ["contrato"], "extensions": [".pdf"], "folder": "contrato"}],
            "llm_policy": {"enabled": False},
        },
        "confidence_thresholds": {"auto_route_min": 0.85, "triage_min": 0.5},
    }


def _write_file(path: Path, content: bytes = b"test content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ── _find_original_in_triage ──


def test_find_original_in_triage_returns_match(tmp_path: Path) -> None:
    profile = _minimal_profile(tmp_path)
    pending_dir = tmp_path / "_TRIAGE_REVIEW" / "pending"
    pending_dir.mkdir(parents=True)
    meta = {"doc_id": "orig-001", "sha256": "abc123", "area_key": "juridica"}
    (pending_dir / "orig-001.json").write_text(json.dumps(meta))

    result = _find_original_in_triage(tmp_path, profile, "abc123")
    assert result is not None
    assert result["doc_id"] == "orig-001"


def test_find_original_in_triage_returns_none_when_no_match(tmp_path: Path) -> None:
    profile = _minimal_profile(tmp_path)
    pending_dir = tmp_path / "_TRIAGE_REVIEW" / "pending"
    pending_dir.mkdir(parents=True)

    result = _find_original_in_triage(tmp_path, profile, "no-match")
    assert result is None


def test_find_original_in_triage_searches_all_subdirs(tmp_path: Path) -> None:
    profile = _minimal_profile(tmp_path)
    rejected_dir = tmp_path / "_TRIAGE_REVIEW" / "rejected"
    rejected_dir.mkdir(parents=True)
    meta = {"doc_id": "orig-rej", "sha256": "rej_sha", "suggested_area": "juridica"}
    (rejected_dir / "orig-rej.json").write_text(json.dumps(meta))

    result = _find_original_in_triage(tmp_path, profile, "rej_sha")
    assert result is not None
    assert result["doc_id"] == "orig-rej"


# ── _find_original_in_search_index ──


def test_find_original_in_index_returns_source() -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "hits": {
            "hits": [{"_source": {"doc_id": "idx-001", "area_key": "juridica", "sha256": "sha_x"}}]
        }
    }
    result = _find_original_in_search_index(mock_client, "proj1", "sha_x")
    assert result is not None
    assert result["doc_id"] == "idx-001"


def test_find_original_in_index_returns_none_on_empty() -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {"hits": {"hits": []}}
    result = _find_original_in_search_index(mock_client, "proj1", "no_match")
    assert result is None


def test_find_original_in_index_returns_none_on_exception() -> None:
    mock_client = MagicMock()
    mock_client.search.side_effect = Exception("connection error")
    result = _find_original_in_search_index(mock_client, "proj1", "sha_x")
    assert result is None


# ── process_inbox_file: early dedup ──


@patch("app.ingestion.ensure_project_structure")
@patch("app.ingestion.sha256_file", return_value="dup_sha256")
@patch("app.ingestion._find_original_in_triage")
def test_process_inbox_file_dedup_deletes_inbox_file(
    mock_find_triage: MagicMock,
    mock_sha: MagicMock,
    mock_ensure: MagicMock,
    tmp_path: Path,
) -> None:
    """When a duplicate is found, the inbox file is deleted and the original info is returned."""
    mock_find_triage.return_value = {
        "doc_id": "original-doc-id",
        "area_key": "juridica",
        "title": "Contrato",
        "canonical_filename": "test__contrato_v01.pdf",
        "path": "/some/path/contrato.pdf",
        "confidence_score": 0.95,
        "tags": ["juridica"],
    }
    inbox_file = _write_file(tmp_path / "_INBOX_DROP" / "contrato.pdf", b"dup content")
    profile = _minimal_profile(tmp_path)
    mock_client = MagicMock()

    result = process_inbox_file(
        client=mock_client,
        project_root=tmp_path,
        profile=profile,
        inbox_file=inbox_file,
    )

    assert result["decision"] == "duplicate"
    assert result["duplicate_of"] == "original-doc-id"
    assert result["doc_id"] == "original-doc-id"
    assert not inbox_file.exists(), "Inbox file should be deleted on duplicate"


@patch("app.ingestion.ensure_project_structure")
@patch("app.ingestion.sha256_file", return_value="dup_sha256")
@patch("app.ingestion._find_original_in_triage", return_value=None)
@patch("app.ingestion._find_original_in_search_index")
def test_process_inbox_file_dedup_via_search_index(
    mock_find_index: MagicMock,
    mock_find_triage: MagicMock,
    mock_sha: MagicMock,
    mock_ensure: MagicMock,
    tmp_path: Path,
) -> None:
    """Falls back to OpenSearch index when triage has no match."""
    mock_find_index.return_value = {
        "doc_id": "idx-orig",
        "area_key": "financeiro",
        "title": "Fatura",
        "confidence_score": 0.88,
        "tags": ["financeiro"],
    }
    inbox_file = _write_file(tmp_path / "_INBOX_DROP" / "fatura.pdf", b"dup content")
    profile = _minimal_profile(tmp_path)
    mock_client = MagicMock()

    result = process_inbox_file(
        client=mock_client,
        project_root=tmp_path,
        profile=profile,
        inbox_file=inbox_file,
    )

    assert result["decision"] == "duplicate"
    assert result["duplicate_of"] == "idx-orig"
    assert not inbox_file.exists()


@patch("app.ingestion.ensure_project_structure")
@patch("app.ingestion.sha256_file", return_value="unique_sha")
@patch("app.ingestion._find_original_in_triage", return_value=None)
@patch("app.ingestion._find_original_in_search_index", return_value=None)
@patch("app.ingestion.classify_bootstrap")
@patch("app.ingestion.read_text_excerpt", return_value="excerpt text")
@patch("app.ingestion.index_document")
@patch("app.ingestion._append_index_md")
def test_process_inbox_file_non_dup_proceeds_to_classification(
    mock_append: MagicMock,
    mock_index: MagicMock,
    mock_excerpt: MagicMock,
    mock_classify: MagicMock,
    mock_find_index: MagicMock,
    mock_find_triage: MagicMock,
    mock_sha: MagicMock,
    mock_ensure: MagicMock,
    tmp_path: Path,
) -> None:
    """Non-duplicate files go through the full classification pipeline."""
    mock_classify.return_value = {
        "business_domain": "juridica",
        "area_key": "juridica",
        "document_type": "contrato",
        "document_type_confidence": 0.96,
        "business_domain_confidence": 0.92,
        "confidence": 0.92,
        "reason": "alias_match",
        "top_candidates": [{"area_key": "juridica", "score": 0.92}],
    }
    inbox_file = _write_file(tmp_path / "_INBOX_DROP" / "new_doc.pdf", b"unique content")
    profile = _minimal_profile(tmp_path)
    (tmp_path / "02_AREAS" / "juridica").mkdir(parents=True)
    mock_client = MagicMock()

    result = process_inbox_file(
        client=mock_client,
        project_root=tmp_path,
        profile=profile,
        inbox_file=inbox_file,
    )

    assert result["decision"] == "auto"
    assert result["area_key"] == "juridica"
    assert "duplicate_of" not in result
    mock_index.assert_called_once()
    mock_append.assert_called_once()


@patch("app.ingestion.ensure_project_structure")
@patch("app.ingestion.sha256_file", return_value="dup_sha256")
@patch("app.ingestion._find_original_in_triage")
def test_process_inbox_file_dedup_no_new_json_or_index_entry(
    mock_find_triage: MagicMock,
    mock_sha: MagicMock,
    mock_ensure: MagicMock,
    tmp_path: Path,
) -> None:
    """Duplicate detection must NOT create new metadata JSON or _INDEX.md entries."""
    mock_find_triage.return_value = {
        "doc_id": "orig-123",
        "area_key": "juridica",
        "confidence_score": 0.9,
        "tags": ["juridica"],
    }
    inbox_file = _write_file(tmp_path / "_INBOX_DROP" / "dup.pdf", b"dup")
    profile = _minimal_profile(tmp_path)
    mock_client = MagicMock()

    # Directories where old code would write
    rejected_dir = tmp_path / "_TRIAGE_REVIEW" / "rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)
    index_md = tmp_path / "_INDEX.md"

    result = process_inbox_file(
        client=mock_client,
        project_root=tmp_path,
        profile=profile,
        inbox_file=inbox_file,
    )

    assert result["decision"] == "duplicate"
    # No new JSON files created in rejected
    json_files = list(rejected_dir.glob("*.json"))
    assert len(json_files) == 0, f"No metadata JSON should be created for dups, found: {json_files}"
    # No _INDEX.md created/appended
    assert not index_md.exists(), "_INDEX.md should not be written for duplicates"
