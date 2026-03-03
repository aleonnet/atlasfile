from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .utils import sanitize_token


AREA_DIR_RE = re.compile(r"^(\d{2})_(.+)$")


def _existing_jd_dirs(work_root: Path) -> list[tuple[int, Path]]:
    dirs: list[tuple[int, Path]] = []
    if not work_root.exists():
        return dirs
    for child in work_root.iterdir():
        if not child.is_dir():
            continue
        m = AREA_DIR_RE.match(child.name)
        if not m:
            continue
        dirs.append((int(m.group(1)), child))
    return sorted(dirs, key=lambda x: x[0])


def _next_jd_number(work_root: Path) -> int:
    used = {n for n, _ in _existing_jd_dirs(work_root)}
    if not used:
        return 1
    candidate = max(used) + 1
    if candidate <= 98 and candidate not in used:
        return candidate
    for n in range(1, 99):
        if n not in used:
            return n
    raise ValueError("Sem numeros JD disponiveis em _WORK")


def resolve_area_path(
    *,
    project_root: Path,
    profile: dict[str, Any],
    area_key: str,
    create_if_missing: bool = True,
) -> str | None:
    work_root_rel = profile.get("work_root", "_WORK")
    work_root = project_root / work_root_rel
    work_root.mkdir(parents=True, exist_ok=True)

    area = next((a for a in profile.get("work_areas", []) if a.get("key") == area_key), None)
    if not area:
        return None

    explicit_path = area.get("path")
    if explicit_path:
        dest = project_root / explicit_path
        if create_if_missing:
            dest.mkdir(parents=True, exist_ok=True)
        return explicit_path

    token = sanitize_token(area_key)

    # Reuso de pasta ja existente para a mesma area (por slug no sufixo)
    for _, folder in _existing_jd_dirs(work_root):
        suffix = AREA_DIR_RE.match(folder.name).group(2)  # type: ignore[union-attr]
        if suffix == token:
            return f"{work_root_rel}/{folder.name}"

    # Respeita numero preferencial do profile quando disponivel
    jd_number = area.get("jd_number")
    if isinstance(jd_number, int) and 1 <= jd_number <= 98:
        candidate_name = f"{jd_number:02d}_{token}"
        candidate_path = work_root / candidate_name
        if create_if_missing:
            candidate_path.mkdir(parents=True, exist_ok=True)
        return f"{work_root_rel}/{candidate_name}"

    # fallback dinamico: usa proximo numero disponivel no padrao JD
    number = _next_jd_number(work_root)
    folder_name = f"{number:02d}_{token}"
    folder_path = work_root / folder_name
    if create_if_missing:
        folder_path.mkdir(parents=True, exist_ok=True)
    return f"{work_root_rel}/{folder_name}"
