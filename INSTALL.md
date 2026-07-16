# AtlasFile - Guia de Instalação (Mac, Linux e Windows)

Este guia cobre o setup completo para qualquer pessoa rodar o AtlasFile localmente.

Para uma visão consolidada dos scripts do repositório e de quando cada um entra no processo, veja `docs/11_scripts_and_operations.md`.

---

## 1) Pré-requisitos

### Obrigatório

- Docker Desktop instalado
  - Mac: <https://www.docker.com/products/docker-desktop/>
  - Windows: <https://www.docker.com/products/docker-desktop/>
  - Linux: <https://docs.docker.com/engine/install/>

### Validação rápida

Abra o terminal e rode:

```bash
docker version
docker compose version
```

Se os dois responderem sem erro, o Docker está pronto.

---

## 2) Obter o projeto

Clone ou copie o repositório e entre na pasta:

```bash
cd AtlasFile
```

---

## 3) Configurar variáveis de ambiente

Copie o arquivo de exemplo e edite:

```bash
cp .env.example .env
```

O campo **obrigatório** é `PROJECTS_HOST_ROOT` — o path absoluto no host onde ficam seus projetos. Este diretório será montado como `/projects` dentro do container.

Esse mesmo root também passa a armazenar o estado operacional compartilhado do AtlasFile em `PROJECTS_HOST_ROOT/_ATLASFILE/`, incluindo registry, reports, models e datasets vivos do classificador.

### Exemplos

```bash
# macOS
PROJECTS_HOST_ROOT=/Users/seu_usuario/Documents/Projects

# Linux
PROJECTS_HOST_ROOT=/home/seu_usuario/Documents/Projects

# Windows (WSL)
PROJECTS_HOST_ROOT=/mnt/c/Users/seu_usuario/Documents/Projects
```

Se a pasta não existir, o AtlasFile a cria automaticamente no primeiro uso.

### Variáveis opcionais

```bash
# Chaves LLM (para chat e classificação assistida)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Habilitar LLM no fluxo de ingestão (default: false)
CLASSIFICATION_LLM_ENABLED=true

# Root operacional dos datasets do classificador
# Default recomendado: não alterar
CLASSIFIER_DATASETS_ROOT=/projects/_ATLASFILE/classifier/datasets
```

```bash
# Embeddings / busca semântica (default: habilitado com provider openai)
# EMBEDDING_ENABLED=true
# EMBEDDING_PROVIDER=openai   # ou "fastembed" (local, sem API):
#   cd backend && .venv/bin/pip install -r requirements-local-embeddings.txt
```

Para popular embeddings de um corpus já indexado (migração), rode:

```bash
cd backend && .venv/bin/python scripts/backfill_embeddings.py           # idempotente
cd backend && .venv/bin/python scripts/backfill_embeddings.py --force   # re-embedar tudo
```

Veja `.env.example` para a lista completa de variáveis (CORS, OpenSearch, reconciliação, embeddings, etc.).

---

## 4) Testes antes de subir

Antes de subir ou atualizar os containers, rode os testes:

```bash
make test
```

Ou individualmente:

- Backend: `cd backend && python -m pytest tests/ -v` (requer virtualenv com `pip install -r requirements.txt`)
- Frontend: `cd frontend && npm run test`

---

## 5) O que acontece no primeiro boot

Depois do primeiro `make docker-update`, o AtlasFile passa a usar `PROJECTS_HOST_ROOT/_ATLASFILE/` como estado operacional persistido:

```text
<PROJECTS_HOST_ROOT>/
├── _ATLASFILE/
│   └── classifier/
│       ├── datasets/
│       │   ├── validation_set/
│       │   │   ├── files/
│       │   │   └── expected.json
│       │   └── training_pool/
│       │       ├── files/
│       │       └── records.jsonl
│       ├── models/
│       ├── reports/
│       └── registry.json
└── <SEUS_PROJETOS>/
```

Estado inicial de um AtlasFile novo:

- a ingestão já funciona com o classificador `bootstrap`, sem depender de `validation_set` ou `training_pool` previamente populados;
- `validation_set` e `training_pool` começam vazios no root operacional;
- benchmark e retreino supervisionado só ficam úteis depois que você alimentar o `validation_set` com arquivos reais e acumular exemplos revisados no `training_pool`.

O repo não é mais usado como seed automático desses datasets no runtime.

---

## 6) Subir os serviços

### Primeira vez ou rebuild completo

```bash
make docker-update
```

Isso roda os testes, faz build das imagens, sobe todos os serviços e executa o smoke test de inicialização.

### Alternativa manual

```bash
docker compose up -d --build
```

### Serviços esperados

```bash
docker compose ps
```

| Container | Serviço | Porta |
|-----------|---------|-------|
| `atlasfile-opensearch` | OpenSearch 2.17 | 9200 |
| `atlasfile-dashboards` | OpenSearch Dashboards | 5601 |
| `atlasfile-api` | Backend FastAPI | 8000 |
| `atlasfile-mcp` | MCP Server (tools para LLM) | 8001 |
| `atlasfile-web` | Frontend React | 5173 |

---

## 7) Verificação de saúde

### Frontend

Abra <http://localhost:5173> — a interface deve carregar com o seletor de projetos no header.

### Backend

```bash
curl http://localhost:8000/health
```

Resposta esperada: `{"status":"ok"}`

### OpenSearch

```bash
curl -k -u "admin:Kaid0Search!2026X" https://localhost:9200
```

---

## 8) Criar um projeto

### Via UI (recomendado)

1. No seletor de projetos do header, selecione uma pasta do seu `PROJECTS_HOST_ROOT`.
2. O modal de inicialização aparece com templates disponíveis.
3. Selecione um template (ex: "M&A / Carve-out") e clique em "Inicializar com template".
4. O AtlasFile cria a estrutura completa:

```
/<PROJETO>/
├── _INBOX_DROP/
├── _TRIAGE_REVIEW/pending|resolved|rejected
├── _PROFILE/profile.json
├── 01_contratos_comunicacao/
├── 02_financeiro/
├── ...
└── _INDEX.md
```

### Via script (requer virtualenv do backend)

```bash
# Template padrão (M&A / Carve-out)
python3 scripts/bootstrap_project.py --name "meu_projeto"

# Com template específico e label legível
python3 scripts/bootstrap_project.py --name "due_diligence" --template default --label "Due Diligence Alfa"
```

O script reutiliza os mesmos módulos do backend (`profile_store`, `bootstrap`), garantindo que o `profile.json` e a estrutura de pastas sejam idênticos ao que a API produz.

---

## 9) Preparar datasets do classificador (opcional)

Para um AtlasFile novo do zero, esta etapa é opcional. Só é necessária quando você quiser usar benchmark, score comparativo e ciclo supervisionado com dados reais.

### `validation_set`

Popule o dataset operacional com arquivos reais usando o script do backend (requer ambiente Python do backend já configurado):

```bash
cd backend
python scripts/bootstrap_validation_set.py "/caminho/para/documentos_reais"
```

Isso copia os arquivos aceitos para `PROJECTS_HOST_ROOT/_ATLASFILE/classifier/datasets/validation_set/files/` e sincroniza `expected.json`.

### `training_pool`

O `training_pool` operacional é alimentado automaticamente por decisões `Approve` / `Correct` na triagem. Para importar histórico já revisado de um projeto (também requer ambiente Python do backend):

```bash
cd backend
python scripts/backfill_training_pool.py "/caminho/absoluto/do/projeto" --replace-project-records
```

Isso grava snapshots estáveis e atualiza `PROJECTS_HOST_ROOT/_ATLASFILE/classifier/datasets/training_pool/`.

---

## 10) Teste funcional rápido (fim a fim)

1. Copie um arquivo para `<PROJECTS_HOST_ROOT>/meu_projeto/_INBOX_DROP/`

2. Na UI (<http://localhost:5173>), selecione o projeto e clique em **Processar INBOX** no card "Ingestão e triagem".

3. Resultado esperado:
   - Arquivo roteado para `02_AREAS/{business_domain}/{document_type}/` (se confiança alta), ou
   - Item em triagem pendente para `Approve/Correct/Reject`.

4. Se você aprovar ou corrigir um item na triagem, o AtlasFile também atualiza o `training_pool` operacional em `_ATLASFILE/classifier/datasets/training_pool/`.

5. Use a busca (Cmd+K ou Enter) para localizar o documento indexado.

### Via API (alternativa)

```bash
curl -X POST http://localhost:8000/api/ingest/scan/meu_projeto
```

---

## 11) Operação diária

- **Ingestão**: coloque arquivos em `/<PROJETO>/_INBOX_DROP/`
- **Processamento**: clique em "Processar INBOX" na UI ou aguarde reconciliação automática
- **Triagem**: decida pendências no card de triagem (Approve, Correct, Reject)
- **Busca**: use Cmd+K para busca rápida ou o card "Resultados completos" com filtros
- **Chat**: use o assistente LLM (aba "Assistente") para perguntas sobre os documentos

---

## 12) Atualização Docker após mudanças de código

O comando recomendado roda testes, faz rebuild e smoke test:

```bash
make docker-update
```

### Opções adicionais

```bash
# Resetar índice de documentos (requer reconciliação depois)
make docker-update RESET_INDEX=1

# Resetar índice de sessões de chat
make docker-update RESET_CHAT=1

# Resetar ambos os índices
make docker-update RESET_INDEX=1 RESET_CHAT=1

# Rebuild completo (todas as imagens, do zero)
docker compose down
docker compose up -d --build

# Rebuild de um serviço específico
docker compose up -d --build api
docker compose up -d --build web
```

---

## 13) Makefile targets

| Target | O que faz |
|--------|-----------|
| `make test` | Roda todos os testes (backend + frontend) |
| `make docker-update` | Testa + rebuild + sobe stack + smoke test |
| `make docker-update RESET_INDEX=1` | Idem + reseta índice de documentos |
| `make docker-update RESET_CHAT=1` | Idem + reseta índice de sessões de chat |
| `make docker-up` | Sobe stack sem rodar testes |
| `make docker-build` | Testa + build das imagens (sem subir) |
| `make reset-index` | Remove índice de documentos |
| `make reset-chat` | Remove índice de sessões de chat |

---

## 14) Troubleshooting

### Docker Desktop: "Integrity issue detected"

1. Clique em **Repair**
2. Reinicie o Docker Desktop
3. Rode: `docker version && docker compose version`

### API não sobe

```bash
docker compose logs api --tail=200
```

### OpenSearch não sobe

```bash
docker compose logs opensearch --tail=200
```

### Subiu parcialmente

```bash
docker compose down
docker compose up -d --build
```

### Limpar ambiente local (containers + rede + volumes)

```bash
docker compose down -v
```

### Reset de índices OpenSearch

Para recriar índices com mapping atualizado (ex.: após upgrade):

1. Documentos: `make reset-index` — depois execute **Reconciliar INDEX** na UI para repopular
2. Sessões de chat: `make reset-chat` — limpa histórico de conversas do assistente
3. Ambos: `make docker-update RESET_INDEX=1 RESET_CHAT=1`

---

## 15) Credenciais e portas (dev)

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | — |
| Backend API | http://localhost:8000 | — |
| MCP Server | http://localhost:8001 | — |
| OpenSearch | https://localhost:9200 | admin / Kaid0Search!2026X |
| Dashboards | http://localhost:5601 | admin / Kaid0Search!2026X |

> Ambiente local de desenvolvimento. Não usar credenciais fixas em produção.

---

## 16) Dashboard programático (OpenSearch Dashboards)

Os saved objects estão em `dashboards/atlasfile.ndjson`.

1. Com o stack no ar, importe: `./scripts/import-dashboards.sh`
2. Faça login em http://localhost:5601 (admin / senha do OpenSearch) e mantenha o tenant padrão.
3. Abra o dashboard pelo link direto: http://localhost:5601/app/dashboards#/view/atlasfile-overview

---

## 17) Backup

Para gerar um backup versionado do repositório (exclui `node_modules`, `.venv`, `dist`, etc.):

```bash
./backup-atlasfile.sh
```

Saída: `AtlasFile_v<versão>_YYYYMMDD.tar.gz` no diretório pai do projeto.
