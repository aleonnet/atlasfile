from __future__ import annotations

from pathlib import Path
from typing import Any

from .profile_runtime import areas_root_rel, resolve_area_folder_name


def resolve_area_path(
    *,
    project_root: Path,
    profile: dict[str, Any],
    area_key: str,
    create_if_missing: bool = True,
) -> str | None:
    area = next((a for a in profile.get("work_areas", []) if a.get("key") == area_key), None)
    if not area:
        return None

    areas_root = areas_root_rel(profile)
    explicit_path = area.get("path")
    if explicit_path:
        dest = project_root / explicit_path
        if create_if_missing:
            dest.mkdir(parents=True, exist_ok=True)
        return explicit_path

    folder_name = resolve_area_folder_name(profile, area_key)
    rel = f"{areas_root}/{folder_name}"
    folder_path = project_root / rel
    if create_if_missing:
        folder_path.mkdir(parents=True, exist_ok=True)
    return rel
