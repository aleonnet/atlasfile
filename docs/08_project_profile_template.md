# Template de profile de projeto (V2)

O profile de cada projeto é armazenado em `_PROFILE/profile.json` no formato JSON, seguindo o schema `ProjectProfileV2` definido em `backend/app/profile_schema_v2.py`.

Templates globais ficam em `config/templates/` e são usados na inicialização de novos projetos.

## Exemplo completo

```json
{
  "profile_version": 2,
  "project_id": "example_project",
  "project_label": "Example Project",
  "project_root": "/projects/example_project",

  "paths": {
    "inbox": "_INBOX_DROP",
    "triage": {
      "pending": "_TRIAGE_REVIEW/pending",
      "resolved": "_TRIAGE_REVIEW/resolved",
      "rejected": "_TRIAGE_REVIEW/rejected"
    }
  },

  "layout": {
    "mode": "para_jd",
    "roots": {
      "projects": "01_PROJECTS",
      "areas": "02_AREAS",
      "resources": "03_RESOURCES",
      "archive": "04_ARCHIVE"
    },
    "areas_root": "02_AREAS",
    "area_folders": [
      { "area_key": "contratos_comunicacao", "folder": "01_contratos_comunicacao" },
      { "area_key": "financeiro", "folder": "02_financeiro" },
      { "area_key": "juridica", "folder": "03_juridica" }
    ]
  },

  "classification": {
    "work_areas": [
      {
        "key": "contratos_comunicacao",
        "jd_number": 1,
        "aliases": ["contrato", "fornecedor", "sla", "nda", "termo aditivo"]
      },
      {
        "key": "financeiro",
        "jd_number": 2,
        "aliases": ["financeiro", "fiscal", "balanco", "dre", "fluxo caixa"]
      },
      {
        "key": "juridica",
        "jd_number": 3,
        "aliases": ["juridico", "parecer", "liminar", "procuracao"]
      }
    ],

    "routing_rules": [
      {
        "when_path_contains": ["output/", "entrega/"],
        "route_to": "entregaveis",
        "confidence": 0.98
      },
      {
        "when_filename_contains": ["contrato", "fornecedor", "sla"],
        "route_to": "contratos_comunicacao",
        "confidence": 0.95
      },
      {
        "when_filename_contains": ["parecer", "liminar"],
        "route_to": "juridica",
        "confidence": 0.95
      }
    ],

    "confidence_thresholds": {
      "auto_route_min": 0.85,
      "triage_min": 0.50
    },

    "llm_policy": {
      "enabled": false,
      "provider": "openai",
      "model": "gpt-4.1",
      "mode": "tag_only",
      "allow_override_fields": ["document_type", "tags", "confidence", "topics"],
      "override_guardrails": {
        "area_override_only_if_rule_confidence_below": 0.65,
        "require_explanation": true,
        "max_area_changes": 1
      }
    }
  },

  "indexing": {
    "topics_path": "config/topics_v1.yaml",
    "extraction_max_chars": 20000,
    "extraction_mode": "excerpt"
  }
}
```

## Blocos do profile

| Bloco | Propósito |
|-------|-----------|
| `paths` | Diretórios de inbox e triagem |
| `layout` | Modo (PARA+JD / custom), raízes, mapeamento área → pasta |
| `classification.work_areas` | Áreas com JD number e aliases para scoring |
| `classification.routing_rules` | Regras explícitas por path/filename (word boundary matching) |
| `classification.confidence_thresholds` | Limites para auto-route e triagem |
| `classification.llm_policy` | Configuração do LLM (provider, modelo, modo, guardrails) |
| `indexing` | Dicionário de topics, limite de extração, modo (excerpt/all) |

## Modos do LLM (`llm_policy.mode`)

| Modo | Comportamento |
|------|---------------|
| `tag_only` | Enriquece tags, document_type, topics. Não altera area_key. |
| `review` | Pode divergir da área, mas envia para triagem em vez de override direto. |
| `full_override` | Pode alterar area_key se guardrails permitirem (confiança baixa + explicação). |

## Notas

- Se `jd_number` for informado na `work_area`, a pasta usa esse número (`NN_area_key`).
- Se `jd_number` não for informado, o motor usa o próximo número disponível.
- `area_folders` em `layout` deve ter uma entrada para cada `work_area` em `classification`.
- O profile é versionado (`version` + `updated_at`) e o histórico fica em `_PROFILE/history/`.
