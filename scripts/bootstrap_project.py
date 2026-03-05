#!/usr/bin/env python3
"""Bootstrap de projeto AtlasFile via CLI.

Reutiliza os mesmos módulos do backend (profile_store, bootstrap) para
garantir que o profile.json, history e estrutura de pastas sejam idênticos
ao que a API /api/projects/{id}/initialize produz.

Uso:
    python3 scripts/bootstrap_project.py --name "meu_projeto"
    python3 scripts/bootstrap_project.py --name "meu_projeto" --template default
    python3 scripts/bootstrap_project.py --name "due_diligence" --label "Due Diligence Alfa" --template default
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.profile_store import ensure_profile, load_profile  # noqa: E402
from app.project_profile import profile_v2_to_runtime  # noqa: E402
from app.bootstrap import ensure_project_structure  # noqa: E402

DEFAULT_PROJECTS_ROOT = Path(
    os.environ.get("PROJECTS_HOST_ROOT", str(Path.home() / "Documents" / "Projects"))
)


def _slugify(value: str) -> str:
    out = value.strip().lower().replace(" ", "_").replace("-", "_")
    return "".join(ch for ch in out if ch.isalnum() or ch == "_").strip("_")


def bootstrap_project(
    *,
    projects_root: Path,
    project_dir_name: str,
    project_id: str,
    project_label: str,
    template_slug: str = "default",
) -> Path:
    project_root = projects_root / project_dir_name
    project_root.mkdir(parents=True, exist_ok=True)

    profile, created = ensure_profile(
        project_root=project_root,
        project_id=project_id,
        project_label=project_label,
        template_slug=template_slug,
    )

    runtime = profile_v2_to_runtime(profile, project_root)
    ensure_project_structure(project_root, runtime)

    status = "criado" if created else "já existia"
    print(f"OK: projeto inicializado em {project_root} (profile {status})")
    print(f"  project_id = {profile.project_id}")
    print(f"  template   = {template_slug}")
    print(f"  version    = {profile.version}")
    return project_root


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap de projeto AtlasFile (usa os mesmos módulos do backend)"
    )
    parser.add_argument("--name", required=True, help="Nome da pasta do projeto")
    parser.add_argument("--id", default=None, help="ID do projeto (default: slugify do name)")
    parser.add_argument("--label", default=None, help="Label legível do projeto")
    parser.add_argument("--template", default="default", help="Slug do template (default: default)")
    parser.add_argument(
        "--projects-root",
        default=str(DEFAULT_PROJECTS_ROOT),
        help=f"Raiz de projetos (default: {DEFAULT_PROJECTS_ROOT})",
    )
    args = parser.parse_args()

    bootstrap_project(
        projects_root=Path(args.projects_root),
        project_dir_name=args.name,
        project_id=args.id or _slugify(args.name),
        project_label=args.label or args.name,
        template_slug=args.template,
    )


if __name__ == "__main__":
    main()
