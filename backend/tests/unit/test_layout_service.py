"""Unit tests for layout_service.py — migration plan generation."""
from __future__ import annotations

from pathlib import Path

from app.layout_service import _is_system_file, plan_layout_migration
from app.profile_schema_v2 import ProjectProfileV2


def _make_profile(project_root: Path, area_folders: list[dict]) -> ProjectProfileV2:
    normalized_folders = area_folders or [{"area_key": "general", "folder": "00_general"}]
    domain_keys = [str(row["area_key"]) for row in normalized_folders]
    default_domain = domain_keys[0]
    return ProjectProfileV2(
        project_id="test",
        project_label="Test",
        project_root=str(project_root),
        layout={
            "mode": "para_jd",
            "roots": {"projects": "01_PROJECTS", "areas": "02_AREAS", "resources": "03_RESOURCES", "archive": "04_ARCHIVE"},
            "areas_root": "02_AREAS",
            "area_folders": normalized_folders,
        },
        classification={
            "work_areas": [{"key": key, "aliases": [key]} for key in domain_keys],
            "business_domains": [{"key": key, "label": key.title(), "aliases": [key]} for key in domain_keys],
            "document_types": [
                {
                    "key": "relatorio",
                    "label": "Relatório",
                    "aliases": ["relatorio"],
                    "extensions": [".pdf", ".txt"],
                    "folder": "relatorio",
                    "fallback_priority": 10,
                }
            ],
            "document_type_priors": {"relatorio": {"default": default_domain, "weight": 0.2}},
            "entity_domain_affinity": {"sample": {"domain": default_domain, "weight": 0.2}},
            "context_boosts": [],
            "thresholds": {
                "document_type_extension_bonus": 0.08,
                "document_type_alias_confidence_base": 0.35,
                "document_type_alias_confidence_scale": 0.6,
                "document_type_confidence_cap": 0.96,
                "document_type_best_effort_confidence": 0.25,
                "business_domain_lexical_scale": 0.75,
                "business_domain_lexical_cap": 0.85,
                "business_domain_context_boost_cap": 0.35,
                "business_domain_alias_fallback_confidence": 0.2,
                "business_domain_best_effort_confidence": 0.05,
                "entity_boost_profiles": {"default": {"cap": 0.45, "scale": 0.5}},
            },
            "routing_rules": [],
            "confidence_thresholds": {"auto_route_min": 0.85, "triage_min": 0.5},
            "llm_policy": {},
        },
    )


def test_system_files_are_excluded_from_plan(tmp_path: Path) -> None:
    """System files should not appear in any op when iterating loose files."""
    project = tmp_path / "proj"
    areas = project / "02_AREAS"
    areas.mkdir(parents=True)
    (areas / ".DS_Store").write_bytes(b"x")
    (areas / "doc.pdf").write_bytes(b"pdf")

    old = _make_profile(project, [])
    new_p = _make_profile(project, [])
    new_p.layout.areas_root = "02_AREAS_NEW"

    plan = plan_layout_migration(old_profile=old, new_profile=new_p, strategy="rename_with_suffix")
    sources = [op.src for op in plan.ops if op.op == "move"]
    assert any("doc.pdf" in s for s in sources)
    assert not any(".DS_Store" in (s or "") for s in sources)


def test_src_equals_dst_produces_no_move(tmp_path: Path) -> None:
    """When areas_root is unchanged and a file has no area match, src == dst → skip."""
    project = tmp_path / "proj"
    areas = project / "02_AREAS"
    areas.mkdir(parents=True)
    (areas / "orphan.txt").write_text("x")

    old = _make_profile(project, [])
    new = _make_profile(project, [])

    plan = plan_layout_migration(old_profile=old, new_profile=new, strategy="rename_with_suffix")
    assert plan.moves == 0
    assert plan.conflicts == 0


def test_rmdir_empty_only_for_actually_empty_dirs(tmp_path: Path) -> None:
    """rmdir_empty should only appear for dirs whose real files are all being moved."""
    project = tmp_path / "proj"
    areas = project / "02_AREAS"
    (areas / "01_legal").mkdir(parents=True)
    (areas / "01_legal" / "doc.pdf").write_bytes(b"pdf")
    (areas / "02_finance").mkdir(parents=True)
    (areas / "03_empty").mkdir(parents=True)

    old = _make_profile(project, [
        {"area_key": "legal", "folder": "01_legal"},
        {"area_key": "finance", "folder": "02_finance"},
        {"area_key": "empty", "folder": "03_empty"},
    ])
    # Remove "empty" from new profile; keep others the same
    new = _make_profile(project, [
        {"area_key": "legal", "folder": "01_legal"},
        {"area_key": "finance", "folder": "02_finance"},
    ])

    plan = plan_layout_migration(old_profile=old, new_profile=new, strategy="rename_with_suffix", cleanup_empty_dirs=True)
    rmdir_dirs = [op.src for op in plan.ops if op.op == "rmdir_empty"]
    # 03_empty should be in the list (it's empty and has no remaining content)
    assert any("03_empty" in (d or "") for d in rmdir_dirs)
    # 01_legal has doc.pdf which stays in place (src==dst), so it should NOT be rmdir'd
    assert not any("01_legal" in (d or "") for d in rmdir_dirs)


def test_rename_folder_uses_rename_dir(tmp_path: Path) -> None:
    """Renaming an area_folder generates rename_dir, not mkdir + moves."""
    project = tmp_path / "proj"
    areas = project / "02_AREAS" / "01_legal"
    areas.mkdir(parents=True)
    (areas / "a.pdf").write_bytes(b"a")
    (areas / "b.pdf").write_bytes(b"b")

    old = _make_profile(project, [{"area_key": "legal", "folder": "01_legal"}])
    new = _make_profile(project, [{"area_key": "legal", "folder": "renamed_legal"}])

    plan = plan_layout_migration(old_profile=old, new_profile=new, strategy="rename_with_suffix")
    assert plan.renames == 1
    assert plan.moves == 0
    assert plan.mkdirs == 0
    rename_ops = [op for op in plan.ops if op.op == "rename_dir"]
    assert len(rename_ops) == 1
    assert "01_legal" in (rename_ops[0].src or "")
    assert "renamed_legal" in (rename_ops[0].dst or "")


def test_remove_folder_with_files_shows_conflicts(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    areas = project / "02_AREAS" / "01_legal"
    areas.mkdir(parents=True)
    (areas / "important.pdf").write_bytes(b"data")

    old = _make_profile(project, [{"area_key": "legal", "folder": "01_legal"}])
    new = _make_profile(project, [])

    plan = plan_layout_migration(old_profile=old, new_profile=new, strategy="rename_with_suffix")
    assert plan.conflicts >= 1
    assert any("no new folder" in op.reason for op in plan.ops if op.op == "conflict")


def test_rename_fallback_to_move_when_dst_exists(tmp_path: Path) -> None:
    """If new folder already exists on disk, can't rename — falls back to moves."""
    project = tmp_path / "proj"
    old_dir = project / "02_AREAS" / "01_legal"
    old_dir.mkdir(parents=True)
    (old_dir / "a.pdf").write_bytes(b"a")
    # Pre-create the new dir so rename is not eligible
    new_dir = project / "02_AREAS" / "renamed_legal"
    new_dir.mkdir(parents=True)

    old = _make_profile(project, [{"area_key": "legal", "folder": "01_legal"}])
    new = _make_profile(project, [{"area_key": "legal", "folder": "renamed_legal"}])

    plan = plan_layout_migration(old_profile=old, new_profile=new, strategy="rename_with_suffix")
    assert plan.renames == 0
    assert plan.moves >= 1


def test_is_system_file_detects_hidden_and_known() -> None:
    assert _is_system_file(Path(".DS_Store"))
    assert _is_system_file(Path(".hidden"))
    assert _is_system_file(Path("Thumbs.db"))
    assert not _is_system_file(Path("document.pdf"))
    assert not _is_system_file(Path("readme.txt"))
