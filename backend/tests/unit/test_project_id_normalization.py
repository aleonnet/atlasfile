"""Tests for project_id normalization (strip accents + lowercase)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils import extract_original_name_from_canonical, normalize_text


def test_normalize_text_strips_accents_and_lowercases():
    assert normalize_text("kaidô_teste") == "kaido_teste"
    assert normalize_text("Kaidô_Teste") == "kaido_teste"
    assert normalize_text("KAIDO_TESTE") == "kaido_teste"
    assert normalize_text("São_Paulo") == "sao_paulo"
    assert normalize_text("plain_text") == "plain_text"


def test_reconcile_normalizes_accented_project_id(tmp_path):
    """reconcile_project_index normalizes project_id from profile."""
    from app.reconcile import reconcile_project_index

    profile = {"project_id": "kaidô_teste", "work_areas": [], "version": 2}
    (tmp_path / "_INDEX.md").write_text("")

    with patch("app.reconcile.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        result = reconcile_project_index(tmp_path, profile)

    assert result["project_id"] == "kaido_teste"


def test_create_default_profile_normalizes_project_id(tmp_path):
    """create_default_profile normalizes project_id but preserves label."""
    from app.profile_store import create_default_profile

    profile = create_default_profile(
        project_root=tmp_path,
        project_id="Kaidô_Teste",
        project_label="Kaidô Teste",
        template_slug="default",
    )
    assert profile.project_id == "kaido_teste"
    assert profile.project_label == "Kaidô Teste"


def test_create_default_profile_preserves_label(tmp_path):
    """project_label keeps original accents even when project_id is normalized."""
    from app.profile_store import create_default_profile

    profile = create_default_profile(
        project_root=tmp_path,
        project_id="São_Paulo",
        project_label="São Paulo",
        template_slug="default",
    )
    assert profile.project_id == "sao_paulo"
    assert profile.project_label == "São Paulo"


def test_project_scope_filter_includes_normalized_variant():
    """_project_scope_filter adds normalized variant to aliases."""
    from fastapi import HTTPException

    from app.main import _project_scope_filter

    with patch("app.main._resolve_project_root", side_effect=HTTPException(status_code=404)):
        result = _project_scope_filter("kaidô_teste")

    assert "bool" in result
    should_clauses = result["bool"]["should"]
    term_values = {c["term"]["project_id"] for c in should_clauses if "term" in c}
    assert "kaidô_teste" in term_values
    assert "kaido_teste" in term_values


def test_project_scope_filter_uppercase_resolves():
    """_project_scope_filter normalizes uppercase to lowercase."""
    from fastapi import HTTPException

    from app.main import _project_scope_filter

    with patch("app.main._resolve_project_root", side_effect=HTTPException(status_code=404)):
        result = _project_scope_filter("KAIDO_TESTE")

    assert "bool" in result
    should_clauses = result["bool"]["should"]
    term_values = {c["term"]["project_id"] for c in should_clauses if "term" in c}
    assert "KAIDO_TESTE" in term_values
    assert "kaido_teste" in term_values


def test_project_scope_filter_space_to_underscore():
    """_project_scope_filter adds underscore variant for space-separated input."""
    from fastapi import HTTPException

    from app.main import _project_scope_filter

    with patch("app.main._resolve_project_root", side_effect=HTTPException(status_code=404)):
        result = _project_scope_filter("kaido teste")

    assert "bool" in result
    should_clauses = result["bool"]["should"]
    term_values = {c["term"]["project_id"] for c in should_clauses if "term" in c}
    assert "kaido teste" in term_values
    assert "kaido_teste" in term_values


def test_project_scope_filter_underscore_to_space():
    """_project_scope_filter adds space variant for underscore-separated input."""
    from fastapi import HTTPException

    from app.main import _project_scope_filter

    with patch("app.main._resolve_project_root", side_effect=HTTPException(status_code=404)):
        result = _project_scope_filter("kaido_teste")

    assert "bool" in result
    should_clauses = result["bool"]["should"]
    term_values = {c["term"]["project_id"] for c in should_clauses if "term" in c}
    assert "kaido_teste" in term_values
    assert "kaido teste" in term_values


def test_project_scope_filter_accent_plus_space():
    """_project_scope_filter handles accented input with spaces, generating all variants."""
    from fastapi import HTTPException

    from app.main import _project_scope_filter

    with patch("app.main._resolve_project_root", side_effect=HTTPException(status_code=404)):
        result = _project_scope_filter("kaidô teste")

    assert "bool" in result
    should_clauses = result["bool"]["should"]
    term_values = {c["term"]["project_id"] for c in should_clauses if "term" in c}
    assert "kaidô teste" in term_values
    assert "kaido teste" in term_values
    assert "kaidô_teste" in term_values
    assert "kaido_teste" in term_values


def test_resolve_project_root_normalized_input(tmp_path):
    """_resolve_project_root finds accented folder when input is the normalized (no-accent) form."""
    from app.main import _resolve_project_root

    accented_dir = tmp_path / "kaidô_teste"
    accented_dir.mkdir()
    profile_dir = accented_dir / "_PROFILE"
    profile_dir.mkdir()
    import json

    (profile_dir / "profile.json").write_text(
        json.dumps({"profile_version": 2, "project_id": "kaidô_teste", "version": 2})
    )

    with patch("app.main.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        result = _resolve_project_root("kaido_teste")

    assert result == accented_dir


def test_resolve_project_root_space_input(tmp_path):
    """_resolve_project_root finds underscore folder when input uses spaces."""
    from app.main import _resolve_project_root

    proj_dir = tmp_path / "kaido_teste"
    proj_dir.mkdir()
    profile_dir = proj_dir / "_PROFILE"
    profile_dir.mkdir()
    import json

    (profile_dir / "profile.json").write_text(
        json.dumps({"profile_version": 2, "project_id": "kaido_teste", "version": 2})
    )

    with patch("app.main.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        result = _resolve_project_root("kaido teste")

    assert result == proj_dir


def test_resolve_project_root_exact_match_preferred(tmp_path):
    """_resolve_project_root prefers exact folder name match over normalized."""
    from app.main import _resolve_project_root

    exact_dir = tmp_path / "kaido_teste"
    exact_dir.mkdir()

    with patch("app.main.settings") as mock_settings:
        mock_settings.projects_root = str(tmp_path)
        result = _resolve_project_root("kaido_teste")

    assert result == exact_dir


# ── extract_original_name_from_canonical ──


def test_extract_original_preserves_accents_and_case():
    """Canonical filename with accented original_name is correctly extracted."""
    canonical = "20260302__kaido__Relatório_Final__v01.pdf"
    result = extract_original_name_from_canonical(canonical)
    assert result == "Relatório_Final.pdf"


def test_extract_original_with_double_underscores_in_name():
    """Original names containing __ are preserved during extraction."""
    canonical = "20260302__proj__Doc___SPA__Anexos__v02.xlsx"
    result = extract_original_name_from_canonical(canonical)
    assert result == "Doc___SPA__Anexos.xlsx"
