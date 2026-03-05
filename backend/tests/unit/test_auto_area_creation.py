"""Tests for _ensure_area_in_profile auto-area creation logic."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.main import _ensure_area_in_profile
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


def test_existing_area_unchanged(tmp_project):
    project_root, profile = tmp_project
    original_count = len(profile["classification"]["work_areas"])
    result = _ensure_area_in_profile(project_root, profile, "financeiro")
    assert len(result["classification"]["work_areas"]) == original_count


def test_new_area_added_to_work_areas(tmp_project):
    project_root, profile = tmp_project
    original_count = len(profile["classification"]["work_areas"])
    result = _ensure_area_in_profile(project_root, profile, "esg_sustentabilidade")
    assert len(result["classification"]["work_areas"]) == original_count + 1
    new_area = next(a for a in result["classification"]["work_areas"] if a["key"] == "esg_sustentabilidade")
    assert new_area["jd_number"] > 0
    assert "esg sustentabilidade" in new_area["aliases"]


def test_new_area_added_to_area_folders(tmp_project):
    project_root, profile = tmp_project
    result = _ensure_area_in_profile(project_root, profile, "esg_sustentabilidade")
    folders = result["layout"]["area_folders"]
    folder = next(f for f in folders if f["area_key"] == "esg_sustentabilidade")
    assert "esg_sustentabilidade" in folder["folder"]


def test_profile_version_incremented(tmp_project):
    project_root, profile = tmp_project
    original_version = profile["version"]
    result = _ensure_area_in_profile(project_root, profile, "esg_sustentabilidade")
    assert result["version"] > original_version


def test_profile_persisted_to_disk(tmp_project):
    project_root, profile = tmp_project
    _ensure_area_in_profile(project_root, profile, "nova_area_teste")
    disk_profile = json.loads((project_root / "_PROFILE" / "profile.json").read_text())
    keys = [a["key"] for a in disk_profile["classification"]["work_areas"]]
    assert "nova_area_teste" in keys


def test_jd_number_is_sequential(tmp_project):
    project_root, profile = tmp_project
    max_jd = max(a.get("jd_number", 0) for a in profile["classification"]["work_areas"])
    result = _ensure_area_in_profile(project_root, profile, "area_x")
    new_area = next(a for a in result["classification"]["work_areas"] if a["key"] == "area_x")
    assert new_area["jd_number"] == max_jd + 1
