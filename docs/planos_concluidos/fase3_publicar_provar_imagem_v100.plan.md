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

## Validação executada (2026-07-30)

1. **Local**: `make test` completo verde (backend + 253 frontend + 223
   instalador + consistência + parse ps1); `compose config` nos 3 cenários
   (overlay OK, versão resolve, `:?` com mensagem clara, `ATLASFILE_IMAGE`
   lazy provado); imagem buildada pelo overlay com ENV de versão correto.
2. **PR #12 com CI 7/7 verde** — inclusive `docker-build` com overlay, job
   `pins` com a guarda de digest e backend rodando o teste de OCR real.
3. **VM lima (atlas-e2e, Ubuntu 24.04 ARM64, recriada do zero)**:
   - Instalação REAL da 0.57.0 pelo one-liner de main (2m15s, auth ligado) +
     seed (projeto, PDF ingerido, triagem aprovada, busca com 1 hit).
   - **Migração real pelo instalador** (`--branch fase3-publicar-imagem`):
     build pelo overlay em 51s, `.env` antigo preservado ganhando
     `ATLASFILE_VERSION=1.0.0` (1 ocorrência), container `atlasfile-local:dev`
     healthy, `/api/setup/status.version == 1.0.0` (o ARG atravessou
     instalador→overlay→imagem), **dado semeado sobreviveu** (busca 1 hit).
   - **Smoke E2E completo verde** na stack migrada: versão, 2 uploads, scan
     determinístico, 2 triagens aprovadas, highlight da sentinela OCR, busca
     do nativo, `/mcp` 401→sessão→`get_stats` sem `isError`.
   - **3 mutantes do smoke reprovaram**: versão errada, key errada e —
     depois de endurecer a guarda — sentinela errada (ver achado 2).
   - **Uninstall sem vazamento**: com `atlasfile-local:dev` E a legada
     `atlasfile-atlasfile:latest` no disco, `--uninstall --yes --purge-data`
     removeu containers, volume e AS DUAS imagens; documentos intocados.

## Achados da validação (fatos novos)

1. **`af_update_clone` não faz update cross-branch** (pré-existente): o clone
   nasce `--depth 1 --branch main`, a refspec do remote só cobre `main`, e
   `git fetch origin <outra-branch>` não cria `origin/<branch>` — merge e
   reset falham ("not something we can merge" / "unknown revision"). O
   caminho real do usuário (re-executar na MESMA branch) não é afetado; o
   teste contornou com `remote.origin.fetch` wildcard na VM. **Corrigir na
   Fase 4a** (o update é reescrito lá; a correção é fetch com refspec
   explícita `+refs/heads/<b>:refs/remotes/origin/<b>`).
2. **Mutante derrubou a 1ª versão da guarda de highlight**: asserir a
   substring "SENTINELA" no snippet passava até com query errada — a busca
   lexical casa token parcial e o snippet carrega o resto da frase do
   documento. Guarda corrigida para exigir os TRÊS termos de conteúdo
   MARCADOS pelo highlighter (`<em>`); mutante re-rodado reprova e o smoke
   verdadeiro passa. Exatamente o motivo da regra "guarda se prova com
   mutante".
3. **Uninstall pós-update preserva o clone** (pré-existente): a re-execução
   do instalador grava `repo_clone=updated` no manifesto por cima do
   `created` original, e o uninstall — por desenho — só remove clone
   `created`. Sub-remoção conservadora (o `.env` e a key são removidos);
   revisitar na Fase 4a junto do update.

## O ensaio rc.1 fez o seu trabalho (2026-07-30, run 30596195322)

O primeiro disparo do `release.yml` (`v1.0.0-rc.1`) **reprovou no smoke das
duas archs** — e o invariante segurou exatamente como desenhado: `publish`
nunca rodou, **nenhuma tag foi aplicada no GHCR**, sobraram só dois digests
sem tag (invisíveis a pull). Três defeitos reais no `smoke-project-init.sh`,
corrigidos e revalidados na VM (cenário exato do CI + mutante sem key + e2e
completo, tudo verde):

4. **O patch de auth definia `auth_curl` mas não trocava os call sites** —
   `initialize`/`profile` seguiam com `curl` puro e levavam 401. A lacuna era
   MINHA cobertura: na VM eu validei o `smoke-e2e.sh` ao vivo, mas nunca
   executei o init script sob auth. O rc pegou o que a bancada não cobriu.
5. **`python` vs `python3`** nos heredocs host-side: os runners do GitHub têm
   `python`, o Ubuntu 24.04 da VM não — trocado para `python3` (os
   `docker exec ... python` ficam: rodam dentro do container).
6. **Expectativa de taxonomia congelada na v0.7.0**: o template mudou na
   v0.39.0 (`364d4cc`, 14→10 tipos — `fato_relevante` saiu,
   `apresentacao/planilha/email` viraram faceta `doc_kind`) e o script ainda
   exigia o conjunto antigo. Latente porque só `make docker-update` roda este
   smoke (o `docker-up` não). Atualizado para os 10 vigentes.

A tag `v1.0.0-rc.1` fica no histórico como o ensaio que reprovou (sem release
e sem tag de imagem); o ensaio seguinte é `v1.0.0-rc.2`.

## Ensaio rc.2 — verde de ponta a ponta + validação externa (2026-07-30)

Run 30596928207: build 2 archs → smoke 2 archs pela imagem publicada →
publish completo. Release `v1.0.0-rc.2` como prerelease com bundle +
SHA256SUMS. Validação externa:

| Prova | Resultado |
|---|---|
| Pull anônimo real (VM sem login no GHCR) | ✔ 18,7s |
| Multi-arch no index | ✔ linux/arm64 + linux/amd64 |
| Download comprimido da app | 274,7 MiB (288 MB) arm64 / 279,8 MiB (293 MB) amd64 — estimativa ~275 MB do roadmap cravou |
| Proveniência | ✔ `gh attestation verify oci://…:1.0.0-rc.2` exit 0 |
| Bundle | ✔ sha256 confere; compose + `.env.example` já pinado `ATLASFILE_VERSION=1.0.0-rc.2` + 2 configs |

**Correção de fato ao plano**: "o 1º push cria o pacote GHCR privado" (vinha
da documentação, via revisão) **não se confirmou** — o pacote nasceu PÚBLICO
já no rc.1 (pacote criado por `GITHUB_TOKEN` em workflow de repo público
herdou a visibilidade do repo). O passo manual de flip não existiu; o job
`smoke` mantém o login mesmo assim (custo zero e blinda contra mudança de
default do GitHub).

## Sequência restante (disparos do autor)

1. ~~Merge do PR #12~~ — feito em 2026-07-30 (`dc34e8d`); o fix do rc.1 entra
   pelo PR seguinte.
2. ~~Ensaio rc.2 + validação externa~~ — **feito em 2026-07-30** (seção acima);
   o flip manual não foi necessário (pacote nasceu público).
3. `git tag -a v1.0.0 -m "Primeira release publicada" && git push origin v1.0.0`
   → mesma validação → Release final. O rc.1 fica como prerelease no histórico.
