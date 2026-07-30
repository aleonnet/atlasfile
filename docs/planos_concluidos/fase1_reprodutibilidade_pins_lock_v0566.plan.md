# Fase 1 do plano de distribuição — reprodutibilidade da camada de aplicação (v0.56.6)

> Executado em 2026-07-29, na branch `fase1-reprodutibilidade`. Primeira fase
> de `docs/roadmap/distribuicao_build_imagens_ghcr.md`, que segue vigente para
> as Fases 2–4. Inclui a recalibração do próprio plano (escrito contra a
> v0.56.2, validado afirmação a afirmação contra a v0.56.5 antes de executar).

## Contexto

O `install.sh` compila na máquina do usuário, então o artefato instalado nunca
é o artefato testado. A Fase 1 fecha a camada que dava para fechar sem tocar
em arquitetura: deps de aplicação com pino exato e resolve travado.

Defeitos fechados (todos verificados no código antes de mexer):

- 9 de 25 deps do backend com piso `>=` sem teto (`requirements.txt:9,12,16-20,24,25`).
- `requirements-dev.txt` contradizia o produto: `httpx>=0.24.0` contra
  `>=0.27.0`, e `scikit-learn` duplicado — a bancada rodava com piso mais
  baixo que a imagem.
- `lucide-react: "latest"` (único outlier entre 39 deps) + `npm install` no
  `frontend/Dockerfile`, que re-resolvia o dist-tag e reescrevia o lockfile
  dentro da imagem — invisível para o CI, que usa `npm ci`.
- `frontend/` sem `.dockerignore`: o context do `web` é `./frontend`, então o
  `.dockerignore` da raiz não valia e o `node_modules` do host entrava no
  `COPY . .`.

## Recalibração que precedeu a execução

Validação por 3 agentes (~90 afirmações do plano contra o código v0.56.5):

- **Correção material**: o "piso falso do `mcp`" não era `ImportError` provado
  em resolve limpo — pip resolve o topo, não o piso. O risco real é ambiente
  que satisfaz `>=1.0.0` com `mcp` antigo (o pyenv global desta máquina tem
  1.9.3, sem `streamable_http_client`). Narrativa corrigida no plano.
- **Achado novo**: o venv de referência é Python **3.11**; a imagem é
  `python:3.12-slim`. O lock não podia nascer de `pip freeze` local.
- Itens já resolvidos pelas v0.56.3–v0.56.5 marcados (o "~15 min", o
  `--dry-run`); números de origem corrigidos (bancada Linux: 1.488 linhas e 60
  asserções estáticas, não 1.394/201; `check_consistency.py`: 13 checks);
  drift do site registrado (4 comandos publicam `--with-ollama`, no-op
  depreciado desde a v0.55.0).
- `plan_one_line_installer.md` (superado) movido de `docs/roadmap/` para
  `docs/planos_concluidos/`, por decisão do autor — reverte o "marcar
  superado, não mover" da auditoria v0.56.1; o CHANGELOG segue apontando o
  caminho antigo como registro histórico.

## Mudanças

| Arquivo | Mudança |
|---|---|
| `backend/requirements.txt` | 9 `>=` → `==` na versão do venv de referência (`pymupdf==1.27.2.2`, `Pillow==12.1.1`, `duckdb==1.5.4`, `mcp==1.26.0`, `httpx==0.28.1`, `openai==2.24.0`, `anthropic==0.84.0`, `aiogram==3.26.0`, `matplotlib==3.10.8`) |
| `backend/requirements.lock.txt` | **Novo**: resolve inteiro (99 pacotes) congelado em `python:3.12-slim` a partir SÓ do requirements.txt; proveniência e comando de regeneração no cabeçalho |
| `backend/requirements-dev.txt` | Remove `httpx>=0.24.0` e a duplicata de `scikit-learn`; passa a `-r requirements.lock.txt` |
| `backend/Dockerfile` | Instala do lock (`COPY`/`pip install -r requirements.lock.txt`) |
| `frontend/package.json` | `lucide-react: "latest"` → `"^0.576.0"`; lockfile atualizado via `npm install --package-lock-only` (diff extra: normalização de metadata bundled do npm local, sem mudança de versão) |
| `frontend/Dockerfile` | `npm install` → `npm ci`; `package-lock.json` deixa de ser opcional no COPY |
| `frontend/.dockerignore` | **Novo**: `node_modules`, `dist`, `coverage` |
| `scripts/check_pins.sh` | **Novo**: guarda de pins (requirements.txt + requirements-local-embeddings.txt + package.json), mesma execução no CI e local |
| `backend/requirements-local-embeddings.txt` | `fastembed>=0.4.0` → `==0.8.0` com proveniência no comentário |
| `.github/workflows/ci.yml` | Job novo `pins`; cache do backend inclui o lock; comentário do requirements-dev atualizado |
| `backend/tests/unit/test_mcp_client_import.py` | **Novo**: importa `app.mcp_client.client` sem patch e afirma que `streamable_http_client` real resolve |
| `INSTALL.md:178` | Setup de testes aponta `requirements-dev.txt` (que instala o lock) |
| `docs/roadmap/distribuicao_build_imagens_ghcr.md` | Recalibrado (ver seção acima) |

## Decisões

- **Pinos = versões do venv de referência** (o ambiente onde a suíte roda há
  semanas), não o topo do índice — bump de versão vira ato deliberado com
  bancada verde.
- **Lock gerado no container 3.12**, não no venv 3.11 — o lock do produto tem
  de nascer na plataforma do produto.
- **Dev instala o lock** — elimina a classe "bancada com resolve diferente do
  produto" pela raiz.
- `requirements-local-embeddings.txt`: **pinado por decisão do autor**
  (`fastembed>=0.4.0` → `==0.8.0`, o resolve do dia — não havia versão
  instalada no venv para herdar) e **coberto pela guarda**. O extra não tem
  bancada própria; bump exige teste manual do provider. Resolve provado limpo
  por cima do lock (`pip check` em `python:3.12-slim`).

## Testes e validações (executados)

| Prova | Resultado |
|---|---|
| `scripts/check_pins.sh` no estado real | OK, exit 0 |
| Mutante `openai>=1.0.0` no requirements.txt | **FAIL, exit 1** (revertido) |
| Mutante `lucide-react: "latest"` no package.json | **FAIL, exit 1** (revertido) |
| Guarda estendida contra o `fastembed>=0.4.0` real (mutante natural) | **FAIL, exit 1** antes do pin; OK depois |
| `fastembed==0.8.0` por cima do lock em `python:3.12-slim` | instala e `pip check` → "No broken requirements found" |
| `test_mcp_client_import.py` no venv (mcp 1.26.0) | 1 passed |
| Mutante em `python:3.12-slim` + lock + `pip install mcp==1.9.3` | **1 failed** com a mensagem desenhada ("não exporta streamable_http_client") |
| Mesmo container com o lock puro (mcp 1.26.0) | 1 passed |
| `make test-backend` | 732 passed |
| `make test` (frontend + bancadas) | 252 passed (33 files) + 218 passed + consistência OK |
| `docker compose build api` com o lock | Built |
| `docker compose build web` com `npm ci` + `.dockerignore` | Built; `npm ci` 5.6s, `COPY . .` instantâneo |

Prova pendente (exige push): o job `pins` vermelho num branch descartável com
mutante — a lógica é a mesma do script já provado localmente, mas a fiação do
CI só se prova no CI.

## O que esta fase NÃO entrega

Apt sem versão, imagem base sem digest e prova funcional da imagem — Fases 2–3
do plano. "Reprodutibilidade resolvida" continua sendo frase proibida.
