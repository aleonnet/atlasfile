# AtlasFile - Guia de Instalacao (Mac e Windows)

Este guia cobre o setup completo para qualquer pessoa rodar o AtlasFile localmente.

---

## 1) Pre-requisitos

### Obrigatorio

- Docker Desktop instalado
  - Mac: <https://www.docker.com/products/docker-desktop/>
  - Windows: <https://www.docker.com/products/docker-desktop/>

### Validacao rapida

Abra o terminal e rode:

```bash
docker version
docker compose version
```

Se os dois responderem sem erro, o Docker esta pronto.

---

## 2) Obter o projeto

Clone ou copie o repositorio e entre na pasta:

```bash
cd AtlasFile
```

---

## 3) Ajustar caminho de projetos no host

O backend precisa montar uma pasta local com os projetos.

No `docker-compose.yml`, ajuste o bind mount do servico `api`:

```yaml
services:
  api:
    volumes:
      - <CAMINHO_LOCAL_PROJETOS>:/projects
```

### Exemplos de caminho

- Mac:
  - `/Users/<seu_usuario>/Documents/Projects:/projects`
- Windows (Docker Desktop + WSL/Compose):
  - `C:\Users\<seu_usuario>\Documents\Projects:/projects`

> Dica: confirme que a pasta existe e que o Docker Desktop tem permissao para acessa-la.

---

## 4) Testes antes de atualizar o Docker

Antes de subir ou atualizar os containers, rode os testes para garantir que backend e frontend estao ok:

```bash
bash scripts/ci.sh
```

Ou `./scripts/ci.sh` (se executavel: `chmod +x scripts/ci.sh`). Se tiver Make instalado:

```bash
make test
```

Comandos individuais:

- Backend: `cd backend && python -m pytest tests/ -v` (requer `pip install -r requirements-dev.txt`)
- Frontend: `cd frontend && npm run test`

Apos os testes passarem, atualize **sempre os dois servicos** (api e web) para garantir que esteja usando as ultimas versoes:

```bash
docker compose up -d --build api web
docker compose ps
```

---

## 5) Subir os servicos

Na raiz do projeto (primeira vez ou rebuild completo):

```bash
docker compose up -d --build
docker compose ps
```

Servicos esperados:

- `atlasfile-opensearch`
- `atlasfile-api`
- `atlasfile-web`
- `atlasfile-dashboards`

---

## 6) Verificacao de saude

### Frontend

- <http://localhost:5173>

### Backend

```bash
curl http://localhost:8000/health
```

Resposta esperada:

```json
{"status":"ok"}
```

### OpenSearch

```bash
curl -k -u "admin:Kaid0Search!2026X" https://localhost:9200
```

---

## 7) Criar projeto de teste (bootstrap)

Exemplo (template estilo Kaido):

```bash
python3 scripts/bootstrap_project.py --name "kaido_teste" --id "kaido_teste"
```

Isso cria:

- `/_INBOX_DROP`
- `/_TRIAGE_REVIEW/pending|resolved|rejected`
- `/_WORK/01_* ... 09_*`
- `/_PROJECT_PROFILE.md`
- `/_INDEX.md`

---

## 8) Teste funcional rapido (fim-a-fim)

1. Copie um arquivo para:
   - `<ProjectsRoot>/kaido_teste/_INBOX_DROP`

2. Dispare o scan:

```bash
curl -X POST http://localhost:8000/api/ingest/scan/kaido_teste
```

3. Abra o frontend:
   - <http://localhost:5173>

4. Resultado esperado:
   - arquivo roteado para `/_WORK/NN_area` (se confianca alta), ou
   - item em triagem para `Approve/Correct/Reject`.

---

## 9) Operacao diaria

- Ingestao:
  - coloque arquivos em `/<PROJETO>/_INBOX_DROP`
- Triagem humana:
  - use a tela do frontend para decidir pendencias
- Busca:
  - use o campo de busca no frontend (BM25)

---

## 10) Atualizacao Docker apos mudancas de codigo

Antes de fazer rebuild, rode os testes (secao 4): `bash scripts/ci.sh` ou `make test`.

**Recomendado:** para garantir que esteja sempre usando as ultimas versoes dos pares backend/api e frontend/web, atualize **sempre os dois servicos** apos os testes:

```bash
make docker-update
```

Ou manualmente:

```bash
docker compose up -d --build api web
docker compose ps
```

### Rebuild apenas um servico (opcional)

Use apenas se tiver certeza de que so alterou um lado:

- Só backend: `docker compose up -d --build api`
- Só frontend: `docker compose up -d --build web`

### Rebuild completo (todas as imagens)

```bash
docker compose down
docker compose up -d --build
```

---

## 11) Troubleshooting

### Docker Desktop: "Integrity issue detected"

1. Clique em **Repair**
2. Reinicie o Docker Desktop
3. Rode novamente:
   - `docker version`
   - `docker compose version`

### API nao sobe

Verifique logs:

```bash
docker compose logs api --tail=200
```

### OpenSearch nao sobe

Verifique logs:

```bash
docker compose logs opensearch --tail=200
```

### Subiu parcialmente

Recrie stack:

```bash
docker compose down
docker compose up -d --build
```

### Limpar ambiente local (containers + rede + volume do projeto)

```bash
docker compose down -v
```

---

## 12) Credenciais e portas (dev)

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- OpenSearch: `https://localhost:9200`
- Dashboards: `http://localhost:5601`
- OpenSearch user: `admin`
- OpenSearch pass: `Kaid0Search!2026X`

> Ambiente local de desenvolvimento. Nao usar credenciais fixas em producao.
