from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def parse_frontmatter_md(md_path: Path) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Arquivo sem frontmatter YAML: {md_path}")

    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError(f"Frontmatter invalido: {md_path}")

    yaml_text = text[4:end]
    data = yaml.safe_load(yaml_text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Frontmatter deve ser objeto YAML: {md_path}")
    return data


def load_project_profile(project_root: Path) -> dict[str, Any]:
    profile_path = project_root / "_PROJECT_PROFILE.md"
    if not profile_path.exists():
        raise FileNotFoundError(f"_PROJECT_PROFILE.md nao encontrado em {project_root}")
    profile = parse_frontmatter_md(profile_path)
    profile["_profile_path"] = str(profile_path)
    return profile


def list_project_roots(projects_root: Path) -> list[Path]:
    if not projects_root.exists():
        return []
    return sorted([p for p in projects_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
