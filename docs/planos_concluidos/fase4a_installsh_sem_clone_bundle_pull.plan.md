# Fase 4a — `install.sh` sem clone (bundle da release + pull)

> Executado em 2026-07-31, branch `fase4a-install-sem-clone`. **Sem bump de
> versão** (decisão dele, na execução): mudança de instalador não altera a
> versão do App, que segue 1.0.0 — o `install.sh` chega pelo raw/main no
> merge, sem precisar de release nova.
> Plano aprovado após revisão adversarial local com 3 revisores paralelos
> (correção factual, cobertura/lacunas, segurança/UX/processo), que derrubaram
> 3 bloqueantes do rascunho v1 — a correção cross-branch prometida pela Fase 3
> tinha sido abandonada em silêncio, o despacho legado→fonte estava sem guarda
> de bancada, e o resolutor de versão não validava o valor resolvido — e um
> fato falso (o `install.ps1` NÃO encaminha `--branch` sempre: `$Branch` nasce
> vazio em `install.ps1:46` e só viaja quando o usuário o passa).

## O que mudou

O caminho padrão do `install.sh` deixou de clonar e compilar: resolve a última
release estável (ou a pinada por `--version X.Y.Z`), baixa o bundle (~10 KB)
com verificação de SHA256 ANTES de abrir o tar, valida o conteúdo (exatamente
os 4 arquivos, nenhum symlink) antes de tocar o dir e sobe a stack por
`docker compose pull` da imagem publicada. O clone vive atrás de
`--from-source` e do auto-despacho por `.git` — a instância de quem instalou
por clone permanece no caminho de clone no re-run, com aviso.

## Decisões (fechadas na aprovação do plano)

| Decisão | Escolha | Por quê |
|---|---|---|
| Resolução de versão | API `releases/latest` + `--version X.Y.Z`; validação estrita de shape no resolvido E no digitado | O valor flui para URL, `sed` do `set_env` (quebra com `\|`) e ref de imagem; a validação é a defesa real contra JSON de rate-limit e campo errado |
| Integridade | SHA256SUMS baixado e conferido antes do tar; conteúdo validado antes do move | Modelo de ameaça declarado: mitiga download truncado/asset trocado, NÃO comprometimento do host (mesma raiz TLS do próprio `curl \| bash`) |
| Update dos arquivos do bundle | hash gravado no manifesto (`bundle_sha`) prova "nosso e não editado"; divergiu → backup datado + aviso nomeando | Paridade com o contrato do clone (recusa e nomeia); sem baseline de hash, todo update clobberaria edição do usuário em silêncio |
| Manifesto | `repo_clone=bundle` (dir criado por nós no caminho novo); chaves novas `bundle_files`, `bundle_sha`, `bundle_backups` (pares get no uninstall — check #13) | Dir preexistente segue `preexisting`: o uninstall nunca remove pasta que não prova ter criado; `created`/`preexisting` não colapsam |
| Uninstall bundle | Mesmas guardas do `created`: `install_dir` bate + arquivo estranho (via manifesto, não git) preserva nomeando | A garantia da v0.54.0 vale igual no mundo novo |
| Legado com `.git` | Auto-fonte no re-run, com `info`; migração clone→bundle é manual e documentada | Zero surpresa para a instância real em `~/AtlasFile` |
| Downgrade | Detectado (`af_version_lt`); confirmação interativa obrigatória, `--yes` não pula | Índice OpenSearch escrito por versão mais nova pode ser incompatível; mesma família da decisão do volume |
| `--repo-url`/`--branch` | Continuam públicos; no bundle path com valor não-default: warn + ignore (precedente Ollama) | `install.ps1` os encaminha quando usados; remover quebraria o Windows antes da 4b |
| Windows (D9) | O `install.ps1` (congelado até a 4b) passa a delegar no bundle path no dia do merge; smoke real na VM Parallels como critério de aceite | Declarado em vez de descoberto: raw/main muda o comportamento de TODA instalação Windows nova |
| Fresh-install guard | "sem `.git` E sem manifesto" (era só `.git`) | Sem isso o re-run bundle com volume existente era barrado como instância estrangeira |

## Arquivos alterados

- **`install.sh`** (2809 → ~2980 linhas): funções novas `af_validate_version`,
  `af_version_lt`, `af_resolve_version`, `af_file_sha`, `af_sha256_check`,
  `af_source_mode`, `af_fresh_install_dir`, `af_downgrade_gate`,
  `af_fetch_bundle`, `af_stack_up`, `un_bundle_own_list`, `un_bundle_strange`;
  flags `--version`/`--from-source`; git condicionado ao caminho fonte; `tar`
  como pré-requisito duro; despacho na fase 2; pin de versão por caminho na
  fase 3; fase 4 build-vs-pull; braços `bundle` em `un_collect`,
  `un_build_plan` e `run_doctor`; refspec explícita no `af_update_clone`
  (cross-branch, achado 1 da Fase 3); dry-run/doctor/mensagens.
- **`tests/installer/run.sh`** (253 → 291 PASS): fixture de release LOCAL
  (tar.gz + SHA256SUMS reais + stub de curl URL→arquivo, tar REAL de
  propósito), 35 casos novos cobrindo validação, resolução, fetch (integridade,
  tar hostil, symlink, 404), contrato de update sem clobber, despacho,
  downgrade, stack_up, uninstall bundle, GHCR-única, doctor, flags e
  cross-branch. Wrapper de tar que registra a ordem (verificar-antes-de-extrair
  é provado, não presumido).
- **`tests/installer/check_consistency.py`**: sem mudança — e ele trabalhou:
  reprovou o `case` aninhado no arm `--version` (e depois a PALAVRA de
  fechamento citada num comentário), que cortavam a fatia do parser analisada
  pelo `check_flags`.
- **Docs**: `README.md`, `README.pt-BR.md`, `INSTALL.md` (bundle+pull, ~290 MB
  medido, sem promessa de segundos), `docs/ROADMAP.md`,
  `docs/roadmap/distribuicao_build_imagens_ghcr.md` (marcação de executada +
  correções de fato + endurecimentos futuros anotados).
- **Versão**: SEM bump (o plano previa 1.1.0; corrigido na execução por
  decisão dele — instalador não bumpa o app). `CHANGELOG.md` ganhou seção
  própria de instalador, fora da numeração do app.

## Correções de fato ao roadmap (verificadas no código)

1. Números de linha defasados (arquivo cresceu para 2809 antes da fase).
2. NÃO existe prompt do Xcode CLT a aposentar (zero hits).
3. O braço GHCR do `un_collect` já existia desde a v1.0.0; o que faltava era a
   guarda do caso "GHCR é a única imagem" — agora existe e é provada por
   mutante que a bancada antiga deixava passar.
4. O código git NÃO foi deletado (o roadmap dizia "aposenta"): o uninstall de
   instalações clonadas precisa dele para sempre; o que se aposentou foi o uso
   no caminho PADRÃO.
5. Achado 3 da Fase 3 falava em `repo_clone=updated`; o código vigente só
   grava `created|preexisting` — a sub-remoção conservadora pós-update foi
   MANTIDA por desenho no caminho clone (clone com história do usuário é
   irrecuperável) e não existe no mundo bundle (dir `bundle` é removível).

## Mutantes (guarda se prova com mutante)

Runner: `mutantes_fase4a.py` (scratchpad da sessão) — aplica cada mutação numa
cópia, roda a bancada INTEIRA e exige que o caso-alvo reprove; restaura sempre.
**10/10 mortos em 2026-07-31** (+M11 do achado do E2E, morto na sequência = 11), cada um reprovando exatamente no alvo:

| Mutante | Alvo que reprovou |
|---|---|
| M1' braço GHCR condicionado a existir imagem legada | "uninstall enxerga a imagem GHCR quando ela é a ÚNICA" (a bancada ANTIGA deixava este mutante passar — é o que prova que o caso novo agrega guarda) |
| M2 pular a verificação de SHA | "SHA adulterado reprova SEM extrair" (4 asserções) |
| M2b extrair ANTES de verificar | idem — a asserção da ORDEM (wrapper de tar que grava a chamada) |
| M3 `af_fetch_bundle` sobrescreve o `.env` | "update preserva .env e arquivo do usuário" |
| M4 pull vira build no caminho bundle | "af_stack_up no bundle faz pull e nunca build" |
| M5 despacho ignora o `.git` | "af_source_mode: .git presente vai para fonte" (protege a instância legada real) |
| M6' `af_validate_version` aceita qualquer coisa | 4 asserções de validação + o caso de rate-limit |
| M7 `un_build_plan` sem o braço `bundle` | 3 casos do uninstall bundle |
| M8 refspec do cross-branch revertida | "update cross-branch passa a funcionar" |
| M9 guarda de downgrade neutralizada | "af_downgrade_gate: headless recusa; interativo respeita" |

Nota de método: durante a execução dos mutantes, um `make test` concorrente
leu o `install.sh` mutado (M6') e reprovou o `test-installer` — resultado
descartado como contaminado e a suíte re-executada com o arquivo restaurado.
Mutação em arquivo compartilhado e suíte concorrente não coexistem.

## Verificação

- **TDD de verdade**: os 34 casos novos nasceram VERMELHOS contra o
  `install.sh` da main (34 FAIL medidos, zero regressão nos 253 antigos) e
  ficaram verdes com a implementação; +1 asserção de ordem (tar wrapper) = 288.
- **`make test` completo verde** (2026-07-31, pós-mutantes, arquivo
  restaurado): backend pytest + frontend vitest + `test-installer` 288 PASS (291 com o achado do E2E) +
  `check_consistency.py` + parse do `install.ps1`. (Um primeiro `make test`
  rodou CONCORRENTE ao runner de mutantes e reprovou com o M6' aplicado —
  descartado como contaminado, ver nota na seção de mutantes.)
- **Sweep dos casos verdes**: nenhum caso full-script da bancada alcança a
  fase 2 do install (todos são --help/--doctor/--dry-run/--uninstall/
  --bootstrap-only — verificado na leitura integral), então nenhum caso verde
  mudou de semântica em silêncio; os casos de função (ensure_git,
  af_update_clone, un_*) re-rodaram verdes.
- **Telas reais inspecionadas**: `--help` (jargão interno removido) e
  `--dry-run` bundle path (release row, "would be INSTALLED from the release
  bundle", tar nos pré-requisitos).
- **`check_consistency.py` trabalhou duas vezes**: reprovou o `case` aninhado
  do arm `--version` e depois a palavra de fechamento citada em comentário —
  as duas cortavam a fatia do parser do `check_flags`.
- **E2E na VM lima `atlas-e2e`** (Ubuntu 24.04 ARM64, 4 vCPU/8 GiB,
  2026-07-31, TODO o roteiro executado e verde; critério de espera: "Install
  finished" no log DA execução):
  1. **Estado-zero**: uninstall NOVO sobre a instalação legada clonada da main
     — 6s; a guarda de sujeira pegou um caso real (`scripts/smoke-project-init.sh`
     alterado pelo E2E da fase 3 → pasta preservada NOMEANDO o arquivo);
     `--force` na sequência revelou o **achado 1 do E2E** (abaixo).
  2. **Install bundle REAL contra a release v1.0.0 pública**: 1m07s total —
     resolução via API real, bundle baixado e verificado (checksum ok), pull
     da imagem 17s (rc.2 tinha medido 18,7s — consistente), health 4s.
     Manifesto: `repo_clone=bundle`, `bundle_files` e `bundle_sha` com os 4
     hashes; `.env` pinado 1.0.0; sem `.git` no dir.
  3. **Fluxo real**: smoke-project-init + smoke-e2e da fase 3 contra a stack
     instalada pelo bundle — OCR do tesseract DA IMAGEM, triagem aprovada,
     busca com highlight, `/mcp` recusando sem key e fechando o loop com key.
  4. **Re-run idempotente** (mesma versão): 33s, bundle re-verificado, `.env`
     preservado, zero backups de bundle, "images already on this machine are
     reused", pull 2s.
  5. **Ciclo `--keep-data`**: volume preservado com senha registrada →
     reinstalação reivindica o volume, restaura a senha, stack healthy em 54s
     e **o índice sobreviveu** (a sentinela do OCR do passo 3 respondeu à
     busca pós-ciclo).
  6. **`--from-source` real**: clone da main via `file://` (repo do host
     montado), build local 11s, 1m02s total; **re-run cross-branch**
     main → `fase4a-install-sem-clone` atualizou o clone raso em 1s (o cenário
     que morria em "unknown revision" antes da refspec).
  7. **Erros reais de pull capturados**: DNS quebrado emite
     `dial tcp: lookup … no such host` (casa com os padrões vigentes do
     `af_falha_de_rede` — classificado como rede ✔); tag inexistente emite
     `not found` (corretamente NÃO classificado como rede). Medido → nenhuma
     edição de padrão necessária.
  8. **Purge final**: dir removido, volume apagado, `atlasfile-local:dev`
     removida, só `opensearchproject/*` preservada (por desenho) — VM limpa.
- **Smoke Windows (D9)**: via seam `ATLASFILE_SH_URL` (`install.ps1:297`)
  apontando para o raw da branch — <!-- PREENCHER após o smoke -->

## Achados do E2E (fatos novos)

1. **`un_compose_down` morria com `.env` removido — em três tempos.** Um
   uninstall parcial (pasta suja preservada) remove o `.env`; a re-execução
   com `--force` morria na interpolação de `OPENSEARCH_INITIAL_ADMIN_PASSWORD`
   (`:?`) com ZERO containers no ar — a barreira parava por interpolação, não
   por stack viva (a v1.0.0 só supria `ATLASFILE_VERSION`). A 1ª correção
   (export) passou na bancada e MORREU na VM: o docker roda atrás do shim de
   sudo e o sudo limpa o ambiente. A 2ª (`--env-file`, o arquivo viaja com o
   comando) passou — e o 3º tempo pegou `PROJECTS_HOST_ROOT`, que não é `:?`
   mas quebra o down com spec `:/projects` inválida (placeholder de CAMINHO,
   `/tmp` — "0.0.0" viraria volume nomeado inexistente). Guarda de bancada com
   stub que LÊ o env-file recebido + mutante M11 (reverter à forma v1.0.0
   reprova exato); asserções negativas `compose down` da bancada atualizadas
   para `compose.*down` (com o formato novo elas cegariam).
2. **A guarda de sujeira do clone provou valor em produção de teste**: pegou
   um arquivo modificado real e o nomeou na tela — o contrato "preserva e diz
   o quê" funcionando fora da bancada.

## Medições (VM lima, ARM64)

| O quê | Medido |
|---|---|
| Uninstall da instalação legada (novo installer) | 6s |
| Install bundle completo (resolve+download+verify+pull+up+health) | 1m07s |
| Pull da imagem do app (283 MB comprimida, arm64) | 17s |
| Re-run idempotente | 33s |
| Ciclo keep-data (uninstall+reinstall com volume reusado) | 54s (reinstall) |
| Install --from-source (clone file:// + build local) | 1m02s (build 11s) |
| Re-run cross-branch (main → branch da fase) | 37s (update 1s, build 1s) |
| Smoke E2E completo (OCR+triagem+busca+MCP) | 4,9s |

## Pendências que ficam

- Fase 4b (Windows) — bloqueada pelo item 4 do roadmap (bancada Windows sob
  `prlctl`); o help do `install.ps1` promete clone até lá (gap declarado).
- Endurecimentos anotados no roadmap: digest pinning/attestation no
  instalador; checksum do próprio `install.sh`.
- Sanitização de filename no upload (`main.py`, path traversal pré-existente)
  — pendência aguardando decisão, fora deste escopo.
- Site (`atlasfile-website`): drift herdado ("five Docker services"/58s)
  continua na fila pós-4a, junto do texto novo de instalação.
