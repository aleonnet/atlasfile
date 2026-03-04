# AtlasFile

AtlasFile e um sistema local para organizacao documental por projeto com:

- ingestao automatica por pasta `_INBOX_DROP`;
- classificacao por regras do projeto em `/_PROJECT_PROFILE.md` (com fallback assistido);
- triagem humana no frontend (`Approve`, `Correct`, `Reject`) para baixa confianca;
- indexacao de conteudo e metadados em OpenSearch com ranking BM25;
- rastreabilidade entre nome original e nome canonico.

## Stack

- Backend: FastAPI (Python 3.12)
- Busca: OpenSearch 2.x (BM25)
- Frontend: Vite + React + TypeScript (tema claro/escuro)
- Runtime: Docker Compose

## Estrutura

- `backend/`: API, motor de ingestao, classificador, indexador, triagem.
- `frontend/`: interface de busca e fila de triagem.
- `docs/`: framework, convencoes e governanca.
- `scripts/`: bootstrap de projeto piloto.

## Projeto piloto Kaido

Pasta alvo para validacao:

`/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/Kaidô`

O arquivo `/_PROJECT_PROFILE.md` desse projeto e lido pelo motor para definir:

- areas de `_WORK`;
- regras de roteamento;
- thresholds de confianca;
- aliases e sinonimos.

## Novo projeto (template estilo Kaidô)

Para criar um projeto novo com estrutura padrao numerada (JD):

```bash
python3 scripts/bootstrap_project.py --name "kaidô_teste" --id "kaido_teste"
```

Isso cria:

- `_INBOX_DROP`
- `_TRIAGE_REVIEW/pending|resolved|rejected`
- `_WORK/01_* ... 09_*`
- `_PROJECT_PROFILE.md`
- `_INDEX.md`

## Execucao local com Docker

```bash
docker compose up -d --build
```

Servicos:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- MCP Server (ferramentas para chat/classificação): `http://localhost:8001`
- OpenSearch: `https://localhost:9200` (basic auth)
- OpenSearch Dashboards: `http://localhost:5601`

Variáveis opcionais (env ou `.env`): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (para chat/classificação), `CLASSIFICATION_LLM_ENABLED=true` (habilitar classificação por LLM no ingest).

**Assistente (modelos e chaves):** na UI (Config) há seleção separada de **modelo triagem** e **modelo chat**; as chaves são enviadas apenas na requisição (não armazenadas no servidor). Autenticação hoje é por API Key; OAuth/assinatura está planejado (referência: OpenClaw `src/agents/auth-profiles`).

### Reset do índice OpenSearch

Para recriar o índice com o mapping atualizado (ex.: após incluir `document_type`, `correspondent`, `review_status`):

1. Com o stack no ar, rode: `./scripts/reset-opensearch-index.sh` (ou defina `OPENSEARCH_HOST`, `OPENSEARCH_PASSWORD` se diferente).
2. Reinicie a API (ou o stack): o backend recria o índice no startup (`ensure_index`).
3. Na UI, execute **Reconciliar INDEX** para repopular a partir dos `_INDEX.md` dos projetos.

Credenciais OpenSearch (dev):

- usuario: `admin`
- senha: `Kaid0Search!2026X`

### Dashboard programático (OpenSearch Dashboards)

Os saved objects (index pattern sem time field, visualização “Documentos por tipo”, dashboard “AtlasFile – Visão geral”) estão em `dashboards/atlasfile.ndjson`. O gráfico de barras agrega por `content_type` (docx, pptx, pdf, xlsx, etc.).

1. Com o stack no ar, importe: `./scripts/import-dashboards.sh` (variáveis opcionais: `DASHBOARDS_URL`, `DASHBOARDS_PASSWORD`).
2. Faça login em http://localhost:5601 (admin / senha do OpenSearch) e **mantenha o tenant padrão** (não troque para Global).
3. Abra o dashboard pelo **link direto**: http://localhost:5601/app/dashboards#/view/atlasfile-overview (a lista em Dashboards pode ficar vazia; o link funciona).

O arquivo `config/opensearch_dashboards.yml` é montado no container para o servidor escutar em todas as interfaces.


## Fluxo operacional

1. Usuario salva arquivo em `/<PROJETO>/_INBOX_DROP`.
2. Motor classifica usando `/_PROJECT_PROFILE.md`.
3. Se score >= threshold, move para `/_WORK/<area>`.
4. Se score baixo, move para `/_TRIAGE_REVIEW/pending`.
5. Humano decide no frontend: `Approve`, `Correct` ou `Reject`.
6. Backend atualiza `/_INDEX.md` e indexa no OpenSearch BM25.

## Observacao

Os documentos em `docs/` consolidam as regras e referencias usadas no plano aprovado.
