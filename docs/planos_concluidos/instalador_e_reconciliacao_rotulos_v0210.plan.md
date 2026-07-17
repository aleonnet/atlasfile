# Instalador one-liner + reconciliação de rótulos + limpeza (silly-meandering-hollerith)

## Contexto

Três demandas encadeadas pós-encerramento do plano rag_hibrido_permissoes_ui_v2 (v0.20.0):

1. **Limpeza**: os screenshots `.png` de revisão de UI acumulados na raiz do repo (autorizado pelo usuário).
2. **Curadoria de rótulos**: a execução de referência do plano E2E v0.20.0 (score 18/20) revelou que o ground truth é **inconsistente entre versões do corpus** (mesmo SHA com rótulos diferentes em v070/v071/v080) e que hoje conflitos são resolvidos **silenciosamente** ("último ganha" em `build_corpus._load_existing_labels`, sem detecção). Decisão do usuário: não usar LLM como ground truth cego; consenso com arbitragem; **dataset e filesystem não devem descasar** — reconciliar datasets primeiro e oferecer reroteamento dos projetos como passo aplicável (dry-run antes).
3. **Instalador**: one-liner estilo `curl -fsSL .../install.sh | bash` (macOS/Linux) + `install.ps1` fino via WSL2 (Windows), com **teste real de instalação do zero caindo no onboarding**. Distribuição: **GitHub `https://github.com/aleonnet/atlasfile`** (repo criado e vazio — o primeiro push faz parte deste plano).

Fatos verificados na exploração:
- Únicos requisitos de host: Docker + docker compose v2; `.env` com `PROJECTS_HOST_ROOT` (única var obrigatória; `.env.example` existe). `docker compose up -d --build` sobe tudo sem make/node/python.
- Sem git remote configurado hoje.
- Onboarding dispara quando `GET /api/setup/status` → `onboarding_suggested=true` (0 projetos inicializados) e não há flag `atlasfile-onboarding-done` no localStorage — instalação fresh cai nele naturalmente.
- Compose sem healthchecks — instalador deve fazer polling de `/health`.
- `container_name` fixos (atlasfile-*) impedem duas stacks simultâneas — o teste do zero exige parar a stack dev temporariamente.
- Curadoria: fontes de rótulo = `training_pool/records.jsonl` + `validation_set/expected.json`; derivados = `corpus.jsonl` + `splits/` (regenerados por `build_corpus.py`/`build_splits.py`). `label_corpus_llm.py` já tem o plumbing LLM (extração + taxonomia + justificativa + custo via `persist_training_usage`). Anti-leakage por SHA existe em 3 pontos; detecção de divergência de rótulo não existe.

---

## Parte A — Limpeza de screenshots (primeiro passo da execução)

- `rm` dos `*.png` untracked na raiz do repo (`chat-citation.png`, `painel-*.png`, `palette-*.png`, `v2-*.png` … — listar via `git status --short | grep '^??.*\.png'` antes de remover; são todos artefatos de revisão desta sessão, autorizados pelo usuário).
- `.playwright-mcp/` e `/v[0-9]*.png` já estão no `.gitignore` — nada a fazer no git.

## Parte B — Reconciliação de rótulos (consenso + arbitragem, proveniência registrada)

### B1. Novo `backend/scripts/reconcile_labels.py`

Pipeline por SHA256:

1. **Colher fontes de rótulo por SHA**:
   - `training_pool/records.jsonl` — TODOS os records (não só o último; hoje o "último ganha" esconde conflitos internos);
   - `validation_set/expected.json` (+ SHA on-the-fly via `sha256_file`, como `evaluation_dataset.py` já faz);
   - **fonte observacional**: paths `02_AREAS/{bd}/{dt}/` de todos os projetos em `PROJECTS_ROOT` (é onde o caso v070≠v080 aparece), com peso menor.
2. **Detectar conflitos**: SHAs com >1 rótulo distinto (bd ou dt) entre quaisquer fontes.
3. **Propor resolução**:
   - Unanimidade → canônico direto, `labeled_by=consensus`.
   - Conflito → LLM forte como **proponente** (reusar extração/taxonomia/prompt-com-justificativa de `label_corpus_llm.py`; `--model` configurável, default um modelo forte, não gpt-4o-mini; custo registrado via `persist_training_usage`). LLM concorda com ≥1 fonte → canônico, `labeled_by=llm_consensus`; LLM diverge de todas → `pending_human`.
4. **Outputs**: `datasets/label_reconciliation.jsonl` (canônicos com proveniência) + `datasets/label_conflicts_report.md` (resíduo humano com justificativas do LLM, tabela editável — o usuário arbitra editando `resolution:`).
5. **`--apply`**: lê reconciliation + report arbitrado e grava:
   - `validation_set/expected.json` atualizado (rótulos canônicos);
   - records corretivos no training pool para SHAs de treino (respeitando anti-leakage: SHA presente no validation nunca vai para o training);
   - regenera derivados chamando `build_corpus.py` + `build_splits.py`.
6. **`--rehome-projects`** (responde "não descasar"): dry-run listando, por projeto, os arquivos em `02_AREAS` cujo path diverge do canônico, com o move proposto; `--rehome-apply` executa via a lógica do endpoint move existente (`/api/documents/{project}/{doc}/move` já atualiza índice + training pool). Nunca roda sem o dry-run explícito.

### B2. Guardrail permanente

- `compute_dataset_integrity()` (`backend/app/classifier_cycle.py:161`) ganha verificação de **divergência de rótulo por SHA** entre training_pool e validation_set → `warning: label_conflicts [ ... ]` no relatório do ciclo. O silêncio acaba.

### B3. Testes

- Unit para o merge/consenso (fixtures com SHAs em unanimidade, conflito resolvido por LLM-mock, resíduo humano) e para o guardrail de integridade.
- Rodar o reconcile de verdade no corpus atual (30 records + validation) e apresentar o relatório de conflitos ao usuário (a arbitragem humana do resíduo é dele).

## Parte C — Instalador one-liner

### C1. `install.sh` (raiz do repo)

Sem make/node/python no host — só Docker. Idempotente (re-execução segura).

- Flags/env: `--repo-url` (default `https://github.com/aleonnet/atlasfile.git`, sobrescritível via `$ATLASFILE_REPO_URL`), `--branch` (main), `--dir` (default `~/AtlasFile`), `--projects-root` (default `~/Documents/AtlasFileProjects`), `--yes` (não-interativo), `--no-open`.
- Passos: banner → checagens (docker, docker compose v2, git, curl; daemon rodando; portas 5173/8000/9200 livres com mensagem clara se ocupadas) → clone ou `git pull` se `--dir` já existe → `cp .env.example .env` se ausente + gravar `PROJECTS_HOST_ROOT` (prompt com default; `mkdir -p`) → `docker compose up -d --build` → polling `http://localhost:8000/health` (timeout 180s, progresso) → abrir `http://localhost:5173` (`open`/`xdg-open`) → resumo final (URLs, `docker compose logs -f`, link INSTALL.md). Primeiro acesso cai no onboarding por construção (0 projetos no root novo).

### C2. `install.ps1` (fino, WSL2)

- Verifica WSL2 (senão instrui `wsl --install` e sai), verifica Docker Desktop com backend WSL, e executa o one-liner Linux dentro da distro default do WSL. Nada de lógica duplicada.

### C3. Documentação

- `README.md` + `INSTALL.md`: seção "Instalação rápida" no topo com os dois one-liners reais:
  - macOS/Linux: `curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash`
  - Windows: `irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1 | iex`
  - INSTALL.md mantém o caminho manual como alternativa.

### C4. Primeiro push para o GitHub

- `git remote add origin https://github.com/aleonnet/atlasfile.git` e push da `main` (com o commit deste plano incluído) — o repo está vazio; o push inaugural faz parte da execução (autorizado pelo usuário: "precisaremos fazer o primeiro commit lá"). Antes do push, conferir que nada sensível está tracked (`.env`, `config/api_keys.json` e datasets já estão no .gitignore — validar com `git ls-files | grep -iE 'api_key|\.env$'`).

### C5. Teste de instalação do zero (executado por mim, com browser, clonando do GitHub real)

1. Parar a stack dev (`docker compose down` no repo — containers têm nome fixo; **autorizado por este plano**, subo de volta ao final).
2. Rodar o one-liner de verdade: `bash <(curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh)` com `--dir <scratchpad>/atlasfile-fresh --projects-root <scratchpad>/projects-fresh --yes --no-open` — exercita download, clone do GitHub, .env, build e subida reais.
3. Validar: health 200; abrir `http://localhost:5173` via Playwright em estado limpo (localStorage sem flag) → **onboarding aparece** (0 projetos); completar o wizard criando projeto real; screenshot como evidência.
4. Teardown do fresh (`docker compose down -v` no dir fresh) e religar a stack dev; smoke `/health` + `:5173`.

## Fechamento (checklist CLAUDE.md)

- Bump **0.21.0** (minor: instalador + reconcile) em `frontend/package.json`+lock; CHANGELOG.
- Plano salvo em `docs/planos_concluidos/instalador_e_reconciliacao_rotulos_v0210.plan.md` + README de planos.
- Staging + proposta de commit (inclui também os pendentes da rodada anterior ainda não commitados: `docs/workflow_documento.md`, `docs/plano_teste_e2e_v0.20.0.md`, README com stack de UI). Commit só com autorização explícita.

## Arquivos

- Novos: `install.sh`, `install.ps1`, `backend/scripts/reconcile_labels.py`, `backend/tests/unit/test_reconcile_labels.py`, `docs/planos_concluidos/instalador_e_reconciliacao_rotulos_v0210.plan.md`.
- Modificados: `backend/app/classifier_cycle.py` (guardrail em `compute_dataset_integrity`), `README.md`, `INSTALL.md`, `CHANGELOG.md`, `frontend/package.json`+lock, `docs/planos_concluidos/README.md`.
- Reuso: plumbing LLM de `backend/scripts/label_corpus_llm.py`; `sha256_file`/paths de `backend/app/evaluation_dataset.py`; `build_corpus.py`/`build_splits.py` como regeneradores; lógica de move do endpoint existente em `main.py`.

## Verificação

1. `make test` verde (novos units do reconcile + integridade).
2. Reconcile real: relatório de conflitos gerado sobre o corpus atual; conflitos conhecidos da execução E2E (Edital, Programa Twist TI, Procuração, RE Faturamento) detectados; nada aplicado sem `--apply`.
3. Instalação do zero conforme C4, com screenshot do onboarding numa instalação fresh e retorno da stack dev saudável.
4. Guardrail: rodar um ciclo e ver `label_conflicts` no relatório enquanto houver divergência pendente.
