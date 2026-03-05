from __future__ import annotations

from pathlib import Path
from typing import Any

from .profile_schema_v2 import ProjectProfileV2
from .profile_store import PROFILE_DIR, PROFILE_FILE, load_profile


def _routing_rule_to_dict(rule: Any) -> dict[str, Any]:
    data = rule.model_dump(mode="json")
    if data.get("when_path_contains") is None:
        data.pop("when_path_contains", None)
    if data.get("when_filename_contains") is None:
        data.pop("when_filename_contains", None)
    return data


def profile_v2_to_runtime(profile: ProjectProfileV2, project_root: Path) -> dict[str, Any]:
    area_folder_map = {af.area_key: af.folder for af in profile.layout.area_folders}
    work_areas: list[dict[str, Any]] = []
    for area in profile.classification.work_areas:
        work_areas.append(
            {
                "key": area.key,
                "jd_number": area.jd_number,
                "aliases": list(area.aliases),
                "folder": area_folder_map.get(area.key),
            }
        )

    return {
        "project_id": profile.project_id,
        "project_label": profile.project_label,
        "project_root": profile.project_root,
        "inbox_path": profile.paths.inbox,
        "triage_path": profile.paths.triage.pending,
        "triage_paths": profile.paths.triage.model_dump(mode="json"),
        "work_root": profile.layout.areas_root,
        "work_areas": work_areas,
        "routing_rules": [_routing_rule_to_dict(r) for r in profile.classification.routing_rules],
        "confidence_thresholds": profile.classification.confidence_thresholds.model_dump(mode="json"),
        "llm_policy": profile.classification.llm_policy.model_dump(mode="json"),
        "layout": profile.layout.model_dump(mode="json"),
        "paths": profile.paths.model_dump(mode="json"),
        "classification": profile.classification.model_dump(mode="json"),
        "indexing": profile.indexing.model_dump(mode="json"),
        "version": profile.version,
        "_profile_path": str(project_root / PROFILE_DIR / PROFILE_FILE),
    }


def load_project_profile(project_root: Path) -> dict[str, Any]:
    profile = load_profile(project_root)
    return profile_v2_to_runtime(profile, project_root)


_HIDDEN_DIRS = {"_ATLASFILE", ".DS_Store"}


def list_project_roots(projects_root: Path) -> list[Path]:
    if not projects_root.exists():
        return []
    return sorted(
        [p for p in projects_root.iterdir() if p.is_dir() and p.name not in _HIDDEN_DIRS],
        key=lambda p: p.name.lower(),
    )
