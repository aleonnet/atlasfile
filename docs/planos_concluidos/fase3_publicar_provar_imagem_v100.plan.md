# Fase 3 — Publicar e provar a imagem (GHCR) — v1.0.0

> Executada em 2026-07-30 na branch `fase3-publicar-imagem`. Fase 3 de
> `docs/roadmap/distribuicao_build_imagens_ghcr.md`. Primeira tag da história
> do repositório: **v1.0.0**, precedida do ensaio **v1.0.0-rc.1** (prerelease).
> O plano foi revisado ANTES da execução por 3 revisores adversariais locais
> (fatos do repo × desenho do workflow × completude vs roadmap/regras) — rigor
> de ultraplan sem sair da máquina, a pedido do autor. A revisão derrubou 3
> bloqueantes do rascunho e mudou o escopo: **a Fase 3 teve de tocar o
> `install.sh`** (mínimo para não quebrar o one-liner e o uninstall).

## Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| Primeira tag | `v1.0.0` (major) | Régua **operacional**, não de API: o contrato de deploy quebra (compose vira consumo, `ATLASFILE_VERSION` obrigatória) e a primeira imagem pública com prova funcional é compromisso de estabilidade. Roadmap autorizava as duas séries |
| Ensaio | `v1.0.0-rc.1` antes | O pipeline só é testável com tag real (runners ARM, GHCR, provenance); a 1ª tag da história não pode ser também o debug do pipeline. Pacote GHCR nasce **privado** — o flip para público acontece entre o rc verde e a v1.0.0 |
| Versão consultável | Sim | `ARG ATLASFILE_VERSION` → env → `/api/setup/status.version` — sem isso o smoke não afirma "a imagem publicada é a vX" por HTTP |
| Overlay renomeia a imagem | `atlasfile-local:dev` | Bits locais nunca usurpam o nome oficial; o `COPY config` assa o config do dev; tag fixa preserva o `docker image prune` de hoje |
| Jobs do release | 4 (não 6) | `manifest`+`attest`+`release` fundidos em `publish` — simplificação sugerida e aceita na revisão; o invariante fica intacto |

## O que a revisão adversarial derrubou (e virou requisito)

1. **BLOQUEANTE — triagem não indexa.** O rascunho supunha doc pendente
   buscável; `index_document` só roda com `decision == "auto"`
   (`ingestion.py:820-822`) e o classificador real dá 0,7598 < 0,85 para a
   própria fixture do smoke (provado executando o pipeline). O smoke passou a
   **aprovar a triagem** — que é também o fluxo humano real.
2. **BLOQUEANTE — `install.sh` quebraria** (`compose build` vira no-op com
   exit 0 e `up` aborta no `:?` sem `ATLASFILE_VERSION`) → instalador grava a
   var e usa o overlay; segue buildando local até a Fase 4a.
3. **BLOQUEANTE — `--uninstall` travaria** no `:?` com `.env` pré-1.0.0
   (`un_execute` para de propósito quando o down falha) → fallback na
   interpolação do down.
4. **ALTO — uninstall vazaria a imagem**: `down --rmi local` não remove imagem
   com `image:` nomeado → `un_collect` lista `ghcr.io/aleonnet/atlasfile:*` e
   `atlasfile-local:*` com remoção explícita e passo próprio na tela.
5. **ALTOS do workflow**: artifact não aceita `/` no nome; digest passa por
   arquivo nomeado pelo próprio digest (merge-multiple sobrescreveria nomes
   fixos → index de 1 arch); `DASHBOARDS_COOKIE_PASSWORD` obrigatória no .env
   do smoke (interpolação roda ANTES do filtro de profiles — provado no
   compose v5.3.1); login no GHCR no job smoke (pacote privado no rc); `needs`
   só expõe outputs de dependência direta; `::add-mask::` na key gerada;
   `tools/call` asserido por `result.isError`, não por HTTP 200.
6. **Guardas na tag** (branch protection segue desligada): formato, tag∈main
   (`merge-base --is-ancestor`), tag↔`frontend/package.json`.

## Entregas

- **`.github/workflows/release.yml`** — `version` → `build` (matrix
  amd64/`ubuntu-latest` + arm64/`ubuntu-24.04-arm`, push por digest, cache gha
  por plataforma, labels OCI) → `smoke` (matrix, stack pela imagem por digest,
  auth ligado) → `publish` (`imagetools create` + prova multi-arch por grep +
  `attest-build-provenance` + bundle ~10 KB + GitHub Release; prerelease sem
  `latest`/`X.Y` pela regra documentada do `metadata-action type=semver`).
  Invariante: **tags só depois dos 2 smokes verdes**; smoke vermelho deixa só
  digests sem tag. Rollback: nunca re-taguear X.Y.Z ruim — publica-se X.Y.(Z+1).
- **`scripts/smoke-e2e.sh`** — versão==tag, upload nativo+escaneado (nomes com
  espaço/acento de propósito), scan determinístico (`EMBEDDING_ENABLED=false`,
  `AUTO_INGEST_ENABLED=false`, agora repassadas pelo compose), triagem
  aprovada, busca com highlight da sentinela OCR (`SENTINELA QUARENTA E DOIS`
  — 4 tokens, abaixo do gatilho do strict_mode), sequência MCP validada contra
  o SDK 1.26.0 (401 → initialize → `mcp-session-id` → 202 → `get_stats` sem
  `isError`), e prova de que a imagem não contém `config/api_keys.json`.
  `smoke-project-init.sh` aprendeu `ATLASFILE_SMOKE_API_KEY` (header, nunca
  query string).
- **Compose**: base vira consumo (`image:` com `ATLASFILE_IMAGE`/`ATLASFILE_VERSION`
  aninhadas — lazy, provado; `:?` com mensagem que ensina o caminho), OpenSearch
  e Dashboards pinados por digest, `start_period` 90s; overlay
  `docker-compose.build.yml` (`atlasfile-local:dev`); `Makefile` com
  `COMPOSE_DEV` + `ensure-atlasfile-version` (sed BSD-safe, sem jq).
- **Backend/Frontend**: `ARG/ENV ATLASFILE_VERSION` no Dockerfile,
  `atlasfile_version` no settings, campo `version` no `/api/setup/status`
  (+ teste), `SetupStatus.version?` em `api.ts`.
- **Fixture de OCR** (`backend/tests/fixtures/ocr/`): gerador com proveniência
  (PIL + pymupdf, JPEG grayscale q85 → 151 KB, 1 página só-imagem) e
  `test_pdf_ocr_fixture.py` — primeiro exercício do OCR de PDF **sem
  monkeypatch**, com âncora que reprova se a fixture ganhar camada de texto.
- **`install.sh`**: grava `ATLASFILE_VERSION` (novo e preexistente), overlay no
  build/up, uninstall com fallback de interpolação + remoção explícita de
  imagens nomeadas (passo próprio na tela — a ação acontece e a tela conta).
- **`ci.yml`**: job `docker-build` com `ATLASFILE_VERSION=dev` + overlay;
  comentário obsoleto do `frontend/Dockerfile` corrigido.
- **Docs**: CHANGELOG 1.0.0 (major justificado), READMEs (imagem oficial,
  tabela de env), INSTALL.md (trilhas usuário×desenvolvedor explícitas + todas
  as ocorrências de `--build`/`logs api`/`--rmi local` corrigidas).

## Guardas novas × prova

| Guarda | Prova |
|---|---|
| Digest de terceiros no compose (`check_pins.sh`) | **Mutante local**: digest removido → FAIL, exit 1 |
| `un_collect` casa imagens nomeadas (bancada `run.sh`) | **Mutante local**: correção revertida → 2 FAILs exatos; restaurada → 223 PASS |
| Sentinela/key/versão do smoke | Mutantes na validação local (VM lima) |
| Regex/ancestor/package.json do job `version` | **Ensaio rc.1** (guardas que só vivem no Actions) |
| Âncora da fixture (sem camada de texto) | Teste unit dedicado |

## Fora de escopo, com nota

- **Site** (`atlasfile-website`): drift "five Docker services"/58s é herdado da
  Fase 2 e a Fase 3 não muda o que o site publica; corrigir junto da 4a.
- **Achado lateral pendente de decisão do autor**: upload sem sanitização de
  filename (`main.py` `upload_to_inbox` — `dest = inbox / original_name`
  aceita traversal). Pré-existente; não incluído por disciplina de escopo.
- Assimetria do rc: sidebar `v1.0.0` (bundle) × `/api/setup/status`
  `1.0.0-rc.1` (tag) — esperada, documentada no CHANGELOG.

## Validação (roteiro executado/a executar)

1. Local: `make test` completo; `compose config` (3 cenários: overlay, versão,
   `:?`); mutantes acima; smoke completo na VM lima contra `atlasfile-local:dev`.
2. PR + CI verde → merge (decisão do autor).
3. `git tag -a v1.0.0-rc.1` (disparo do autor) → run verde → flip do pacote
   GHCR para público → pull anônimo, `imagetools inspect` (2 archs),
   `gh attestation verify`, medição do pull real.
4. Migração na VM lima: `git pull` + `make docker-update` (build local, `.env`
   antigo ganha a var, volume e dados sobrevivem) + uninstall sem vazar imagem.
5. `git tag -a v1.0.0` (disparo do autor) → mesma validação → Release final.
