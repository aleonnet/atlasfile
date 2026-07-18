# Migração e remoção governada de taxonomia (v0.26.0)

> Concluído em 2026-07-18. Fecha o ciclo de governança iniciado na criação governada (v0.22): renomear/consolidar/remover keys sem órfãos e sem contaminar o classificador.

## Problema

O TemplateEditorView deletava linhas de taxonomia sem guarda alguma (documentos órfãos), e uma key vive em **9 lugares**: template default + user templates, profiles (classification + `layout.business_domain_folders` + routing_rules), pastas físicas `02_AREAS/{bd}/{dt}`, índice OpenSearch (+ embeddings de chunk), 4 arquivos de dataset (por SHA), o `.pkl` do sparse (classes assadas), `_INDEX.md` e sugestões pendentes de triagem.

## Decisões de design

- **Dry-run obrigatório na UX**: `plan_taxonomy_migration` conta tudo (docs por projeto via aggregation, datasets por rótulo, pendências, templates, routing_rules) e avisa (sparse com classe antiga; docs fora de `02_AREAS`).
- **Sem contaminar o hold-out** (risco central): o move em massa usa `_relocate_document(dataset_routing=False)` — flag novo que pula `route_labeled_document`; os datasets são reescritos **in-place por rótulo antigo** (`rewrite_dataset_labels`, generalização do `_update_jsonl_labels_by_sha` do label_conflicts), zero registros novos.
- **Origem vira alias do destino** (default): aliases + extensions herdados — o bootstrap reconhece o legado imediatamente (mesmo princípio da própria key como alias na criação).
- **routing_rules reapontadas ANTES do filtro silencioso** do template_store (`_filter_routing_rules` descartaria rules órfãs no próximo save).
- **Pendências de triagem reescritas** (`suggested_*`) — sem isso, aprovar um pendente pós-migração explode no `_ensure_*_in_profile`.
- **Fora de `02_AREAS` (ex.: 04_ARCHIVE)**: só metadados no índice + aviso (mover a árvore de archive fica fora da v1).
- **Remoção pura guardada**: 409 com contagens de uso ativo, apontando para a migração.
- **Sparse não é editado**: classes antigas ficam no `.pkl` até o próximo ciclo — aviso explícito no dry-run e no resultado.
- Destino deve existir antes (reusa a criação governada); histórico de profiles/template notes não são reescritos (registro); ordem do apply: taxonomia primeiro (o `_ensure_*_in_profile` do move valida o destino), depois docs, datasets, pendências.

## Arquivos

Novos: `backend/app/taxonomy_migration.py`, `frontend/src/features/templates/TaxonomyMigrateModal.tsx` (+ testes de ambos).
Modificados: `main.py` (2 endpoints + flag `dataset_routing` no `_relocate_document`), `TemplateEditorView.tsx` (botão "Migrar / remover"), `api.ts`/tipos.

## Validação

- 11 unit backend (rewrite por rótulo com sha imutável e notes de proveniência; pendências; `_rename_in_raw` com herança de aliases/extensions e reescrita de rules; plan exige destino; apply move em áreas + index-only fora + template com alias; idempotência de 2ª execução; remoção guardada 409/limpa) + 3 de componente (dry-run preview, confirmação no apply, remoção guardada).
- E2E real na instância de teste (round-trip completo, estado final = original): criar `memorando_v2` → migrar `memorando`→`memorando_v2` (arquivo físico movido, índice, dataset de treino reescrito, template com alias) → recriar `memorando` → migrar de volta → remover `memorando_v2` (guarda liberou após esvaziar).
- Suítes completas: 559 backend + 144 frontend.
