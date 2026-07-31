# Planos Concluídos — AtlasFile

Registro dos planos de implementação executados, organizados por versão.

---

## 1.0.0 — instalador (Fase 4b, 2026-07-31, sem bump de versão do app)

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [fase4b_installps1_release_flags_painel](fase4b_installps1_release_flags_painel.plan.md) | Fase 4b do plano de distribuição — **o `install.ps1` conta a história da release**: nascem `-Version` (com validação cedo no ps1 — medido que `-Version banana` via `-File` rodava a instalação inteira por encaixe posicional), `-FromSource` (correção de regressão da 4a: o caminho contribuidor estava inacessível do Windows), `-RepoUrl` (só com `-FromSource`; fecha o item 2 do ROADMAP) e `-NoOpen` (com seam `Open-AfBrowser` — anúncio observável em vez de sinal que só existe na falha). Painel ensina `logs`/`stop` com o dono real (`wsl -u root -e` quando root — item 3), ajuda sem promessa de clone incondicional, fase 3 anuncia pull. Guarda do header do `check_flags` ressuscitada (extração devolvia vazio). Bancada 206→228 no canal prlctl/SYSTEM com baseline por NOME, vermelho natural registrado (212/16), 7 mutantes na VM + 1 local matando exatamente as guardas-alvo. `-Registry` e `-NoOllama` deliberadamente não nascem. Errata da 4a registrada (ps1 nunca encaminhou `--repo-url`). Plano revisado ANTES por 3 revisores adversariais locais (~40 achados; guarda morta do header, falso-verde do browser e a reclassificação da regressão vieram deles) |

---

## 1.0.0 — instalador (Fase 4a, 2026-07-31, sem bump de versão do app)

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [fase4a_installsh_sem_clone_bundle_pull](fase4a_installsh_sem_clone_bundle_pull.plan.md) | Fase 4a do plano de distribuição — **instalar sem clone**: o caminho padrão do `install.sh` resolve a release (API + `--version X.Y.Z` com validação estrita), baixa o bundle com SHA256 verificado ANTES do tar e conteúdo validado antes do move (tar hostil/symlink recusados), e sobe por `docker compose pull`; git sai dos pré-requisitos (fica no `--from-source` e no auto-despacho por `.git` — instância clonada nunca migra sozinha), `tar` entra. Update sem clobber (hash no manifesto prova "nosso"; editado ganha backup nomeado), downgrade exige confirmação, uninstall ganha o mundo `repo_clone=bundle` com as mesmas guardas do clone (install_dir + arquivo estranho via manifesto), doctor idem. Correção cross-branch do `af_update_clone` (achado 1 da Fase 3, refspec explícita). Bancada 253→291 PASS com release LOCAL real; 11 mutantes provando as guardas novas; plano revisado ANTES por 3 revisores adversariais locais (3 bloqueantes derrubados, 1 fato falso corrigido) |

---

## 1.0.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [fase3_publicar_provar_imagem_v100](fase3_publicar_provar_imagem_v100.plan.md) | Fase 3 do plano de distribuição — **a primeira imagem publicada e provada**: `ghcr.io/aleonnet/atlasfile` multi-arch (amd64+arm64 em runners nativos), `release.yml` por tag com o invariante "tags só depois do smoke E2E nas 2 archs contra os digests já publicados" (smoke vermelho deixa só manifests sem tag), proveniência atestada, bundle ~10 KB no Release, versão consultável (`/api/setup/status.version == tag`), compose vira consumo (digests de terceiros pinados, `ATLASFILE_VERSION` sem default) com build local no overlay `atlasfile-local:dev`. Plano revisado ANTES por 3 revisores adversariais locais: derrubaram a premissa "triagem indexa" (0,7598 < 0,85 provado no classificador real → o smoke aprova a triagem), e anteciparam da 4a o mínimo do `install.sh` (var no `.env`, overlay, uninstall com fallback + remoção explícita de imagens nomeadas — `--rmi local` não remove `image:` nomeado). Mutantes: check_pins (digest), bancada do un_collect (2 FAILs exatos → 223 PASS), sentinela/key/versão no smoke. Primeira tag `v1.0.0` precedida do ensaio `v1.0.0-rc.1` (pacote GHCR nasce privado; flip manual antes da final) |

---

## 0.57.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [fase2_um_app_um_container_v0570](fase2_um_app_um_container_v0570.plan.md) | Fase 2 do plano de distribuição — **um app, um container** (BREAKING: MCP `:8001/mcp`→`:8000/mcp` com a mesma API key; UI `:5173`→`:8000` como bundle de produção). Consolida api+mcp+web num uvicorn (Route `/mcp` por request — mount duplicaria o path e responderia 307; lifespan recria o session manager single-use; `MCPAuthMiddleware` porque Route não herda o require_auth global), primeiros healthchecks do compose, api_keys vira bind mount, Dashboards opt-in por profile. Das 7 armadilhas, 3 achadas fora do roadmap — e a mais grave no E2E: **o SDK executa tool síncrona inline no event loop** e cada tool call deadlockava o processo inteiro por 60s (medido; invisível na topologia antiga de 2 processos) → wrapper `@tool()` com to_thread, 60.100ms→59ms. 12 mutantes mortos, migração 0.56.6→0.57.0 provada na VM lima com `.env` intocado e volume vivo (47.7s, órfãos removidos), fluxo completo na UI real via Playwright e carga de 50 tool calls concorrentes em 1.2s |

---

## 0.56.6

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [fase1_reprodutibilidade_pins_lock_v0566](fase1_reprodutibilidade_pins_lock_v0566.plan.md) | Fase 1 do plano de distribuição: o artefato instalado passa a ser resolvível ao testado. 9 pisos `>=` viram `==`, lock de 99 pacotes gerado **dentro de `python:3.12-slim`** (o venv local é 3.11 — armadilha achada na recalibração), dev instala o MESMO resolve do produto, `lucide-react` sai de `"latest"`, `npm ci` no Dockerfile e `.dockerignore` novo no frontend. Guarda `check_pins.sh` (CI job `pins` + local) provada com dois mutantes antes de valer, e o teste que faltava: import real do `mcp_client` reprova com `mcp==1.9.3` em container 3.12 e passa com o lock. Inclui a recalibração completa do plano de distribuição (v0.56.2 → v0.56.5, ~90 afirmações revalidadas: a narrativa do "piso falso" estava superdimensionada — pip resolve o topo, não o piso) |

---

## 0.56.5

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [e2e_windows_real_e_modos_readonly_v0565](e2e_windows_real_e_modos_readonly_v0565.plan.md) | Primeiro E2E do `install.ps1` **num Windows 11 real** (instalação do zero em 15m56s, reinstalação idempotente em 26s, `-Uninstall -DryRun` e `-KeepData`) — achou 4 defeitos que nenhum outro canal via: `wsl --list` também dispara o instalador do WSL (curto-circuito no `Test-WslUsable`), o reset .bat com o mesmo defeito recém-corrigido, o winget que sai 0 sem achar o pacote ("código de saída não é sinal, a mensagem é"), e o plano de uninstall ignorando `-KeepData` já decidido. De quebra: documentos deixam de nascer dentro do OneDrive e as estimativas de tempo foram recalibradas (11 dos 15 min eram o download do Docker Desktop, não o build). Cobre também a v0.56.4 (PR #8: `-DryRun`/`-Doctor` disparavam o instalador do WSL). _Entrada adicionada retroativamente na v0.56.6 — o plano existia sem constar deste índice_ |

---

## 0.56.3

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [tres_correcoes_naming_reconcile_dryrun_v0563](tres_correcoes_naming_reconcile_dryrun_v0563.plan.md) | Três defeitos independentes, todos reproduzidos antes de corrigir. **O nome do documento perdia o identificador**: arquivo cujo nome de usuário já terminava em `__vNN` e continha `__` era confundido com canônico, e `DocuSign_Project_Neptune___SPA__Anexos_v_A__v01__v01.pdf` virava `Anexos_v_A__v01.pdf` — o guarda validava o candidato de SAÍDA em vez de provar a ENTRADA. **O reconcile nunca rodava na subida**: o laço faz `wait(interval)` antes do corpo, então uma instalação nova sobre pasta com documentos mostrava zero por 10 minutos. **O `--dry-run` se contradizia** e pior do que o registrado — duas fontes de verdade faziam a tela dizer `✘ docker not found` e `✔ none — everything needed is already here` na mesma imagem. E, já que o CI verde era requisito, **a bancada que travava seis horas** no job macOS: o rastreio novo (`AF_BENCH_TRACE`) provou o ponto de parada na primeira execução — o gerador de senha lia `/dev/urandom` para sempre e dependia de um `SIGPIPE` que naquele runner não chegava. Bancadas 725→731 e 211→218, cada guarda provada contra mutante — e a do gerador nasceu inútil duas vezes antes de valer |

---

## 0.56.2

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [uninstall_linux_stack_real_v0562](uninstall_linux_stack_real_v0562.plan.md) | Primeiro E2E do `install.sh` **em Linux com stack real no ar** (VM Ubuntu limpa, sem Docker) — o buraco que v0.54.0→v0.56.1 nunca cobriram, porque todas validaram em macOS ou Windows. Achou o desinstalador **apagando os meios de reverter e falhando em reverter**: plano cego pelo `docker info` sem sudo (0 containers com 5 no ar, volume sumido das duas seções, exigência headless evaporada) e `un_execute` seguindo depois de o `compose down` falhar. Shim sem efeito colateral, barreira na execução, e os cinco caminhos do uninstall validados com stack real |

---

## 0.56.1

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [paridade_instaladores_auditoria_v0561](paridade_instaladores_auditoria_v0561.plan.md) | Auditoria dos dois instaladores lado a lado, com os 4.663 linhas de fonte lidas e os caminhos read-only executados. **A guarda estava verde e 26 divergências viviam sob ela**: ela compara tabelas e existência de primitivas, e o que divergia eram os algoritmos e o uso delas. Um `-DryRun` que prometia instalar Ollama, uma desinstalação que abandonava o Docker Desktop, o trilho furado dos dois lados, e quatro divergências no banner — cauda do cometa faiscada, luas congeladas, ignição adiantada, brilho com outra fórmula. Guarda nova de **paridade de quadros** (renderiza os 26 dos dois e compara caractere a caractere), que nasceu cega e só passou a valer depois de âncora e piso de sanidade |

---

## 0.56.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [installer_validacao_maquina_real_macos_windows_v0560](installer_validacao_maquina_real_macos_windows_v0560.plan.md) | Sete rodadas de instalação e desinstalação num macOS e num Windows 11 **reais** — a única prova que o CI não dá. Vinte e um defeitos que a bancada não via: `winget` instalando o Docker com interface, integração WSL que não subia, clone divergente matando a instalação, log acumulado entre execuções mostrando evidência de *outra* execução, documentos nascendo dentro da distro, e a tela do lado Linux degradada em silêncio por falta de `TERM`/`COLORTERM`. Bancadas 116→196 e 73→~200, toda guarda provada contra cópia mutada |

---

## 0.55.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [installer_orquestracao_dois_lados_e_ux_unificada_v0550](installer_orquestracao_dois_lados_e_ux_unificada_v0550.plan.md) | O plano de remoção passa a cobrir os **dois** escopos da máquina Windows, com uma confirmação só; o lado Windows só age com duas provas (código de saída **e** linha-sentinela), porque cancelar antes removia o Docker assim mesmo. `.gitignore` quebrado impedia a remoção da pasta em toda instalação feita pelo one-liner. UX unificada nos dois instaladores no padrão do `mac_env_install.sh` (calha, régua, barra, placar), banner com a mesma arte, e `--doctor`/`--dry-run`/`--verbose`. Bancadas 79→119 e 73→100+, com guarda de paridade de arte e de UI |

---

## 0.54.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [installer_uninstall_e_banner_orbital_v0540](installer_uninstall_e_banner_orbital_v0540.plan.md) | `install.sh --uninstall` reverte só o que a instalação criou, guiado por manifesto em dois escopos (host e instalação), com plano em texto antes de agir e o volume de dados sem default; banner orbital animado (ignição, duas luas, cometa que acende o wordmark) substituindo a carinha; `--help` de verdade nos dois instaladores. Seis bugs preexistentes corrigidos com evidência medida, três deles achados numa VM Windows limpa |

---

## 0.52.0 – 0.53.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [causa_real_sem_texto_e_toggle_idioma_v0520](causa_real_sem_texto_e_toggle_idioma_v0520.plan.md) | A triagem diz POR QUE não houve texto (7 causas derivadas do `ExtractionResult`, com precedência do OCR indisponível sobre imagem embutida) no lugar do genérico "(OCR vazio)", que às vezes era falso; toggle de idioma na sidebar no mesmo padrão do tema (pedido do usuário) |
| 2 | [journal_durabilidade_chats_custos_v0530](journal_durabilidade_chats_custos_v0530.plan.md) | Chats e eventos de custo deixam de viver só no índice: journal append-only em `_ATLASFILE/journal/` (NDJSON por mês) + snapshot atômico por sessão, restauração idempotente no reconcile que nunca sobrescreve índice vivo; E2E do incidente: índice apagado → sessão restaurada |

---

## 0.51.0 – 0.51.1

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [sso_local_observabilidade_v0510](sso_local_observabilidade_v0510.plan.md) | Link "Observabilidade" abre o Dashboards já autenticado: a API loga pela rede interna e devolve o cookie de sessão no redirect (cookies ignoram porta — provado no Chrome real); a senha nunca chega ao browser/URL/histórico; guarda explícita quando Dashboards está em outro domínio e degradação para a tela de login em qualquer falha; **adendo v0.51.1**: repassa todos os cookies (sessão dividida/nome customizado) e abre direto no dashboard de operação com checagem prévia do saved object |

---

## 0.50.5

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [reconcile_restaura_fatos_dashboard_v0505](reconcile_restaura_fatos_dashboard_v0505.plan.md) | Dashboard cego após rebuild: o reconcile zerava `ingested_at`/`processed_at` (time field de TODO painel temporal) e não repunha `classifier_mode`/`entities`; `embedding_status` nunca era regravado no caminho `up_to_date`. Fatos do evento restaurados do `ingest_history` + metas do `resolved` (+ prefixo do nome canônico para data), com backfill no incremental e guarda anti-loop; medido 0→108/108 datas, 0→104/108 modo |

---

## 0.50.3

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [cache_feature_text_sugestor_v0503](cache_feature_text_sugestor_v0503.plan.md) | Sugestões de alias "não somem após a ação" = refetch pendurado em GET de 61,8s (re-extração de TODOS os resolvidos a cada request; PDF escaneado de 46 págs re-OCRizado toda vez); cache persistente do excerpt por sha256 em `_PROFILE/feature_text_cache/` → 35ms (1.780×); nome recomposto por chamada (sem contaminação); E2E: linha some em ~1s |

---

## 0.50.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [auto_ingest_widget_unico_sem_botoes_v0500](auto_ingest_widget_unico_sem_botoes_v0500.plan.md) | Auto-ingest de verdade (watcher.py era código morto; escuta ampla pois VirtioFS entrega criação como `modified` — medido; quiescência 4s + estabilidade 5s + sweep 60s + anti-loop de falha); widget global vira superfície única de processamento (aparece sozinho em runs automáticos); botões "Processar INBOX" e "Reconciliar INDEX" eliminados — reconcile automático só anuncia quando corrige algo, escape hatch discreto "Reconciliar agora" preserva o escopo da v0.44.0 |

---

## 0.49.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [ocr_inline_pptx_calibrado_v0490](ocr_inline_pptx_calibrado_v0490.plan.md) | OCR de imagens no PPTX roda SEMPRE (não só envelope): shape PICTURE → tesseract com âncora `slide:N:image:M`; logos do master fora de graça; corte de ruído de 85 chars calibrado por medição em 12 decks reais (logo=0–14, diagrama=513+); WMF pulado; validado no deck real `doc_0075` (2 diagramas de topologia viraram chunks pesquisáveis); docx/xlsx seguem só-envelope por decisão de custo-benefício |

---

## 0.48.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [ocr_imagens_embutidas_office_v0480](ocr_imagens_embutidas_office_v0480.plan.md) | OCR de imagens embutidas em docx/pptx/xlsx "envelope" (documento sem texto próprio → tesseract em `word/media/*`, `ppt/media/*`, `xl/media/*`; cap 10 imagens em metadata; mesmo motor do PDF escaneado); validado no docx real das atas do RCA (1.698 chars extraídos); legados OLE2 e mensagem com causa real registrados no ROADMAP |

---

## 0.47.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [llm_type_aura_medidor_v0470](llm_type_aura_medidor_v0470.plan.md) | document_type do LLM governado (sentinela 'outro' banida do prompt; aplica só se existir na taxonomia; degradação para triagem em vez de FALHA); aura de processamento com orb blackhole no lugar do halo arco-íris; medidor de contexto honesto (janela real do Ollama via /api/show — gemma4 = 262k medido; recálculo na troca de modelo; tooltip com heurística) |

---

## 0.46.1

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [incidente_429_disco_heap_dedup_vivo_v0461](incidente_429_disco_heap_dedup_vivo_v0461.plan.md) | Post-mortem factual do 429 (disco flood-stage dominante + heap 512m saturado): dedup só contra documento vivo (rejected nunca; pending/resolved com arquivo existente), retry diferenciado no indexador (breaker sim, cluster_block vira erro legível), heap 1g parametrizável, monitor de disco no alerting do ROADMAP |

---

## 0.46.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [seletores_agrupados_por_provedor_v0460](seletores_agrupados_por_provedor_v0460.plan.md) | Combo rápido de modelos com curadoria (benchmark ChatGPT/Cursor): atual + recentes + customs em `<optgroup>` por provedor; "Todos os modelos…" abre o settings com a busca dos 68+; recentes em localStorage (cap 5); cascata provedor→modelo rejeitada com critério; "Estrutura de Layout" do perfil inicia fechada |

---

## 0.45.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [ciclo1_confianca_acesso_naming_v0450](ciclo1_confianca_acesso_naming_v0450.plan.md) | Estado vivo do modelo custom nos seletores (selo honesto com re-validação; storage com data e migração de legado), link "Observabilidade" no Painel (URL derivada do host + `DASHBOARDS_PUBLIC_URL` opcional), reconcile varre órfão físico do pending (guarda de 600s, rejected com sidecar), e reingestão de nome canônico desembrulha o original (fim do `__v01__v01`; linhagem de versão restaurada) — smokes reais na stack dev, incluindo o Ollama caindo de verdade durante o teste do badge |

---

## 0.44.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [tier1_confianca_aprendizado_reconcile_cookie_v0440](tier1_confianca_aprendizado_reconcile_cookie_v0440.plan.md) | Tier 1 do roadmap por ganho de UX: aliases com escopo por projeto (default) ou global na aprovação; scoring do bootstrap corrigido pelo diagnóstico real do kit marítimo (overlap tipo↔domínio só pontua com hit de conteúdo — √N do roadmap refutado pelo novo `trace_classification.py`; benchmark 62 docs idêntico antes/depois); botão do reconcile explicita o escopo e a limpeza de órfãos; `DASHBOARDS_COOKIE_PASSWORD` por instalação (cookie velho vira login limpo em vez de 500) |

---

## 0.43.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [installer_bootstrap_prereqs_v0430](installer_bootstrap_prereqs_v0430.plan.md) | Instalador bootstrapa os próprios pré-requisitos: detecta Docker/git ausentes e OFERECE instalar (Homebrew/cask no macOS com espera do daemon; get.docker.com + apt/dnf no Linux; winget/WSL no Windows); política `--yes` conservadora + `--install-deps`; Ollama opt-in (`--with-ollama` + modelo, falha nunca derruba); idempotente com ✔/versão e hints de upgrade; en-US como idioma dos instaladores; 17 testes com stubs + smoke real em ubuntu:24.04; step 0 do site removido |

---

## 0.41.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [dashboards_observabilidade_v0410](dashboards_observabilidade_v0410.plan.md) | Dashboard "AtlasFile — Operação" (18 painéis / 3 index patterns: acervo, fluxo × decisão, confiança, saúde de extração/embeddings, custo LLM, tag cloud de tópicos) gerado deterministicamente e **auto-importado no boot** da API (thread com retry, overwrite idempotente, nunca bloqueia startup); validado ao vivo com 22/22 objetos e screenshot autenticado |

---

## 0.40.0 – 0.40.2

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [projects_root_self_healing_v0400](projects_root_self_healing_v0400.plan.md) | Self-healing da raiz de projetos: a deleção da pasta host manifesta em DOIS modos (mount fantasma `emptied` via marcador `.atlasfile_root` + evidência no índice; mount quebrado `unavailable` com setup/status que nunca mais 503) — modal de recuperação em 1 clique (`POST /api/system/restart` → SIGTERM → `restart: unless-stopped` religa → Docker recria a pasta, validado com probes reais → reconcile global limpa órfãos → onboarding); guard anti-limbo 503 `PROJECTS_ROOT_EMPTIED`; acabamentos v0.40.2: 409 benigno da triagem com mensagem honesta, ModalActions `flex-wrap`, default de modelo custo-consciente `openai/gpt-5.1` |

---

## 0.39.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [taxonomy_essential_types_v0390](taxonomy_essential_types_v0390.plan.md) | Taxonomia essencial: document_types 14→10 (formatos apresentacao/planilha/email viram faceta doc_kind; fato_relevante sai do default) — gênero volta a competir (plano.pptx → plano); emendas de qualidade guiadas por 12 arquivos reais: `head_chars` nas regras de cabeçalho (menção profunda não é título) e teto de alias 0.84 (frequência nunca auto-roteia); piso com régua "zero auto-route de tipo errado" |

---

## 0.38.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [projects_root_resilience_v0380](projects_root_resilience_v0380.plan.md) | Resiliência à perda da raiz de projetos: sonda de saúde (`projects_root_health`) une três fixes — 503 `PROJECTS_ROOT_UNAVAILABLE` + banner global com instrução (fim do "NetworkError" mudo), limpeza de órfãos do índice destravada (guard distinguindo raiz saudável-vazia de raiz inacessível) e templates builtin imunes a OSError do diretório user; wizard não abre com mount quebrado |

---

## 0.37.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [bootstrap_alias_suggester_v0370](bootstrap_alias_suggester_v0370.plan.md) | Sugeridor de aliases do bootstrap: minera n-gramas discriminativos das correções da triagem (par sugerido→final do triage_resolved) e propõe aliases com evidência para aprovação humana na nova seção do Classificador; append governado `add_taxonomy_aliases` (template+profiles), dispensas persistidas no profile; corte contrastivo (suporte ≥2, precisão ≥0.8) validado em dados reais; candidatos compatíveis com o matching do bootstrap por construção |

---

## 0.36.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [llm_providers_responses_v0360](llm_providers_responses_v0360.plan.md) | Correção do bug 400 de modelos OpenAI pós-gpt-5.2 (tools+reasoning agora via Responses API, roteado por capacidade de catálogo `openai_api` com inferência no refresh LiteLLM); registro central de providers com Moonshot (Kimi) e Ollama local via base_url OpenAI-compatible (backend `llm_providers.py` + frontend `lib/providers.ts`); validação automática de chaves no modal Assistant Settings (debounce 700ms, 5 estados incl. unreachable); modelos custom validados no seletor do chat; erro dedicado `LLM_MODEL_NEEDS_RESPONSES_API`; +30 testes novos incl. `/api/models/validate` que não tinha nenhum |

---

## 0.33.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [frontend_sota_tanstack_query_i18n_ptbr_enus_v0330](frontend_sota_tanstack_query_i18n_ptbr_enus_v0330.plan.md) | Consolidação SOTA do frontend em 6 fases: TanStack Query v5 como camada única de server-state (bus de eventos aposentado, SSE→cache via ponte única, App slim); i18n completo PT-BR/EN-US (i18next, 12 namespaces, ~1.000 chaves/idioma, paridade testada, detecção + seletor persistido + alternador no gate/wizard); códigos de erro estáveis no backend (`{code, params, message}`, 62 codes) resolvidos pela UI; formatação regional via Intl (`lib/format.ts`); Classificador promovido a tela da sidebar; severidade de status estrutural; ortografia PT do catálogo corrigida |

---

## 0.26.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [migracao_e_remocao_governada_de_taxonomia_v0260](migracao_e_remocao_governada_de_taxonomia_v0260.plan.md) | Migrar key de taxonomia (origem→destino) cobrindo os 9 lugares onde ela vive: docs movidos sem disparar o hold-out (`dataset_routing=False`), datasets reescritos por rótulo, pendências, templates+profiles com origem virando alias; dry-run com contagens; remoção pura guardada (409 com uso ativo); modal "Migrar / remover" no editor de templates |

---

## 0.23.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [catalogo_dinamico_planilhas_sql_holdout_v0230](catalogo_dinamico_planilhas_sql_holdout_v0230.plan.md) | Catálogo de modelos dinâmico (fonte LiteLLM, combobox com modelo custom validado no provedor, custos honestos com badge "não rastreado"); análise estruturada de planilhas no chat (tools MCP spreadsheet_schema/query, DuckDB SELECT-only sobre o arquivo original, remark-gfm); ciclo do classificador destravado (hold-out ~20% por SHA das decisões humanas, regra semente, warm-up, backfill estratificado, readiness na UI) |

---

## 0.22.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [ui_conflitos_e_taxonomia_governada_v0220](ui_conflitos_e_taxonomia_governada_v0220.plan.md) | Card "Conflitos de rótulo" no Painel (arbitragem em um clique com proveniência, propagação por SHA a fontes e derivados) + criação governada de taxonomia a partir de sugestão aprovada (template default + propagação a profiles; bootstrap/llm reconhecem em runtime); rehome 20/20 aplicado |

---

## 0.21.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [instalador_e_reconciliacao_rotulos_v0210](instalador_e_reconciliacao_rotulos_v0210.plan.md) | Instalador one-liner (`install.sh` + `install.ps1` via WSL2, docs, primeiro push para github.com/aleonnet/atlasfile, teste de instalação do zero com onboarding); reconciliação de rótulos por SHA256 (consenso + LLM proponente + arbitragem humana no resíduo, guardrail `label_conflicts` no ciclo); limpeza de screenshots de revisão |

---

## 0.14.0 → 0.20.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [rag_hibrido_permissoes_ui_v2](rag_hibrido_permissoes_ui_v2.plan.md) | Plano de 7 fases (uma versão minor por fase, 0.14.0–0.20.0): remoção do modo setfit; embeddings + índice vetorial separado (`atlasfile_chunk_vectors`, backfill idempotente); busca híbrida BM25+kNN com RRF manual + rerank cross-encoder ONNX e golden-set benchmark (`benchmark_retrieval.py`); auth mínima por API key com escopo de projeto; UI Foundation (Tailwind v4 CSS-first + primitivas ui/ temadas + decomposição do App.tsx em contexts/hooks); redesign 100% das telas com zero CSS legado ("instrumento de precisão vivo"); Orb WebGL (FBM + fresnel + luas keplerianas, fallback SVG integral) |

---

## Ferramental / PoCs (não versionado)

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [poc_markitdown_vs_atlasfile_extractor](poc_markitdown_vs_atlasfile_extractor.plan.md) | PoC `extractor-benchmark_mdxaf`: comparação lado-a-lado MarkItDown vanilla vs extrator do AtlasFile sobre 6 contratos (PDF/DOCX/XLSX/PPTX). Achado: AtlasFile superior em PDF nativo (fidelidade) e escaneado (OCR; MarkItDown vazio + 24 min); MarkItDown só agrega Markdown estruturado de Office |

---

## 0.13.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [upload_move_reconciliacao_v013](upload_move_reconciliacao_v013.plan.md) | Upload de arquivos via frontend (drag-and-drop + file picker), move de documentos entre bd/dt com training pool, extração PainelView do App.tsx, fix reconcile incremental (path), fix build_corpus (último SHA ganha), triage atualiza ingest_history |

---

## 0.12.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [ui_evolution_v012](ui_evolution_v012_f4e5d6c7.plan.md) | Reestruturação de navegação (Painel/Assistente/Configuração), decomposição IngestTriageCard e App.tsx, refinamentos visuais (tipografia DM Sans, motion, toast, skeletons, charts animados) |

---

## 0.11.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [usage_api_calls_e_custo_arredondamento](usage_api_calls_e_custo_arredondamento_a3b4c5d6.plan.md) | Fix formatUsd (Math.floor→Math.round), contagem de chamadas API (api_call_count) no orchestrator/sessões/treinamento, card "Chamadas API" unificado, nomenclatura consistente |
| 2 | [graficos_chat_custos_treinamento_b7c8d9e0](graficos_chat_custos_treinamento_b7c8d9e0.plan.md) | Gráfico diário com dados de todos os processos (assistente+classificação+treinamento), abas "Por tipo"/"Por processo", captura de cache tokens da OpenAI, by_day nos endpoints training e classification |

---

## 0.10.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [graficos_chat_custos_treinamento](graficos_chat_custos_treinamento.plan.md) | Gráficos inline no chat (Recharts + matplotlib/Telegram). Custos de treinamento/pipeline com índice OpenSearch, instrumentação de benchmark_llm/label/augmentation, endpoint API e UsageView. CompanionOrb. Preços LLM atualizados. |
| 2 | [companion_orb_aurora_thinking](companion_orb_aurora_thinking.plan.md) | CompanionOrb com mecânica orbital Kepleriana, aurora borealis e estados visuais (idle, thinking, responding) |

---

## 0.9.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [classificacao_4_modos_pipeline_dados_v090](classificacao_4_modos_pipeline_dados_v090.plan.md) | Reestruturação pipeline de dados (corpus unificado, splits estratificados, fim data leakage). Expansão para 4 modos (bootstrap, sparse_logreg, setfit/ModernBERT, LLM). Benchmark card definitivo. Ciclo ML com modos configuráveis, cancelamento, herança de métricas. Frontend: barras progresso SSE, evolução recente com delete, sync modelo triagem. Augmentation preparada (feature flag off). |

---

## 0.8.1

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [migracao_pypdf_para_pymupdf](migracao_pypdf_para_pymupdf_e5f6g7h8.plan.md) | Migração do motor de extração PDF de pypdf para pymupdf com parsing espacial via bounding boxes |

---

## 0.8.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [ml_ciclo_e_benchmarking](ml_ciclo_e_benchmarking_961e78ef.plan.md) | Diagnóstico factual do benchmark atual, clarificação do papel de `baseline` vs `bootstrap` e direção incremental para ciclo ML com benchmark, retreino e promoção controlada |
| 2 | [ciclo_ml_0_7](ciclo_ml_0_7_b3080de2.plan.md) | Registry operacional do classificador, benchmark + retreino com reports persistidos, champion/override, serving supervisionado com fallback e transparência na UI |
| 3 | [naming_e2e_commit](naming_e2e_commit_ff496695.plan.md) | Corte final de `{area}` para `{business_domain}`, reescrita do E2E `0.8.0` como delta do `0.7.0` e fechamento estrutural com gates de qualidade |
| 4 | [classifier-dataset-root](classifier-dataset-root_b9b69d72.plan.md) | Primeira migração para root operacional dos datasets em `_ATLASFILE`, com snapshots do training pool, dataset manifest, lineage e guardrails de integridade |
| 5 | [classifier-single-source](classifier-single-source_896138eb.plan.md) | Segundo corte arquitetural para remover o seed físico do repo do runtime, mover fixtures para `backend/tests/fixtures` e consolidar `_ATLASFILE` como fonte física única |

---

## 0.7.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [bootstrap_config_source](bootstrap_config_source_31378c1a.plan.md) | Bootstrap config-driven: `default.json` como fonte única da política de classificação; remoção de `DEFAULT_*`; inclusão de `suprimentos`, `edital` e `plano`; benchmark e editor blindados contra drift |
| 2 | [fechar_ciclo_atlasfile](fechar_ciclo_atlasfile_837ac0a4.plan.md) | Fechamento do ciclo com `training_pool` real e disjunto, ampliação do `validation_set`, benchmark oficial, rebuild Docker e smoke funcional de ingestão, busca/highlight e assistente |

---

## 0.6.0

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [canais_transparentes_e_classificacao](canais_transparentes_e_classificacao_9fc37008.plan.md) | Canais como pipe transparente (sessão/histórico/usage unificado); rastreamento de uso LLM na classificação; gestão de janela de contexto (truncamento FIFO + ContextRing); filtro por canal na UsageView |
| 2 | [fix_cross-channel_session_sync](fix_cross-channel_session_sync_dfc3371f.plan.md) | Correção de sessões cross-channel (append atômico, refresh antes de enviar); espelhamento configurável de respostas para canal de origem (Markdown→HTML); SSE real-time para atualização automática do chat web |

---

## 0.5.0 (2026-03-09)

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [fix_usage_cost_tracking](fix_usage_cost_tracking_102e73ab.plan.md) | Correção de 5 bugs no rastreamento de uso/custo: `usage_by_model` per-session; acumulação em sessões novas; title tokens contabilizados |
| 2 | [search_ui_mintlify_redesign](search_ui_mintlify_redesign_36583d18.plan.md) | Redesign da barra e modal de busca no estilo Mintlify: pill-shape, focus ring accent, lista flat com hover highlight, proporções e sombras refinadas |

---

## 0.4.0 (2026-03-06)

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [simplificar_formato_canonico](simplificar_formato_canonico_765c9e08.plan.md) | Formato canônico configurável via `naming.canonical_pattern`; remoção de `area_key` do nome; preservação do nome original intacto; `_fs_safe` e `extract_original_name_from_canonical` |
| 2 | [naming_pattern_migration](naming_pattern_migration_43076f52.plan.md) | Coluna `naming_pattern` per-file no `_INDEX.md`; parsing reverso usa pattern da row (não do profile); backward-compat com fallback |
| 3 | [para_roots_scan](para_roots_scan_7de6d48a.plan.md) | Scan de todas as roots PARA (`01_PROJECTS`, `02_AREAS`, `03_RESOURCES`, `04_ARCHIVE`); remoção do fallback legado `_WORK/`; `area_key` por categoria PARA |
| 4 | [content_indexing_architecture](content_indexing_architecture_6b04708a.plan.md) | Arquitetura Pure Nested: remoção de 4 campos flat (`content`, `content_normalized`, `content_chunks_text`, `content_chunks_normalized`); busca full-text migrada para nested queries; highlight via `inner_hits` |
| 5 | [fix_search_highlighting](fix_search_highlighting_781facff.plan.md) | Dual highlight nativo (text + text_normalized); eliminação de funções manuais; `_trim_highlight` preserva todos `<em>`; snippet 120 chars; ordenação híbrida |
| 6 | [list_documents_+_mcp_fixes](list_documents_+_mcp_fixes_a27cba5a.plan.md) | Endpoint `GET /api/documents` (listagem/browse); tool MCP `list_documents`; guard `min_length` no `search_documents` |
| 7 | [controle_operacional_+_responsividade](controle_operacional_+_responsividade_7ee57b2a.plan.md) | Controle operacional redesenhado; dashboard stats; responsividade 1024-1280px; mini-table de projetos |
| 8 | [onboarding_ui_+_install](onboarding_ui_+_install_94d25d7b.plan.md) | `OnboardingWizard`; endpoint `GET /api/setup/status`; detecção automática de primeira execução |
| 9 | [atlasfile_channel_integration](atlasfile_channel_integration_79e456ca.plan.md) | Camada nativa de channels (protocol Channel + ChannelManager); TelegramChannel via aiogram 3.x; endpoints `/api/channels/*`; UI no modal do Assistente |
| 10 | [docx_pagina-paragrafo](docx_pagina-paragrafo_a4f5b688.plan.md) | Localização amigável para DOCX no formato Página/Parágrafo; estratégia híbrida (marcadores reais + fallback estimado); labels `docx_page` e `docx_page_est` |

---

## 0.3.0 (2026-03-05)

| # | Plano | Escopo |
|---|-------|--------|
| 1 | [classifier_scoring_improvement](classifier_scoring_improvement_15688aec.plan.md) | Word boundary matching; normalização sqrt; routing rules completas |
| 2 | [llm_visibility_templates_aliases](llm_visibility_templates_aliases_9e3f44f1.plan.md) | Campos de visibilidade LLM; contexto de projeto no prompt; prompt de chat enriquecido |
| 3 | [template_editor_completo](template_editor_completo_58250547.plan.md) | Template store backend; CRUD API; editor visual; seleção na inicialização |
| 4 | [search_filters_stats_llm_context](search_filters_stats_llm_context_f0eb431c.plan.md) | Endpoint `GET /api/stats`; filtros `doc_kind` e `area_key` na busca |
| 5 | [atlasfile_profile_v2_cutover](atlasfile_profile_v2_cutover_58945536.plan.md) | Migração para Profile v2 com schema Pydantic; validação; histórico |
| 6 | [profile_v2_e_layout_llm](profile_v2_e_layout_llm_5b350c4b.plan.md) | Layout plan/apply; editor de profile; seções colapsáveis |
| 7 | [nested_chunks_inner_hits](nested_chunks_inner_hits_a1b2c3d4.plan.md) | Nested chunks com inner_hits; localização por chunk; highlight por trecho |

---

## Históricos (rascunhos superados)

| Documento | O que é |
|-----------|---------|
| [plan_one_line_installer](plan_one_line_installer.md) | Rascunho original do instalador one-liner (estilo OpenClaw), anterior à v0.21.0. **Superado**: o que foi entregue entre a v0.21.0 e a v0.56.0 diverge em URLs, flags e arquitetura — o banner do documento traz a tabela rascunho × entregue. Movido de `docs/roadmap/` em 2026-07-29; o CHANGELOG referencia o caminho antigo como registro histórico |
