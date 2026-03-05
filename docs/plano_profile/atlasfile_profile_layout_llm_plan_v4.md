# AtlasFile — Plano incremental (Profile v2 JSON + Layout migration + LLM override + Topics) — **Implementação guiada por testes**

## Objetivo
Evoluir o AtlasFile para:
1) eliminar **hardcode** de `work_areas`/`routing_rules` (defaults via template de arquivo);
2) tornar o **Profile v2** **editável pelo frontend** (sem edição manual de `.md`);
3) permitir **reorganização/migração de estrutura de pastas** (ex.: iniciar com **PARA/JD** e migrar para estrutura customizada depois);
4) tornar o LLM capaz de **revisar e (opcionalmente) sobrescrever** o resultado rule-based de forma **governada**, por projeto;
5) incorporar `topics_v1.yaml` (topics controlados por sinônimos) no pipeline.

> Requisito de qualidade: mudanças **incrementais, reversíveis** e com **auditoria** (não “refazer tudo”).  
> **Fonte da verdade do profile:** arquivo JSON no projeto (`_PROFILE/profile.json`). **Não existe `.md` como storage.**  
> **Regra de implementação:** cada fase só avança quando os **testes da fase** estiverem passando (CI verde).

---

## Estado atual (factual, do código)
- Inicialização de projeto:
  - Se não existe `_PROJECT_PROFILE.md`, o backend cria um profile “default” via `_build_default_profile()` (hardcoded) e escreve no disco.
  - `scripts/bootstrap_project.py` também gera estrutura/profile (hardcoded), fora da API.
- Ingestão:
  - Rule-based sempre roda primeiro e define `area_key`, `reason`, `top_candidates`, `confidence`.
  - LLM (se habilitado) roda **depois** e hoje pode sobrescrever **somente** `confidence` e adicionar `tags/document_type` (não define rota).
- Triagem:
  - Documentos pendentes ficam em `_TRIAGE_REVIEW/pending`; aprovados/corrigidos vão para o work_root atual (ex.: `_WORK/<area>`).
- Indexação:
  - OpenSearch armazena campos de busca e chunks; há boost em title/filenames e nested inner_hits.

---

## Decisão arquitetural: Profile v2 “objeto” (JSON) editável via API/UI
### Regra de ouro
O profile não pode ser “config hardcoded” nem “arquivo que o usuário edita manualmente”. Ele deve ser:
- **Estruturado e validado** (Pydantic `ProjectProfileV2` – ver `profile_v2.py`);
- **Persistido** no projeto com histórico/auditoria;
- **Editável via API/UI** com validação e migrações (plan/apply).

### Onde o Profile v2 fica armazenado
- `project_root/_PROFILE/profile.json`  ✅ **fonte da verdade**
- `project_root/_PROFILE/history/<timestamp>__vNN.json`  ✅ histórico (append-only)

> (Opcional) “Export Markdown” pode existir como feature, mas **não** como storage.

### Template default (sem hardcode)
- `config/templates/profile_v2_default.json` (ou `.yaml` apenas como template)
- Ao criar um projeto novo, o backend copia esse template, preenche `project_id`, `project_label`, `project_root` e grava em `_PROFILE/profile.json`.

---

## Estrutura do Profile v2 (alinhada ao `profile_v2.py`)
O Profile v2 é validado por Pydantic (`ProjectProfileV2`). Campos centrais:

- `paths.inbox` e `paths.triage.*` (inbox/triagem)
- `layout.areas_root` + `layout.area_folders[]` (onde ficam as áreas e como cada `area_key` mapeia para uma pasta)
- `classification.work_areas[]` + `classification.routing_rules[]` + thresholds
- `indexing.topics_path` + extraction caps/mode
- `classification.llm_policy` (override governado: tag_only/review/full_override)

Exemplo completo: `profile_v2_example.json`.

---

## Plano incremental (P0 / P1 / P2) — **não pular fases sem testes**

# P0 — Profile v2 JSON no projeto + tirar hardcode + PARA/JD como default

### 1) Unificar defaults em um template de arquivo (sem hardcode)
**Criar**
- `config/templates/profile_v2_default.json` (template canônico)

**Alterar**
- `_build_default_profile()`:
  - **deixa de** gerar YAML hardcoded
  - passa a copiar o template JSON e preencher `project_id/project_label/project_root`
  - grava em `project_root/_PROFILE/profile.json`
- `scripts/bootstrap_project.py`:
  - carrega o MESMO template default
  - cria estrutura + grava `_PROFILE/profile.json` (sem hardcode)

**Testes (obrigatórios para fechar P0.1)**
- `test_default_template_roundtrip`: carregar template → validar com `ProjectProfileV2` → salvar → recarregar → igual (exceto `updated_at/version`)
- `test_build_default_profile_writes_profile_json`: criar projeto “vazio” → rodar init → existe `_PROFILE/profile.json`

---

### 2) Bootstrap/ensure_structure a partir do Profile v2 (PARA/JD)
**Regras**
- Estrutura inicial deve ser criada com base em `profile.layout` e `profile.paths`.
- PARA “out of the box”:
  - criar `layout.roots.projects/areas/resources/archive`
  - criar `layout.areas_root` e cada `area_folders[*].folder`
- Não tocar em inbox/triage fora do que está no profile.

**Testes (obrigatórios para fechar P0.2)**
- `test_ensure_structure_creates_para_roots`: cria projeto novo → ensure_structure → existem 01/02/03/04
- `test_ensure_structure_creates_area_folders`: cria profile com 3 áreas → ensure_structure → pastas criadas
- `test_ensure_structure_does_not_touch_triage_contents`: se triage tem arquivos, ensure_structure não move/deleta

---

### 3) API de Profile editável (frontend) — sem `.md`
**Criar**
- `backend/app/profile_store.py`:
  - `load_profile(project_root) -> ProjectProfileV2`
  - `save_profile(project_root, profile, if_match_version, updated_by) -> ProjectProfileV2`
  - grava history (`_PROFILE/history/...json`)
  - retorna `etag` (hash do JSON canônico)
- `backend/app/profile_api.py`:
  - `GET /api/projects/{project_id}/profile`
  - `PUT /api/projects/{project_id}/profile`
  - `POST /api/projects/{project_id}/profile/validate`
  - `GET /api/projects/{project_id}/profile/history`

**Concorrência**
- `PUT` exige `if_match_version` (optimistic lock). Divergiu → `409 Conflict`.

**Testes (obrigatórios para fechar P0.3)**
- `test_profile_get_returns_version_etag`
- `test_profile_put_requires_if_match_version_conflict`
- `test_profile_put_writes_history_entry`
- `test_profile_validate_rejects_invalid_area_folders`

---

# P1 — Reorganização/migração de pastas via plan/apply (determinístico)
> **Importante:** migração de pastas é executada pelo backend (determinística).  
> O LLM pode **propor** alterações no profile/layout, mas **não** executa apply.

### 4) Layout migration: plan/apply (alinhado ao `layout_migration.py` novo)
`layout_migration.py` já suporta:
- mudança de `areas_root`
- remapeamento de `area_folders` por `area_key`
- `cleanup_empty_dirs` opcional (best-effort)

**Criar endpoints**
- `POST /api/projects/{project_id}/layout/plan`
  - Input: `new_profile` (ou `new_layout` + `strategy` + `cleanup_empty_dirs`)
  - Output: `plan` + `summary` + `plan_id` (hash do plano)
  - Sempre dry-run (não move)
- `POST /api/projects/{project_id}/layout/apply`
  - Input: `{ plan_id, confirm: true, run_reconcile: true|false }`
  - Executa apply (dry_run=false)
  - Se `run_reconcile=true`, chama reconcile/sync ao final
  - Retorna apply_summary e opcional reconcile_summary

**Testes (obrigatórios para fechar P1.4)**
- `test_layout_plan_dry_run_no_fs_changes`
- `test_layout_plan_includes_remap_area_folders`
- `test_layout_apply_moves_files_and_preserves_reserved_roots`
- `test_layout_apply_cleanup_empty_dirs_best_effort`

---

### 5) Pipeline passa a usar layout dinâmico (sem hardcode)
**Mudança funcional**
- Ingestão continua produzindo `area_key`.
- O destino final do move passa a ser:
  - `layout.areas_root / layout.area_folders[area_key].folder`

**Testes (obrigatórios para fechar P1.5)**
- `test_ingest_moves_to_profile_layout_folder`
- `test_ingest_uses_profile_layout_areas_root_not__WORK`

---

# P1 — LLM override governado (review → full_override)

### 6) LLM revisa o output rule-based (com política no profile)
- Política em `profile.classification.llm_policy`.
- Modos:
  - `tag_only`: altera somente `document_type/tags/confidence/topics`
  - `review`: pode sugerir `area_key`, mas divergência vira `triage_pending` (não move)
  - `full_override`: pode mudar `area_key` se guardrails permitirem

**Importante**
- LLM **não** executa layout migration.
- Toda alteração do LLM deve ser registrada (audit no `_INDEX.md` ou metadata do doc).

**Testes (obrigatórios para fechar P1.6)**
- `test_llm_tag_only_does_not_change_area_key`
- `test_llm_review_disagreement_forces_triage_pending`
- `test_llm_full_override_respects_guardrails`

---

# P0 — Topics controlados via topics_v1.yaml

### 7) topics_v1.yaml (source of truth) + matcher determinístico
**Regras**
- `topics` é faceta controlada.
- Matching por synonyms roda antes do LLM.
- LLM só sugere keys existentes.

**Testes (obrigatórios para fechar P0.7)**
- `test_topics_matcher_returns_only_known_keys`
- `test_topics_matcher_bias_by_area`
- `test_topics_source_synonym_match`

---

# P2 — melhorias (opcionais)
- UI com editor visual de layout (drag/drop) + preview do plan
- rollback de migração (transaction log)
- métricas de qualidade: top-3 hit rate por queries reais
- sugestão assistida de layout (LLM propõe folder names) **sem** apply automático

---

## Mockup ASCII — Edição de Profile (Layout + Migração)
┌──────────────────────────────────────────────────────────────┐
│ Projeto: Kaidô - Implantação UPI Tahto   (Profile v2 JSON)    │
│ ID: kaido_upi_tahto                 Versão: 7   Última: Ale   │
└──────────────────────────────────────────────────────────────┘

[ Abas ]  (Geral) (Layout) (Classificação) (LLM) (Indexação) (Histórico)

============================  Layout  ============================

Modo de layout:  (•) PARA + JD     ( ) Custom

Raízes (PARA):
  01_PROJECTS   [editar]  ->  "01_PROJECTS"
  02_AREAS      [editar]  ->  "02_AREAS"
  03_RESOURCES  [editar]  ->  "03_RESOURCES"
  04_ARCHIVE    [editar]  ->  "04_ARCHIVE"

Areas root (onde ficam as áreas):
  areas_root:  "02_AREAS"  [editar]

Mapeamento de áreas → pastas:
  ┌──────────────────────┬───────────────────────────────┐
  │ area_key              │ folder                         │
  ├──────────────────────┼───────────────────────────────┤
  │ societario_fiscal     │ 01_societario_fiscal          │
  │ juridica              │ 02_juridica                   │  <- [editar]
  │ ativos                │ 03_ativos                     │
  │ financeiro            │ 04_financeiro                 │
  │ contratos_comunicacao │ 05_contratos_comunicacao      │
  │ pessoas               │ 06_pessoas                    │
  │ sistemas_migracao     │ 07_sistemas_migracao          │
  │ processos_tsa         │ 08_processos_tsa              │
  │ entregaveis           │ 09_entregaveis                │
  └──────────────────────┴───────────────────────────────┘

[ + Adicionar área_folder ]   [ Validar alterações ]   [ Salvar Profile ]

------------------------------------------------------------------
⚠ Alterações detectadas em layout (areas_root/area_folders)
Salvar o profile NÃO move arquivos automaticamente.

[ Gerar plano de migração (dry-run) ]  Estratégia conflito: (•) renomear  ( ) pular  ( ) sobrescrever
[ ] cleanup dirs vazios (best-effort)
------------------------------------------------------------------

====================  Preview: Plano de Migração  ====================

plan_id:  7b4e...c19a

Resumo:
  mkdir: 1   move: 128   conflicts: 3   skip: 0   rmdir_empty: 12

Operações (amostra):
  + mkdir  /projects/Kaidô/02_AREAS/Juridico
  > move   /projects/Kaidô/02_AREAS/02_juridica/20260302__...pdf
          ->/projects/Kaidô/02_AREAS/Juridico/20260302__...pdf

Conflitos:
  ! conflict destino já existe:
     .../Juridico/20260302__...pdf

Estratégia de conflito:
  (•) renomear com sufixo  ( ) pular  ( ) sobrescrever

[ Aplicar migração ]  [ Cancelar ]  [ Baixar plano (.json) ]

---

## Checklist (implementação)
### Criar
- `config/templates/profile_v2_default.json`
- `backend/app/profile_store.py` (load/save/history/etag/version)
- `backend/app/profile_api.py` (GET/PUT/validate/history)
- `backend/app/layout_api.py` (layout/plan, layout/apply)
- `backend/app/topics.py` (loader/matcher)

### Alterar
- `_build_default_profile()` → usa template JSON + grava `_PROFILE/profile.json`
- `scripts/bootstrap_project.py` → usa template JSON
- `area_resolver.py` → usa `profile.layout.area_folders`
- `ingestion.py` → remove hardcode de `_WORK` e usa `profile.layout.areas_root`
- `reconcile.py` → usa `profile.layout.areas_root`
- `orchestrator` → schema da tool + merge policy `llm_policy`
- `indexer` → usar `profile.indexing.topics_path` e extraction settings (já coberto no indexer_v3)

---

## Critérios de aceitação
1) Defaults do profile não estão no código: só no template JSON.
2) Profile é editável via frontend (API), com validação, version e history.
3) Layout pode migrar (areas_root e/ou area_folders) via plan/apply com preview e confirmação.
4) LLM revisa output rule-based sob política `llm_policy` (sem executar migração).
5) Topics controlados via `topics_v1.yaml` entram como faceta e melhoram busca humana.
