# Template de profile de projeto (V2)

O profile de cada projeto fica em `_PROFILE/profile.json` e segue o schema `ProjectProfileV2` em `backend/app/profile_schema_v2.py`.

## Contrato operacional da 0.8.0

- O eixo funcional canonico e `classification.business_domains`.
- O eixo formal canonico e `classification.document_types`.
- O layout fisico final em `02_AREAS/` e derivado como `02_AREAS/<business_domain>/<document_type>/`.
- `layout.business_domain_folders` mapeia o primeiro nivel fisico.
- `business_domain` e o unico eixo funcional persistido no runtime, na API e no indice.
- O schema atual usa apenas `classification.business_domains` e `layout.business_domain_folders` para o eixo funcional.
- `classification.operational.override_mode` permite fixar o modo efetivo do classificador por projeto quando houver necessidade de override manual.

## Exemplo minimo alinhado a 0.8.0

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
    "business_domain_folders": [
      { "business_domain": "juridico", "folder": "juridico" },
      { "business_domain": "financeiro", "folder": "financeiro" },
      { "business_domain": "suprimentos", "folder": "suprimentos" }
    ]
  },
  "classification": {
    "business_domains": [
      {
        "key": "juridico",
        "label": "Juridico",
        "aliases": ["juridico", "contrato", "aditivo", "parecer"],
        "primary_scope": "Contratos sob otica legal, pareceres, contencioso e procuracoes.",
        "subfunction_topics": ["parecer", "procuracao", "contencioso"]
      },
      {
        "key": "financeiro",
        "label": "Financeiro",
        "aliases": ["financeiro", "controladoria", "tesouraria", "faturamento"],
        "primary_scope": "FP&A, controladoria, tesouraria, AP/AR e caixa.",
        "subfunction_topics": ["controladoria", "tesouraria", "faturamento"]
      },
      {
        "key": "suprimentos",
        "label": "Suprimentos",
        "aliases": ["suprimentos", "compras", "procurement", "fornecedor"],
        "primary_scope": "Compras, sourcing e governanca de fornecedores.",
        "subfunction_topics": ["fornecedores", "compras_procurement", "rfp_rfq"]
      }
    ],
    "document_types": [
      {
        "key": "contrato",
        "label": "Contrato",
        "aliases": ["contrato", "agreement", "acordo"],
        "extensions": [".pdf", ".docx"],
        "folder": "contrato",
        "fallback_priority": 80,
        "detection_rules": [
          {
            "all_of": ["contrato", "contratante"],
            "confidence": 0.96,
            "reason": "structural_header"
          }
        ]
      },
      {
        "key": "planilha",
        "label": "Planilha",
        "aliases": ["planilha", "xlsx", "csv"],
        "extensions": [".xls", ".xlsx", ".csv"],
        "folder": "planilha",
        "extension_confidence_by_extension": {
          ".xlsx": 0.98,
          ".csv": 0.90
        },
        "fallback_priority": 15
      },
      {
        "key": "edital",
        "label": "Edital",
        "aliases": ["edital", "procedimento competitivo", "rfp", "rfq"],
        "extensions": [".pdf", ".docx"],
        "folder": "edital",
        "fallback_priority": 35,
        "detection_rules": [
          {
            "any_of": ["edital", "procedimento competitivo"],
            "confidence": 0.96,
            "reason": "structural_header"
          }
        ]
      }
    ],
    "entity_catalog": [],
    "routing_rules": [],
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
        "business_domain_override_only_if_rule_confidence_below": 0.65,
        "require_explanation": true,
        "max_business_domain_changes": 1
      }
    },
    "operational": {
      "override_mode": null
    }
  },
  "naming": {
    "canonical_pattern": "{date}__{project}__{business_domain}__{original_name}",
    "date_format": "%Y%m%d"
  },
  "indexing": {
    "topics_path": "config/topics_v1.yaml",
    "extraction_max_chars": 50000,
    "extraction_mode": "all"
  },
  "version": 1
}
```

## Blocos do profile

| Bloco | Proposito |
|-------|-----------|
| `paths` | Diretarios de inbox e triagem |
| `layout` | Raizes PARA e mapeamento `business_domain -> folder` |
| `classification.business_domains` | Dominios canonicos do projeto |
| `classification.document_types` | Tipos documentais canonicos e regras de deteccao |
| `classification.entity_catalog` | Entidades conhecidas adicionais para extracao deterministica |
| `classification.routing_rules` | Atalhos deterministas opcionais por path ou filename |
| `classification.confidence_thresholds` | Gates de auto-route e triagem |
| `classification.llm_policy` | Configuracao do LLM; no template default da 0.8.0 fica desabilitado |
| `classification.operational` | Override opcional do modo efetivo do classificador por projeto |
| `naming` | Pattern canonico do nome do arquivo |
| `indexing` | Topics, limite de extracao e modo (`excerpt` ou `all`) |

## Regras importantes

- `classification.business_domains` nao pode ser vazio.
- `classification.document_types` nao pode ser vazio.
- Cada `document_type.folder` deve ser unico.
- Cada `layout.business_domain_folders.business_domain` deve existir em `classification.business_domains`.
- `naming.canonical_pattern` precisa conter `{original_name}`.
- `classification.operational.override_mode`, quando preenchido, deve ser `bootstrap`, `sparse_logreg` ou `sparse_linear_svc`.
- `routing_rules` sao opcionais; o bootstrap atual nao depende delas para funcionar.
- `entity_catalog` pode ficar vazio; regexes basicas continuam ativas para CNPJ, email, contrato e valores.

## LLM no profile

O schema ainda suporta `tag_only`, `review` e `full_override`, mas o contrato operacional da 0.8.0 e:

- LLM desabilitado por padrao em `config/templates/default.json`.
- LLM nao e classificador primario.
- Quando habilitado, atua como enriquecedor ou revisor, nunca como pre-requisito para o fluxo.
- O override manual do classificador pertence a `classification.operational` e e independente da politica de LLM.
