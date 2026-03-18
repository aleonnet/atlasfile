"""Tests for strict profile validation in triage helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.main import _ensure_area_in_profile, _ensure_document_type_in_profile
from app.profile_store import create_default_profile, save_profile


@pytest.fixture()
def tmp_project(tmp_path: Path):
    project_root = tmp_path / "TestProject"
    project_root.mkdir()
    profile_model = create_default_profile(
        project_root=project_root,
        project_id="TestProject",
        project_label="Test Project",
    )
    saved = save_profile(project_root=project_root, profile=profile_model, updated_by="test:init")
    profile_dict = saved.model_dump(mode="json")
    return project_root, profile_dict


def test_existing_area_is_accepted(tmp_project):
    project_root, profile = tmp_project
    result = _ensure_area_in_profile(project_root, profile, "financeiro")
    assert result is profile


def test_missing_area_raises_error(tmp_project):
    project_root, profile = tmp_project
    with pytest.raises(ValueError, match="business_domain not configured"):
        _ensure_area_in_profile(project_root, profile, "esg_sustentabilidade")


def test_existing_document_type_is_accepted(tmp_project):
    project_root, profile = tmp_project
    result = _ensure_document_type_in_profile(project_root, profile, "contrato")
    assert result is profile


def test_missing_document_type_raises_error(tmp_project):
    project_root, profile = tmp_project
    with pytest.raises(ValueError, match="document_type not configured"):
        _ensure_document_type_in_profile(project_root, profile, "memorando")
