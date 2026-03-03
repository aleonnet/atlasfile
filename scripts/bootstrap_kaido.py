from __future__ import annotations

from pathlib import Path


KAIDO_ROOT = Path("/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/Kaidô")

PROJECT_PROFILE = """---
project_id: kaido_upi_tahto
project_label: "Kaidô - Implantação UPI Tahto"
project_root: "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/Kaidô"
inbox_path: "_INBOX_DROP"
triage_path: "_TRIAGE_REVIEW/pending"
work_root: "_WORK"

work_areas:
  - key: societario_fiscal
    jd_number: 1
    aliases: ["societario", "fiscal", "cnpj", "filiais", "incorporacao", "estabelecimentos"]
  - key: juridica
    jd_number: 2
    aliases: ["juridico", "passivo", "contingencia", "parecer", "juridica"]
  - key: ativos
    jd_number: 3
    aliases: ["ativo", "imobilizado", "cmdb", "segregacao_ativos", "doacao"]
  - key: financeiro
    jd_number: 4
    aliases: ["carveout", "cp", "contabil", "seguros", "garantias", "fianca", "fiscal"]
  - key: contratos_comunicacao
    jd_number: 5
    aliases: ["contrato", "fornecedor", "cliente", "comunicacao", "preâmbulo", "eml"]
  - key: pessoas
    jd_number: 6
    aliases: ["colaborador", "rh", "beneficio", "hc", "organograma", "gerencia", "diretoria"]
  - key: sistemas_migracao
    jd_number: 7
    aliases: ["sistema", "plataforma", "migracao_sistemas", "sap"]
  - key: processos_tsa
    jd_number: 8
    aliases: ["tsa", "sox", "processo_operacional", "atendimento", "pos-closing"]
  - key: entregaveis
    jd_number: 9
    aliases: ["output", "visao_consolidada", "framework_3ps", "inventario", "metricas", "escopo"]

routing_rules:
  - when_path_contains: ["output/"]
    route_to: "entregaveis"
    confidence: 0.98
  - when_filename_contains: ["contrato", "fornecedor", "cliente", "preâmbulo"]
    route_to: "contratos_comunicacao"
    confidence: 0.9
  - when_filename_contains: ["filiais", "cnpj", "estabelecimentos"]
    route_to: "societario_fiscal"
    confidence: 0.9
  - when_filename_contains: ["cmdb", "ativo", "imobilizado", "doação"]
    route_to: "ativos"
    confidence: 0.9
  - when_filename_contains: ["colaboradores", "organograma", "gh_"]
    route_to: "pessoas"
    confidence: 0.9

confidence_thresholds:
  auto_route_min: 0.85
  triage_min: 0.5
---

# Kaidô Project Profile

Perfil de classificacao do projeto Kaidô para uso pelo motor AtlasFile.
"""


def main() -> None:
    KAIDO_ROOT.mkdir(parents=True, exist_ok=True)

    for rel in [
        "_INBOX_DROP",
        "_TRIAGE_REVIEW/pending",
        "_TRIAGE_REVIEW/resolved",
        "_TRIAGE_REVIEW/rejected",
        "_WORK",
        "_WORK/01_societario_fiscal",
        "_WORK/02_juridica",
        "_WORK/03_ativos",
        "_WORK/04_financeiro",
        "_WORK/05_contratos_comunicacao",
        "_WORK/06_pessoas",
        "_WORK/07_sistemas_migracao",
        "_WORK/08_processos_tsa",
        "_WORK/09_entregaveis",
    ]:
        (KAIDO_ROOT / rel).mkdir(parents=True, exist_ok=True)

    (KAIDO_ROOT / "_PROJECT_PROFILE.md").write_text(PROJECT_PROFILE, encoding="utf-8")

    index_path = KAIDO_ROOT / "_INDEX.md"
    if not index_path.exists():
        index_path.write_text(
            "# _INDEX\n\n"
            "| doc_id | project_id | area | original_filename | canonical_filename | decision | confidence | path |\n"
            "|---|---|---|---|---|---|---:|---|\n",
            encoding="utf-8",
        )

    print(f"OK: projeto Kaidô inicializado em {KAIDO_ROOT}")


if __name__ == "__main__":
    main()
