# bootstrap_alias_suggester_v0370 — Sugeridor de aliases do bootstrap

> **CONCLUÍDO em 2026-07-23.** Origem: item "Sugeridor de aliases a partir da triagem"
> do `docs/ROADMAP.md` (registrado 2026-07-22), promovido a plano por decisão do usuário.
> Branch: `feature/bootstrap-alias-suggester-v0370` (empilhado no v0.36.0).

## Contexto

O bootstrap é estático por design (regras + aliases do profile); quem aprende é o
`sparse_logreg`. A lacuna: as correções humanas da triagem evidenciam termos que o
bootstrap desconhece (ex.: corrigir docs com "escritura" para `juridico` sem que
"escritura" seja alias) — e o ajuste era 100% manual no editor de templates.
Sintoma real observado: bootstrap campeão com `type 100%` e `domain 0%`.

## Decisões de design (fatos da exploração)

1. **Fonte da evidência**: JSONs de `triage_resolved_dir` — únicos que guardam o par
   `suggested_*` (sugestão do classificador) vs rótulo final humano. O training pool
   só marca `decision=corrected`, sem a sugestão original.
2. **Texto minerado = texto que o bootstrap vê**: `classifier_cycle.extract_feature_text`
   (nome original + excerpt, com `fold_ocr_spacing`) — candidatos casam por construção
   com o matching real (`_word_pattern`, boundary `[a-z0-9]`), com auto-verificação
   final de cada termo contra os textos-fonte.
3. **Candidatos por PARTE** (stem do nome sem extensão | excerpt): n-gramas não
   atravessam a fronteira nome→texto (bug real pego por teste: o bigrama artificial
   "txt escritura" engolia o unigrama legítimo) e extensões de arquivo nunca viram alias.
4. **Corte contrastivo sem stopwords artesanais**: suporte ≥2 docs corrigidos da
   classe-alvo + precisão ≥0.8 sobre TODOS os docs resolvidos + ≥2 rótulos distintos
   no corpus. Genéricos morrem na precisão; 2-grama com mesmo suporte absorve o
   1-grama redundante. Colisão com `_document_type_lexicon` descartada (espelho do
   runtime do bootstrap).
5. **Append governado**: `taxonomy.add_taxonomy_aliases` (novo — antes só havia
   create/migrate) faz merge ordenado no template `default` + propagação aos profiles,
   com proveniência; idempotente. Dispensas persistem no profile
   (`classification.alias_suggestions_dismissed`, campo novo no schema v2).
6. **UI**: 3ª seção colapsável do Classificador (molde do card de conflitos):
   grupos por entrada com chips de termo + evidência (docs, precisão) e ações
   Aprovar/Dispensar; some quando não há sugestões. i18n PT/EN completa.

## Entregas

- `backend/app/alias_suggester.py` (novo) — minerador puro (nada persiste).
- `backend/app/taxonomy.py` — `add_taxonomy_aliases` + `_merge_aliases_into_entry`.
- `backend/app/profile_schema_v2.py` — `alias_suggestions_dismissed`.
- `backend/app/main.py` — `GET /api/projects/{ref}/alias-suggestions`,
  `POST /api/taxonomy/aliases`, `POST /api/projects/{ref}/alias-suggestions/dismiss`.
- Frontend: `api.ts` (3 funções + tipos), `qk.aliasSuggestions`, invalidação em
  `invalidateAfterTaxonomyChange`, seção no `IngestTriageCard`, i18n `ingest:aliasSuggest.*`
  e `errors:api.*` nos 2 idiomas.
- Testes: 5 unit do minerador (incl. o bug do bigrama de fronteira), 2 do append,
  3 integração dos endpoints, 2 da seção na UI + mock atualizado; paridade i18n verde.
  Suíte completa: 617 backend + 225 frontend.

## Medição do gatilho em dados reais (instância de teste, leitura pura)

4 resolvidos, 2 correções (classes diferentes: `operacoes`, `memo`, `fluxogram`),
4 rótulos distintos → **0 sugestões no corte oficial** (correto: 1 doc não é padrão).
Preview com suporte=1 confirmou o porquê do corte: ruído de OCR ("prospecgio
desenvolvimen") e bigramas genéricos passariam sem ele. O N=2 do gatilho do ROADMAP
está validado com dados reais. Nota operacional: paths dos JSONs resolvidos são do
container — a medição host-side exige remap (o produto roda in-container, sem remap).

## Não-objetivos (mantidos)

Auto-aplicação; mineração via LLM; stemming multilíngue (ROADMAP i18n).

## Verificação futura (roteiro E2E v0.37)

Estágio novo: fazer ≥2 correções para a MESMA classe com termo recorrente → seção
"Sugestões de aliases" aparece com o termo → Aprovar → ingerir doc novo com o termo →
bootstrap classifica na classe correta; Dispensar → termo não volta.
