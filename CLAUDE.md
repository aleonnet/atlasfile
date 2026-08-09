# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Diretrizes do projeto

> As regras de trabalho (comunicação, papel, investigação, escopo, git) valem
> para todos os projetos e vivem no `CLAUDE.md` global do usuário — não são
> repetidas aqui para não divergirem. Abaixo fica só o que é **deste**
> repositório.

### Planejamento
- Todo plano deve incluir:
  - lista de mudanças
  - arquivos a alterar
  - decisões de schema/mapping/query
  - steps de migração, se houver
  - testes e validações

### Planos de implementação
- Cada plano deve ter um nome único e descritivo (nunca reutilizar/sobrescrever um plano anterior).
- Planos concluídos devem ser salvos em `docs/planos_concluidos/` como registro de decisões.

### Ao concluir planos (checklist obrigatório)
1. Salvar plano em `docs/planos_concluidos/<nome_unico>.plan.md`
2. Atualizar `docs/planos_concluidos/README.md` com o novo plano
3. Bump de versão **só em release real do app** — e **nunca por conta própria**:
   - **Mudança de instalador NÃO bumpa** (`install.sh`/`install.ps1`/bancadas):
     eles viajam por `raw.githubusercontent.com/main` e não fazem parte do
     bundle da release. Decisão registrada em 2026-07-31; desde a v1.0.0 já
     foram cinco planos concluídos sem bump.
   - Quando bumpar: `frontend/package.json` + `frontend/package-lock.json`,
     SemVer — **patch** (0.0.x) bug fixes e ajustes visuais; **minor** (0.x.0)
     features, endpoints, componentes; **major** (x.0.0) breaking em API/schema.
   - O bump exige **confirmação nominal do dono no momento**. Plano aprovado
     não é autorização para bumpar.
4. Atualizar `CHANGELOG.md` com as mudanças da versão
5. Revisar `README.md` e `INSTALL.md` — atualizar se houve mudança em setup, dependências ou funcionalidades documentadas
6. Adicionar todos os arquivos alterados ao git staging
7. Propor texto de commit baseado nas alterações desde o último commit, considerando os planos concluídos

## Skills obrigatórios
- **safe-exec** (`.claude/skills/safe-exec/SKILL.md`): Deve ser sempre usado antes de executar qualquer comando Bash. Classifica comandos como safe (executar imediatamente) ou destructive (pedir confirmação explícita).

## O que "verde" significa aqui (invariantes, não números)

Número em arquivo apodrece — então o que vale é o **comando** e o **invariante**.
Medir antes de afirmar; nunca citar contagem de memória.

| Canal | Comando | Invariante |
|---|---|---|
| Bancada dos instaladores | `bash tests/installer/run.sh` | `0 failed` |
| Baseline por NOME | `AF_BENCH_TRACE=1 bash tests/installer/run.sh 2>&1 >/dev/null \| grep -c '^TRACE'` | **zero nome perdido** contra a medição anterior (`comm -23` vazio). Nome de bloco é a unidade de regressão — total de asserções sozinho esconde perda |
| Consistência dos instaladores | `python3 tests/installer/check_consistency.py` | 13 guardas verdes; reprovação é sinal, nunca flake |
| Bancada Windows | `tests/installer/win/run.ps1` na VM, canal `prlctl exec` **sem** `-u` (SYSTEM) | `0 failed`; o canal `--current-user` mede errado por falta de elevação |
| Backend / frontend | `make test` | `0 failed` |

Última medição (2026-08-01): bancada sh **383/0** com **214 nomes**;
consistência **13/13**. Windows **241/0** em 2026-07-31 (não re-medido depois).

## Armadilhas conhecidas do `install.sh`

- **O gate de biblioteca não torna nada intestável.** Abaixo do
  `ATLASFILE_INSTALL_LIB` o `run_case` não alcança — mas a bancada **roda o
  instalador inteiro** em ~1,4 s: release local (`af_release_local` +
  `stub_curl_release`, tar e sha reais) + stub de docker que falha no `pull`, e
  a corrida atravessa as fases 1–3 e morre na 4, com `.env` escrito e tela
  inteira observável. **Nunca declarar um caminho "intestável" sem medir esse
  canal** — foi premissa errada num plano aprovado, corrigida pela banca.
- **Guarda se prova com mutante**, um por vez, cada um nomeando a asserção-alvo
  que morreu; restauração byte-exata conferida com `cmp`.
- **Nunca rodar processo que MUTA o `install.sh` em paralelo com suíte que o
  lê** — o resultado vira ruído impossível de interpretar.
- Instalação por bundle **não deixa `install.sh` na pasta**: re-executar exige o
  one-liner do raw/main.

## Comandos de build e teste

```bash
# Todos os testes (backend pytest + frontend vitest)
make test

# Backend apenas
make test-backend
# Equivale a: cd backend && .venv/bin/python -m pytest tests/ -v

# Teste único backend (exemplo)
cd backend && .venv/bin/python -m pytest tests/unit/test_utils.py -v
cd backend && .venv/bin/python -m pytest tests/unit/test_utils.py::test_nome -v

# Frontend apenas
make test-frontend
# Equivale a: cd frontend && npm run test

# Teste único frontend (exemplo)
cd frontend && npx vitest run src/features/ingest/IngestTriageCard.test.tsx

# Stack Docker completo (testa, builda, sobe, smoke test)
make docker-update

# Subir stack sem testes
make docker-up

# Reset de índices
make reset-index    # documentos
make reset-chat     # sessões de chat
```

## Arquitetura

Monorepo com 2 serviços Docker (3 com o profile opt-in `dashboards`): `atlasfile` (:8000 — um uvicorn serve a API REST/SSE em `/api/*`, o MCP em `/mcp` e o bundle de produção da UI em `/`), OpenSearch (127.0.0.1:9200 por default) e Dashboards (:5601, opt-in). Portas de host configuráveis via `.env` (`ATLASFILE_PORT`/`OPENSEARCH_PORT`+`OPENSEARCH_BIND`/`DASHBOARDS_PORT`; instalador: `--port`/`-Port`). Em desenvolvimento a UI roda no vite dev (:5173) com proxy para :8000.

### Backend (`backend/`)

- **Python 3.12**, FastAPI, async-first. Sem pyproject.toml — usa `requirements.txt`.
- **`app/main.py`** — arquivo monolítico (~2000+ linhas) com todos os endpoints REST e SSE. Entry point do uvicorn.
- **`app/ingestion.py`** — pipeline de ingestão: extração de texto, dedup SHA256, classificação, roteamento para filesystem, indexação no OpenSearch.
- **`app/document_extractor.py`** — extração de PDF, DOCX, XLSX, PPTX, MSG com OCR (tesseract).
- **`app/classifier_*.py`** — sistema de classificação com 3 modos: `bootstrap` (regras + aliases), `sparse_logreg` (TF-IDF + LogReg), `llm` (GPT-4o-mini). Registry global em `_ATLASFILE/classifier/`. Decisões de design: `docs/planos_concluidos/classificacao_4_modos_pipeline_dados_v090.plan.md` (o modo `setfit` foi removido posteriormente).
- **`app/orchestrator.py`** — loop de chat LLM com MCP tools, suporta OpenAI e Anthropic.
- **`app/mcp/server.py`** — MCP server (FastMCP) que expõe tools de busca, tags e stats.
- **`app/mcp_client/`** — cliente MCP para o orchestrator chamar tools.
- **`app/api/`** — routers adicionais: `profile.py`, `layout.py`, `channels.py`.
- **`app/config.py`** — settings via pydantic-settings (OpenSearch, LLM, busca, channels).
- **`app/reconcile.py`** — sincronização filesystem ↔ OpenSearch.
- **`app/watcher.py`** — filesystem watcher para auto-ingest.
- **`app/area_resolver.py`** — resolução de business domain a partir da classificação.
- **`app/triage.py`** — workflow de triagem manual de documentos em `_TRIAGE_REVIEW/pending`.
- **`app/ingest_history.py`** — trilha de auditoria de eventos de ingestão.
- **`app/usage_costs.py`** — rastreamento de custo de chamadas LLM (tabela em `config/usage_costs.json`).
- **Testes**: `tests/unit/` (51 arquivos) e `tests/integration/` (15 arquivos). Config em `pytest.ini` com `asyncio_mode = auto`.

### Scripts de Data Pipeline (`backend/scripts/`)

Executar dentro do venv do backend (`cd backend && .venv/bin/python scripts/<script>.py`):

| Script | Função |
|--------|--------|
| `build_corpus.py` | Consolida training_pool + validation_set → `corpus.jsonl` (dedup SHA256) |
| `build_splits.py` | Split estratificado 70/15/15 via StratifiedShuffleSplit |
| `label_corpus_llm.py` | Rotulagem automática via GPT-4o-mini |
| `inject_training_records.py` | Injeção manual de registros com anti-leakage SHA256 |
| `run_classifier_cycle.py` | Entrypoint CLI para benchmark completo |
| `run_augmentation.py` | Geração de exemplos sintéticos de treino |
| `update_catalog_snapshot.py` | Atualiza o snapshot LiteLLM embarcado (`app/data/llm_catalog_snapshot.json`); preserva `user_models`/`user_costs` |

Estrutura de dados do classifier:
```
_ATLASFILE/classifier/datasets/
├── corpus.jsonl                        # fonte unificada
└── splits/{train,validation,test}.jsonl  # 70/15/15
```

### Configuração e extras

- **`config/`** — `topics_v1.yaml` (74 tópicos pt-BR com área-bias), `usage_costs.json` (preços LLM por modelo), `templates/default.json` (template de projeto padrão).
- **`extractor-benchmark/`** — suite de benchmark de extração PDF separada da stack principal (corpus, ground_truth, results, providers).

### Frontend (`frontend/`)

- **Vite 5 + React 18 + TypeScript 5**, strict mode. Sem ESLint configurado.
- **`src/App.tsx`** — componente principal com state management centralizado.
- **`src/api.ts`** — camada de integração com a API (fetch wrapper, usa `VITE_API_URL`).
- **`src/types.ts`** — tipos TypeScript compartilhados (~644 linhas).
- **Features modulares** em `src/features/`: onboarding, ingest, triage, profile-layout, templates, settings, search, usage.
- **`src/components/ChatPanel.tsx`** — UI do assistente conversacional.
- **Testes**: Vitest com jsdom e @testing-library/react. Arquivos `*.test.tsx` co-localizados com features.

### Fluxo principal

```
Arquivo → _INBOX_DROP → dedup SHA256 → extração de texto → classificação (bootstrap/supervisionado)
  → confiança alta: move para 02_AREAS/{business_domain}/{document_type}, indexa no OpenSearch
  → confiança baixa: move para _TRIAGE_REVIEW/pending → triagem humana → training pool
```