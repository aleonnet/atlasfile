"""Tests for template_store CRUD operations with dual-root (builtin + user)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.template_store import (
    BUILTIN_DIR,
    DEFAULT_SLUG,
    create_profile_from_template,
    delete_template,
    get_template,
    list_templates,
    save_template,
)

SAMPLE_TEMPLATE_DATA = {
    "template_meta": {"slug": "test_tmpl", "name": "Test", "description": "A test template"},
    "profile_version": 2,
    "project_id": "__PROJECT_ID__",
    "project_label": "__PROJECT_LABEL__",
    "project_root": "__PROJECT_ROOT__",
    "paths": {"inbox": "_INBOX_DROP", "triage": {"pending": "p", "resolved": "r", "rejected": "j"}},
    "layout": {
        "mode": "para_jd",
        "roots": {"projects": "01", "areas": "02", "resources": "03", "archive": "04"},
        "areas_root": "02",
        "area_folders": [{"area_key": "test_area", "folder": "01_test"}],
    },
    "classification": {
        "work_areas": [{"key": "test_area", "jd_number": 1, "aliases": ["test"]}],
        "routing_rules": [],
        "confidence_thresholds": {"auto_route_min": 0.85, "triage_min": 0.5},
        "llm_policy": {
            "enabled": False, "provider": "openai", "model": "gpt-4o-mini", "mode": "tag_only",
            "allow_override_fields": [], "override_guardrails": {
                "area_override_only_if_rule_confidence_below": 0.65,
                "require_explanation": True, "max_area_changes": 1,
            },
        },
    },
    "indexing": {"topics_path": "config/topics_v1.yaml", "extraction_max_chars": 50000, "extraction_mode": "all"},
    "version": 1,
}


def test_list_templates_returns_default():
    templates = list_templates()
    slugs = [t["slug"] for t in templates]
    assert DEFAULT_SLUG in slugs
    default = next(t for t in templates if t["slug"] == DEFAULT_SLUG)
    assert default["source"] == "builtin"


def test_get_template_default():
    tmpl = get_template(DEFAULT_SLUG)
    assert tmpl["slug"] == DEFAULT_SLUG
    assert "profile" in tmpl
    assert tmpl["areas_count"] > 0
    assert tmpl["source"] == "builtin"


def test_get_template_not_found():
    with pytest.raises(FileNotFoundError):
        get_template("nonexistent_template_xyz")


def test_save_to_user_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.template_store._user_dir", lambda: tmp_path)
    meta = save_template("test_tmpl", {**SAMPLE_TEMPLATE_DATA})
    assert meta["slug"] == "test_tmpl"
    assert meta["name"] == "Test"
    assert meta["areas_count"] == 1
    assert meta["source"] == "user"
    assert (tmp_path / "test_tmpl.json").exists()


def test_user_template_overrides_builtin(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.template_store._user_dir", lambda: tmp_path)
    user_data = {**SAMPLE_TEMPLATE_DATA, "template_meta": {"slug": DEFAULT_SLUG, "name": "Custom Default"}}
    save_template(DEFAULT_SLUG, user_data)
    tmpl = get_template(DEFAULT_SLUG)
    assert tmpl["source"] == "user"
    assert tmpl["name"] == "Custom Default"


def test_list_merges_builtin_and_user(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.template_store._user_dir", lambda: tmp_path)
    save_template("custom_tmpl", {**SAMPLE_TEMPLATE_DATA, "template_meta": {"slug": "custom_tmpl", "name": "Custom"}})
    templates = list_templates()
    slugs = [t["slug"] for t in templates]
    assert DEFAULT_SLUG in slugs
    assert "custom_tmpl" in slugs
    custom = next(t for t in templates if t["slug"] == "custom_tmpl")
    assert custom["source"] == "user"


def test_delete_template_protects_default():
    with pytest.raises(ValueError, match="Cannot delete"):
        delete_template(DEFAULT_SLUG)


def test_delete_builtin_not_allowed(tmp_path: Path, monkeypatch):
    """Non-default builtin templates cannot be deleted via user dir."""
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    (builtin / "shipped.json").write_text(json.dumps({"template_meta": {"slug": "shipped"}, "classification": {"work_areas": []}}))
    monkeypatch.setattr("app.template_store.BUILTIN_DIR", builtin)
    user = tmp_path / "user"
    user.mkdir()
    monkeypatch.setattr("app.template_store._user_dir", lambda: user)
    with pytest.raises(ValueError, match="Cannot delete.*built-in"):
        delete_template("shipped")


def test_delete_template_not_found(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.template_store._user_dir", lambda: tmp_path)
    with pytest.raises(FileNotFoundError):
        delete_template("nonexistent_xyz_999")


def test_delete_user_template(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.template_store._user_dir", lambda: tmp_path)
    save_template("to_delete", {**SAMPLE_TEMPLATE_DATA, "template_meta": {"slug": "to_delete"}})
    assert (tmp_path / "to_delete.json").exists()
    delete_template("to_delete")
    assert not (tmp_path / "to_delete.json").exists()


def test_create_profile_from_template():
    profile = create_profile_from_template(
        DEFAULT_SLUG,
        project_root=Path("/tmp/TestProject"),
        project_id="TestProject",
        project_label="Test Project",
    )
    assert profile.project_id == "TestProject"
    assert profile.project_label == "Test Project"
    assert len(profile.classification.work_areas) > 0


def test_create_profile_from_user_template(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.template_store._user_dir", lambda: tmp_path)
    save_template("custom", {**SAMPLE_TEMPLATE_DATA, "template_meta": {"slug": "custom", "name": "Custom"}})
    profile = create_profile_from_template(
        "custom",
        project_root=Path("/tmp/CustomProject"),
        project_id="CustomProject",
        project_label="Custom Project",
    )
    assert profile.project_id == "CustomProject"
    assert len(profile.classification.work_areas) == 1
