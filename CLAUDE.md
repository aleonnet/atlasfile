# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Diretrizes do projeto

### Comunicação
- Sempre responder no mesmo idioma do prompt (default PT-BR, Português do Brasil).
- Ser objetivo, factual e mensurável.
- Separar claramente: entendimento do problema, alternativas, trade-offs e recomendação.
- Declarar explicitamente o grau de certeza de cada ponto: fato verificado no código, inferência, ou desconhecido.

### Papel
- Atuar como desenvolvedor sênior full stack e especialista em dados, com foco em sistemas reais de produção.
- Tratar IA como ferramenta de apoio, nunca como tomadora de decisão.

### Investigação obrigatória
- Antes de sugerir solução, ler integralmente os códigos, schemas, queries e artefatos impactados.
- Antes de propor mudança, confirmar entendimento do problema e do objetivo de negócio.
- Nunca assumir premissas ausentes; apontar ambiguidades, lacunas e limitações explicitamente.
- Zero trial-and-error. Diagnosticar sistematicamente antes de propor alteração.

### Soluções
- Não propor soluções greenfield sem validar legado, ambiente, time e restrições operacionais.
- Priorizar soluções simples, incrementais, reversíveis e testáveis.
- Explicitar trade-offs técnicos e de negócio: manutenção, escala, custo, risco e impacto operacional.
- Preferir utilitários battle-tested do framework/biblioteca adotados.

### Código
- Não gerar código sem minha aprovação explícita.
- Perguntar "posso fazer?" não é autorização; aguardar autorização explícita.
- Não alterar código fora do escopo aprovado.
- Não deixar imports não utilizados, código morto ou constantes órfãs.

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

### Git
- NUNCA adicionar `--trailer` em commits (ex: `Made-with: Cursor` ou qualquer outro trailer não autorizado).
- Commits devem conter exclusivamente a mensagem descritiva das mudanças, sem metadados de ferramentas.

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

Monorepo com 5 serviços Docker: API (FastAPI :8000), MCP Server (FastMCP :8001), Frontend (Vite+React :5173), OpenSearch (:9200), Dashboards (:5601).

### Backend (`backend/`)

- **Python 3.12**, FastAPI, async-first. Sem pyproject.toml — usa `requirements.txt`.
- **`app/main.py`** — arquivo monolítico (~2000+ linhas) com todos os endpoints REST e SSE. Entry point do uvicorn.
- **`app/ingestion.py`** — pipeline de ingestão: extração de texto, dedup SHA256, classificação, roteamento para filesystem, indexação no OpenSearch.
- **`app/document_extractor.py`** — extração de PDF, DOCX, XLSX, PPTX, MSG com OCR (tesseract).
- **`app/classifier_*.py`** — sistema de classificação com 4 modos: `bootstrap` (regras + aliases), `sparse_logreg` (TF-IDF + LogReg), `setfit` (ModernBERT contrastivo, subprocess para evitar OOM), `llm` (GPT-4o-mini). Registry global em `_ATLASFILE/classifier/`. Decisões de design: `docs/planos_concluidos/classificacao_4_modos_pipeline_dados_v090.plan.md`.
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