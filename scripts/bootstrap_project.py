from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_PROJECTS_ROOT = Path("/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects")


TEMPLATE_AREAS = [
    ("societario_fiscal", 1, ["societario", "fiscal", "cnpj", "filiais", "incorporacao", "estabelecimentos"]),
    ("juridica", 2, ["juridico", "passivo", "contingencia", "parecer", "juridica"]),
    ("ativos", 3, ["ativo", "imobilizado", "cmdb", "segregacao_ativos", "doacao"]),
    ("financeiro", 4, ["carveout", "cp", "contabil", "seguros", "garantias", "fianca", "fiscal"]),
    ("contratos_comunicacao", 5, ["contrato", "fornecedor", "cliente", "comunicacao", "preambulo", "eml"]),
    ("pessoas", 6, ["colaborador", "rh", "beneficio", "hc", "organograma", "gerencia", "diretoria"]),
    ("sistemas_migracao", 7, ["sistema", "plataforma", "migracao_sistemas", "sap"]),
    ("processos_tsa", 8, ["tsa", "sox", "processo_operacional", "atendimento", "pos-closing"]),
    ("entregaveis", 9, ["output", "visao_consolidada", "framework_3ps", "inventario", "metricas", "escopo"]),
]


def slugify(value: str) -> str:
    out = value.strip().lower()
    out = out.replace(" ", "_")
    out = out.replace("-", "_")
    return "".join(ch for ch in out if ch.isalnum() or ch == "_").strip("_")


def build_profile(
    *,
    project_id: str,
    project_label: str,
    project_root: Path,
) -> str:
    areas_yaml = []
    for key, jd_number, aliases in TEMPLATE_AREAS:
        alias_yaml = ", ".join(f'"{a}"' for a in aliases)
        areas_yaml.append(
            f'  - key: {key}\n'
            f"    jd_number: {jd_number}\n"
            f"    aliases: [{alias_yaml}]"
        )
    areas_block = "\n".join(areas_yaml)

    return f"""---
project_id: {project_id}
project_label: "{project_label}"
project_root: "{project_root}"
inbox_path: "_INBOX_DROP"
triage_path: "_TRIAGE_REVIEW/pending"
work_root: "_WORK"

work_areas:
{areas_block}

routing_rules:
  - when_path_contains: ["output/"]
    route_to: "entregaveis"
    confidence: 0.98
  - when_filename_contains: ["contrato", "fornecedor", "cliente", "preambulo"]
    route_to: "contratos_comunicacao"
    confidence: 0.9
  - when_filename_contains: ["filiais", "cnpj", "estabelecimentos"]
    route_to: "societario_fiscal"
    confidence: 0.9
  - when_filename_contains: ["cmdb", "ativo", "imobilizado", "doacao"]
    route_to: "ativos"
    confidence: 0.9
  - when_filename_contains: ["colaboradores", "organograma", "gh_"]
    route_to: "pessoas"
    confidence: 0.9

confidence_thresholds:
  auto_route_min: 0.85
  triage_min: 0.5
---

# Project Profile

Perfil de classificacao do projeto para uso pelo motor AtlasFile.
"""


def bootstrap_project(
    *,
    projects_root: Path,
    project_dir_name: str,
    project_id: str,
    project_label: str,
) -> Path:
    project_root = projects_root / project_dir_name
    project_root.mkdir(parents=True, exist_ok=True)

    for rel in [
        "_INBOX_DROP",
        "_TRIAGE_REVIEW/pending",
        "_TRIAGE_REVIEW/resolved",
        "_TRIAGE_REVIEW/rejected",
        "_WORK",
    ]:
        (project_root / rel).mkdir(parents=True, exist_ok=True)

    for key, jd_number, _ in TEMPLATE_AREAS:
        (project_root / f"_WORK/{jd_number:02d}_{key}").mkdir(parents=True, exist_ok=True)

    profile_content = build_profile(
        project_id=project_id,
        project_label=project_label,
        project_root=project_root,
    )
    (project_root / "_PROJECT_PROFILE.md").write_text(profile_content, encoding="utf-8")

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
