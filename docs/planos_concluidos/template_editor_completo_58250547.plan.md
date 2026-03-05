---
name: Template editor completo
overview: Expandir o modal de edição de templates com 4 novas seções colapsáveis para routing rules, confidence thresholds, LLM policy e indexing, reutilizando padrões visuais existentes e mantendo compatibilidade total com o backend.
todos:
  - id: types-routing-rule
    content: Adicionar interface RoutingRule em types.ts e atualizar routing_rules de Record para RoutingRule[]
    status: completed
  - id: css-sections
    content: Adicionar CSS para grids das novas secoes (thresholds, llm, guardrails, indexing) em templates.css. Garantir que itc-collapsible esta disponivel.
    status: completed
  - id: editor-routing-rules
    content: "Implementar secao Routing Rules no editor: tabela editavel com tipo/patterns/area/confidence + add/remove"
    status: completed
  - id: editor-thresholds
    content: "Implementar secao Confidence Thresholds: grid 2 colunas com inputs numericos"
    status: completed
  - id: editor-llm-policy
    content: "Implementar secao LLM Policy: toggle, selects provider/model/mode, sub-secao guardrails"
    status: completed
  - id: editor-indexing
    content: "Implementar secao Indexacao: topics_path, extraction_max_chars, extraction_mode"
    status: completed
  - id: frontend-tests
    content: Criar TemplateEditorView.test.tsx com testes de renderizacao e interacao para todas as secoes
    status: completed
  - id: final-validation
    content: ReadLints nos arquivos alterados + rodar make test (backend 176 + frontend)
    status: completed
isProject: false
---

# Expandir Editor de Templates com Seções Completas

## Contexto

O editor de templates atual ([TemplateEditorView.tsx](frontend/src/features/templates/TemplateEditorView.tsx)) edita apenas:

- Meta: nome, slug, descrição
- Work Areas: tabela com `#`, `AREA_KEY`, `ALIASES`

O JSON do template ([default.json](config/templates/default.json)) contém 4 blocos adicionais que precisam ser editaveis:

- `classification.routing_rules`
- `classification.confidence_thresholds`
- `classification.llm_policy` + `override_guardrails`
- `indexing` (topics_path, extraction_max_chars, extraction_mode)

O backend (`template_store.py`, `profile_schema_v2.py`) ja salva/carrega o JSON completo -- nenhuma alteracao backend e necessaria.

## Mockup do Modal Expandido

```
+-------------------------------------------------------+
| Editar template: M&A / Carve-out            [X]       |
+-------------------------------------------------------+
| Nome:       [M&A / Carve-out                        ] |
| Slug:       [default                        ] (ro)    |
| Descricao:  [Template padrao para...                ] |
+-------------------------------------------------------+
| > Estrutura de Layout (9 areas)                       |
|   # | AREA_KEY            | ALIASES           | [x]  |
|   1 | societario_fiscal   | societario, ...   | [x]  |
|   ...                                                 |
|   [+ Adicionar area]                                  |
+-------------------------------------------------------+
| > Routing Rules (5 regras)                            |
|   TIPO      | PATTERNS              | AREA   | CONF  |
|   filename  | contrato, fornecedor  | contr  | 0.90  |
|   path      | output/               | entreg | 0.98  |
|   ...                                          [x]   |
|   [+ Adicionar regra]                                 |
+-------------------------------------------------------+
| > Confidence Thresholds                               |
|   Auto-route minimo:  [0.85]   Triage minimo: [0.50] |
+-------------------------------------------------------+
| > LLM Policy                                          |
|   Ativado: [toggle]                                   |
|   Provedor: [openai v]   Modelo: [gpt-4.1         ]  |
|   Modo:     [tag_only v]                              |
|   --- Guardrails ---                                  |
|   Override se confianca abaixo de: [0.65]             |
|   Exigir explicacao: [x]  Max area changes: [1]      |
+-------------------------------------------------------+
| > Indexacao                                           |
|   Topics path:      [config/topics_v1.yaml          ] |
|   Max chars:        [50000                          ] |
|   Modo extracao:    [all v]                           |
+-------------------------------------------------------+
|                           [Cancelar] [Salvar template] |
+-------------------------------------------------------+
```

Todas as secoes usam `<details className="itc-collapsible">` (padrao ja existente no `IngestTriageCard`). Secoes iniciam colapsadas exceto "Estrutura de Layout" que ja abre expandida.

## Arquivos a Alterar

### 1. Frontend: tipos (`frontend/src/types.ts`)

Adicionar interface `RoutingRule` explicita (hoje e `Record<string, unknown>`):

```typescript
export interface RoutingRule {
  when_path_contains?: string[];
  when_filename_contains?: string[];
  route_to: string;
  confidence: number;
}
```

Atualizar `ProjectProfileV2.classification.routing_rules` de `Array<Record<string, unknown>>` para `RoutingRule[]`.

### 2. Frontend: editor (`frontend/src/features/templates/TemplateEditorView.tsx`)

Adicionar 4 secoes colapsaveis no modal do editor, entre "Estrutura de Layout" e "modal-actions":

- **Secao "Routing Rules"**: tabela editavel com colunas Tipo (select: path/filename), Patterns (input comma-separated), Area (select populado das work_areas do editor), Confidence (input number 0-1). Botoes de adicionar/remover.
- **Secao "Confidence Thresholds"**: grid 2 colunas com inputs numericos para `auto_route_min` e `triage_min`.
- **Secao "LLM Policy"**: toggle enabled, selects para provider (openai/anthropic), input modelo, select modo (tag_only/review/full_override). Sub-secao "Guardrails" com input numerico para threshold, checkbox para require_explanation, input numerico para max_area_changes.
- **Secao "Indexacao"**: input texto para topics_path, input numerico para extraction_max_chars, select para extraction_mode (all/excerpt).

Helpers de estado: funcoes `updateClassification(field, value)`, `updateLlmPolicy(field, value)`, `updateGuardrails(field, value)`, `updateIndexing(field, value)` analogas ao `updateArea` existente, operando sobre `editor.profileData`.

Para routing rules: funcoes `addRule()`, `removeRule(idx)`, `updateRule(idx, field, value)` analogas a `addArea/removeArea/updateArea`.

### 3. Frontend: CSS (`frontend/src/features/templates/templates.css`)

Adicionar classes para o layout dos novos campos:

- `.tmpl-thresholds-grid` -- grid 2 colunas para thresholds
- `.tmpl-llm-grid` -- grid 2 colunas para LLM fields
- `.tmpl-guardrails-grid` -- grid 2-3 colunas para guardrails
- `.tmpl-indexing-grid` -- grid 2 colunas para indexing

Reusar `.itc-collapsible`, `.itc-collapsible-header`, `.itc-collapsible-body`, `.itc-scan-table`, `.itc-badge-count` que ja estao importados via `ingestTriageCard.css` (verificar se o import e global ou precisa ser adicionado em `templates.css`).

### 4. Frontend: importar CSS colapsavel

O `TemplateEditorView` usa classes `itc-collapsible` mas NAO importa `ingestTriageCard.css`. Verificar se esses estilos estao disponveis globalmente. Se nao, replicar as regras necessarias em `templates.css` ou importar o CSS.

### 5. Testes frontend

Adicionar testes em um novo arquivo `frontend/src/features/templates/TemplateEditorView.test.tsx`:

- Teste de renderizacao: verificar que as 5 secoes colapsaveis existem no modal
- Teste de routing rules: abrir secao, verificar tabela, simular adicao de regra
- Teste de thresholds: verificar inputs e valores default
- Teste de LLM policy: verificar toggle, selects de provider/mode
- Teste de indexing: verificar inputs e select de modo

Mock de `api.ts` para `listTemplates` e `getTemplate` retornando dados com todos os campos preenchidos.

### 6. Backend: sem alteracoes

O `template_store.py` ja salva/carrega o JSON completo. O `profile_schema_v2.py` ja valida todos os modelos. Nenhuma mudanca e necessaria no backend.

### 7. Testes backend: sem alteracoes

Os testes existentes em `test_template_store.py` (12 testes) ja cobrem save/load com dados completos via `SAMPLE_TEMPLATE_DATA`. Nenhum teste novo necessario.

## Validacoes no Frontend

- **Routing rule**: `route_to` obrigatorio, `confidence` entre 0 e 1, pelo menos um pattern (path ou filename)
- **Thresholds**: `triage_min <= auto_route_min`, ambos entre 0 e 1
- **LLM guardrails**: `area_override_only_if_rule_confidence_below` entre 0 e 1, `max_area_changes >= 0`
- **Indexing**: `extraction_max_chars > 0`

O botao "Salvar template" ja existente envia o `profileData` completo (incluindo os novos campos editados). Sem mudanca na API.

## Ordem de Implementacao

1. Atualizar `types.ts` (RoutingRule)
2. Adicionar CSS em `templates.css`
3. Expandir `TemplateEditorView.tsx` com as 4 secoes
4. Criar testes `TemplateEditorView.test.tsx`
5. Verificar lint + rodar todos os testes

