from __future__ import annotations

from pathlib import Path
from typing import Any

from .area_resolver import resolve_area_path
from .profile_runtime import areas_root_rel, inbox_rel, triage_paths


def ensure_project_structure(project_root: Path, profile: dict[str, Any]) -> None:
    triage = triage_paths(profile)
    (project_root / inbox_rel(profile)).mkdir(parents=True, exist_ok=True)
    (project_root / triage["pending"]).mkdir(parents=True, exist_ok=True)
    (project_root / triage["resolved"]).mkdir(parents=True, exist_ok=True)
    (project_root / triage["rejected"]).mkdir(parents=True, exist_ok=True)
    (project_root / areas_root_rel(profile)).mkdir(parents=True, exist_ok=True)
    (project_root / "_PROFILE" / "history").mkdir(parents=True, exist_ok=True)

    roots = (profile.get("layout") or {}).get("roots", {})
    for root_dir in roots.values():
        if root_dir:
            (project_root / root_dir).mkdir(parents=True, exist_ok=True)

    for area in profile.get("work_areas", []):
        area_key = area.get("key")
        if area_key:
            resolve_area_path(project_root=project_root, profile=profile, area_key=area_key, create_if_missing=True)

    index_path = project_root / "_INDEX.md"
    if not index_path.exists():
        index_path.write_text(
            "# _INDEX\n\n"
            "| doc_id | project_id | area | original_filename | canonical_filename | decision | confidence | path |\n"
            "|---|---|---|---|---|---|---:|---|\n",
            encoding="utf-8",
        )
