from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROJECTS_ROOT = Path("/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects")


def slugify(value: str) -> str:
    out = value.strip().lower()
    out = out.replace(" ", "_")
    out = out.replace("-", "_")
    return "".join(ch for ch in out if ch.isalnum() or ch == "_").strip("_")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_default_template() -> dict:
    template_path = _repo_root() / "config" / "templates" / "profile_v2_default.json"
    raw = template_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Template invalido: {template_path}")
    return data


def build_profile(*, project_id: str, project_label: str, project_root: Path) -> dict:
    profile = _load_default_template()
    profile["project_id"] = project_id
    profile["project_label"] = project_label
    profile["project_root"] = str(project_root)
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    profile["updated_by"] = "bootstrap_project.py"
    profile["version"] = 1
    return profile


def bootstrap_project(
    *,
    projects_root: Path,
    project_dir_name: str,
    project_id: str,
    project_label: str,
) -> Path:
    project_root = projects_root / project_dir_name
    project_root.mkdir(parents=True, exist_ok=True)

    profile = build_profile(
        project_id=project_id,
        project_label=project_label,
        project_root=project_root,
    )

    dirs_to_create = [
        profile["paths"]["inbox"],
        profile["paths"]["triage"]["pending"],
        profile["paths"]["triage"]["resolved"],
        profile["paths"]["triage"]["rejected"],
        profile["layout"]["areas_root"],
        "_PROFILE/history",
    ]
    roots = profile.get("layout", {}).get("roots", {})
    for root_dir in roots.values():
        if root_dir and root_dir not in dirs_to_create:
            dirs_to_create.append(root_dir)
    for rel in dirs_to_create:
        (project_root / rel).mkdir(parents=True, exist_ok=True)

    areas_root = project_root / profile["layout"]["areas_root"]
    for af in profile["layout"].get("area_folders", []):
        folder = af.get("folder")
        if folder:
            (areas_root / folder).mkdir(parents=True, exist_ok=True)

    profile_path = project_root / "_PROFILE" / "profile.json"
    profile_json = json.dumps(profile, ensure_ascii=False, indent=2)
    profile_path.write_text(profile_json, encoding="utf-8")

    history_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ__v01.json")
    (project_root / "_PROFILE" / "history" / history_name).write_text(profile_json, encoding="utf-8")

    index_path = project_root / "_INDEX.md"
    if not index_path.exists():
        index_path.write_text(
            "# _INDEX\n\n"
            "| doc_id | project_id | area | original_filename | canonical_filename | decision | confidence | path |\n"
            "|---|---|---|---|---|---|---:|---|\n",
            encoding="utf-8",
        )

    return project_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap de projeto AtlasFile com template estilo Kaidô")
    parser.add_argument("--name", required=True, help='Nome da pasta do projeto, ex: "kaidô_teste"')
    parser.add_argument("--id", default=None, help='ID do projeto, ex: "kaido_teste"')
    parser.add_argument("--label", default=None, help='Label legivel do projeto')
    parser.add_argument("--projects-root", default=str(DEFAULT_PROJECTS_ROOT), help="Raiz de projetos")
    args = parser.parse_args()

    project_name = args.name
    project_id = args.id or slugify(project_name)
    project_label = args.label or project_name
    projects_root = Path(args.projects_root)

    root = bootstrap_project(
        projects_root=projects_root,
        project_dir_name=project_name,
        project_id=project_id,
        project_label=project_label,
    )
    print(f"OK: projeto inicializado em {root}")
    print(f"project_id={project_id}")


if __name__ == "__main__":
    main()
