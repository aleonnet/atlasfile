# Roadmap — AtlasFile

Evoluções avaliadas com critério e registradas para além das sessões de desenvolvimento.
Cada item traz o **gatilho** que justifica tirá-lo daqui — nada entra em execução sem plano próprio aprovado.

## Internacionalização e classificação multilíngue

_Contexto: v0.33.0 entregou UI PT-BR/EN-US completa e classificação bilíngue no modelo SKOS/EuroVoc (key canônico + sinônimos multilíngues na mesma entrada). Detalhes em `planos_concluidos/frontend_sota_tanstack_query_i18n_ptbr_enus_v0330.plan.md`._

| Item | O que é | Gatilho para executar |
|---|---|---|
| Detecção de idioma por documento (`doc_language`) + analyzers por idioma no OpenSearch | Padrão Elastic multilingual: cada doc detecta o idioma na ingestão; índice usa analyzer específico (stemming EN vs PT); dicionários de topics/aliases separados roteados pela detecção | Dicionários multilíngues combinados começarem a colidir (falsos positivos cross-idioma) ou entrada de um 3º idioma |
| `topics` EN validado por corpus | Os +315 sinônimos EN (v0.33.0) foram derivados por tradução de domínio; validação estatística exige corpus EN rotulado no pipeline do classificador | Volume real de documentos EN decididos na triagem suficiente para compor validação |
| Localização de prompts LLM | **Rejeitada com critério** (v0.33.0): prompt canônico único + regra "responda no idioma do usuário" cobre o caso sem duplicar manutenção/QA | Só reavaliar se um idioma exibir qualidade de resposta comprovadamente inferior |

## Classificador

_O item "Sugeridor de aliases a partir da triagem" foi executado — ver
`planos_concluidos/bootstrap_alias_suggester_v0370.plan.md` (v0.37.0), com o
loop de descoberta fechado na v0.39.1–v0.39.2 (cortes de qualidade + toast +
estado vazio explicativo)._

_Executados na v0.44.0 — ver
`planos_concluidos/tier1_confianca_aprendizado_reconcile_cookie_v0440.plan.md`:
"Scoring de domínio sem diluição √N" (diagnóstico do √N foi REFUTADO pelo
`scripts/trace_classification.py` — a causa real era overlap tipo↔domínio
pontuando sem evidência de conteúdo, corrigida com gate), "Aliases por projeto
vs globais" (escopo na aprovação, default projeto) e "Escopo do reconcile
visível na UI" (label + tooltip por modo)._

| Item | O que é | Registrado em |
|---|---|---|
| ~~Órfão em `_TRIAGE_REVIEW/pending`~~ | **Entregue na v0.45.0** — ver `planos_concluidos/ciclo1_confianca_acesso_naming_v0450.plan.md` (varredura no reconcile com guarda de 600s; move para rejected com meta sidecar, nunca deleta) | — |
| Nome embrulhado como sinal de classificação | A reingestão de canônico foi corrigida (v0.45.0), mas a CLASSIFICAÇÃO ainda vê o nome embrulhado como sinal de filename (tokens de projeto/domínio no nome podem enviesar aliases). Usar o nome desembrulhado como sinal exige benchmark próprio antes. | 2026-07-25, observação do ciclo 1 |

## Instalação / onboarding

| Item | O que é | Gatilho para executar |
|---|---|---|
| ~~Instalador bootstrapa os próprios pré-requisitos~~ | **Entregue na v0.43.0** — ver `planos_concluidos/installer_bootstrap_prereqs_v0430.plan.md` (bootstrap com confirmação, `--install-deps`, en-US, step 0 do site removido). O Ollama opt-in daquele ciclo **saiu do instalador na v0.55.0**: o pull são vários GB e tirava a previsibilidade da duração | — |

### Distribuir a build pronta em vez de compilar na máquina do usuário

| Item | O que é | Gatilho para executar |
|---|---|---|
| Publicar imagens no GHCR e consolidar a stack | **Plano escrito e revisado, nada executado** — ver `roadmap/distribuicao_build_imagens_ghcr.md`. Hoje o `install.sh` clona o repositório e compila na máquina do usuário, então o que ele instala nunca é o que a bancada testou (9 dependências sem teto, `lucide-react` em `latest`, apt sem versão, imagem base em tag móvel, nenhum teste tocando stack real). O plano publica **uma** imagem multi-arquitetura no GHCR, consolida os 5 containers em 2, troca o clone por um pacote de ~10 KB e prova a imagem com um smoke de fluxo real. Corta 33% do download e todo o tempo de compilação no host | **Decisão de arranque é sua.** O plano está em 4 etapas e a última se divide em Linux e Windows; a etapa Windows depende do item 4 abaixo (a bancada Windows precisa voltar a enxergar antes de ser reescrita). As três primeiras etapas não dependem de nada |

### Pendências abertas dos instaladores (v0.56.1 / v0.56.2)

Sobraram da auditoria de paridade (PR #2) e do E2E em Linux com stack real
(PR #3). Nenhuma bloqueia usuário; estão em ordem de custo/benefício.

| # | Item | O que é | Por que ainda não foi feito |
|---|---|---|---|
| 1 | ~~`--dry-run` do `install.sh` se contradiz~~ | **Entregue na v0.56.3** — ver `planos_concluidos/tres_correcoes_naming_reconcile_dryrun_v0563.plan.md`. **Não era a correção de ~1 linha** que este item registrava, e o defeito era pior: com binário presente mas mudo, a tela dizia `✘ docker not found` e `✔ none — everything needed is already here` — as duas seções discordavam da *existência* do Docker, não só do daemon. A causa eram duas fontes de verdade; `doc_prereqs` passou a registrar `DOC_MISSING`/`DOC_BLOCKERS` e o `run_dry_run` consome em vez de remedir | — |
| 2 | `install.ps1` sem `-NoOpen`, `-RepoUrl` e `-NoOllama` | O `.sh` tem as três; o `.ps1` não. `-RepoUrl`/`ATLASFILE_REPO_URL` é a que dói: **impede testar um *fork* de ponta a ponta no Windows** (uma *branch* funciona, via `ATLASFILE_SH_URL` + `-Branch`) | Achado A4 da auditoria, deliberadamente fora dos 31 itens aprovados. Exige mexer no `param()`, no `Show-Usage` e no encaminhamento — a guarda `check_flags` cobra os três. **CONGELADO enquanto o plano de distribuição estiver de pé**: sem clone não existe "repo URL", existe registry e versão — implementar `-RepoUrl` agora é criar uma bandeira que aquele plano apaga. `-NoOpen` e `-NoOllama` são independentes e podem ir a qualquer momento |
| 3 | Painel final do `install.ps1` usa `wsl -e` sem `-u root` | Os comandos de `logs`/`stop` que a caixa final imprime não carregam `$script:WslUser`. Funciona hoje porque distro não inicializada tem root como padrão; **quebra assim que alguém completar o assistente de conta do Ubuntu** | Achado A7, mesma decisão de escopo. Risco baixo, correção pequena. **Vai junto com a etapa Windows do plano de distribuição**, que reescreve esse painel inteiro de qualquer forma — fazer antes é escrever duas vezes |
| 4 | 6 falhas pré-existentes da bancada Windows sob `prlctl exec` | A `main` já falha 6 asserções do grupo "fechamento de trilho/calha" quando a bancada roda via `prlctl exec` na VM Parallels. **Não são regressão** — medidas contra baseline da `main` no mesmo canal | Hipótese **não provada**: `prlctl exec` roda como `nt authority\system` com saída redirecionada, `$AfTrueColor` cai e o desenho degrada. **É a mais valiosa, e agora é BLOQUEANTE**: além de cegar a bancada Windows neste canal, ela trava a etapa Windows do plano de distribuição. Aquela etapa reescreve o caminho de instalação do `install.ps1`, e a bancada Windows não tem **nenhuma** asserção sobre clone/build (contra 80 linhas do lado Linux) — reescrever com ela cega, e com 6 falhas não explicadas por cima, é trial-and-error por definição. **É o único item aberto do roadmap que trava outro trabalho** |
| 5 | Estimativa de tempo desatualizada | O instalador fala em café (`install.sh:2585`, `a good moment for a coffee`) e o `install.ps1:2267` promete **~15 min** ao usuário. Medido numa VM Ubuntu ARM64: **48s de build, 2m10s no total**, e 94s a frio no runner x86 do CI. **Correção de atribuição (2026-07-29):** este item dizia que os ~15 min estavam no `INSTALL.md` — não estão; verificado nas 541 linhas. As ocorrências são `install.ps1:2267` (a única user-facing) e comentários em `install.ps1:2286` e `install.sh:242` | Uma única medição não justifica mudar o texto. **Gatilho: medir em mais uma máquina** (x86, disco lento ou rede fria) antes de recalibrar. **Deixa de existir se o plano de distribuição andar**: sem compilação no host, o tempo passa a ser o do download, que é previsível e não precisa de calibragem |
| 6 | Site publica `--with-ollama` | Quatro ocorrências em `~/Development/atlasfile-website`. As flags do Ollama são aceitas e ignoradas desde a v0.55.0, então **não quebra** — mas o site ensina o que o instalador desaprovou | Fora deste repositório |

**Como validar o que for feito.** O `install.sh` tem E2E com stack real numa VM
Linux (`lima`) — ver `planos_concluidos/uninstall_linux_stack_real_v0562.plan.md`.
O `install.ps1` só é validável na VM Parallels ou no CI: a bancada invoca
`powershell` 5.1, que não existe no macOS. **Sempre medir a VM contra a baseline
da `main` no mesmo canal** — sem isso, as 6 falhas do item 4 leem como regressão.

## Extração

| Item | O que é | Registrado em |
|---|---|---|
| ~~OCR de imagens embutidas em DOCX/PPTX/XLSX~~ | **Entregue na v0.48.0** — ver `planos_concluidos/ocr_imagens_embutidas_office_v0480.plan.md` (OCR de `word/media/*`, `ppt/media/*`, `xl/media/*` quando o documento não tem texto próprio; cap de 10 imagens registrado em metadata; validado no docx-envelope real que motivou o item: 1.698 chars extraídos) | — |
| Causa real na mensagem da triagem "sem texto extraível" | O extrator agora registra `embedded_images_found`/`embedded_images_ocr` no metadata — insumo pronto para a UI dizer "contém apenas imagem embutida sem texto legível" em vez do genérico. Falta plumbing metadata → meta da triagem → `TriageItem` → i18n. Caso ficou raro (scans legíveis agora classificam normalmente). | 2026-07-25, observação da v0.48.0 |
| OCR embutido em Office legado (.doc/.xls/.ppt) | Legados são binários OLE2, não zip — `_ocr_embedded_images` (zipfile) não os alcança; exigiria parser OLE dedicado (ex.: olefile). Gatilho: aparecer envelope legado real na triagem. | 2026-07-25, limitação registrada na v0.48.0 |
| OCR inline em DOCX/XLSX (doc COM texto + imagem de conteúdo) | **Rejeitado com critério na v0.49.0** (decisão do usuário, custo-benefício): em docx o conteúdo está no texto e em xlsx imagem é logo/gráfico decorativo — só o PPTX ganhou modo "sempre" (ver `planos_concluidos/ocr_inline_pptx_calibrado_v0490.plan.md`). Gatilho para reavaliar: caso real de docx/xlsx com texto nativo + scan embutido relevante perdido. | 2026-07-25 |

## Dashboard / observabilidade

| Item | O que é | Registrado em |
|---|---|---|
| Durabilidade de chats e eventos de custo | Incidente real (25/07, dois resets de volume): chats e eventos de custo LLM vivem SÓ nos índices — sem origem em filesystem, perda de volume é perda permanente (docs/profiles/ingest_history sobrevivem por morar no disco). Candidatas com trade-offs a avaliar em plano próprio: (a) journal append-only em `_ATLASFILE/` reconcile-ável (coerente com local-first) ou (b) snapshots nativos do OpenSearch para diretório montado. Gatilho: antes da próxima minor com mudanças de índice. | 2026-07-25, pós-incidente dos volumes |
| ~~Credencial do Observabilidade acessível da UI~~ | **Entregue na v0.51.0–v0.51.1** — ver `planos_concluidos/sso_local_observabilidade_v0510.plan.md`. A solução ficou melhor que as candidatas registradas (mostrar/copiar a senha): o link abre o dashboard **já autenticado** — a API loga pela rede interna e devolve os cookies de sessão no redirect, então a senha nunca chega ao browser, à URL ou ao histórico. Degrada para a tela de login em qualquer falha ou quando o Dashboards está em outro domínio. | — |
| ~~Link "Observabilidade" na UI~~ | **Entregue na v0.45.0** — ver `planos_concluidos/ciclo1_confianca_acesso_naming_v0450.plan.md` (URL derivada do host atual + `DASHBOARDS_PUBLIC_URL` opcional para proxy) | — |
| Heatmap hora × dia da ingestão | Exige campo derivado na INDEXAÇÃO (`ingested_hour`/`ingested_weekday`) — scripted fields via ndjson apagam o cache de campos do index-pattern (aprendido em campo, v0.42.0). | 2026-07-23 |
| Alerting nativo do OpenSearch | Monitores: extração `failed` acima de N, custo LLM diário acima de teto, fila de triagem acumulando, **disco acima do high watermark / índice com bloco read-only** (incidente real de 2026-07-25: flood-stage silencioso derrubou toda ingestão até o diagnóstico manual) — pendente de o usuário definir canal de notificação (e-mail/webhook). | 2026-07-23; monitor de disco em 2026-07-25 |
| Reporting PDF agendado | Relatório periódico do dashboard "AtlasFile — Operação" via plugin de reporting. | 2026-07-23 |
| ~~Cookie password por instalação no Dashboards~~ | **Entregue na v0.44.0** — ver `planos_concluidos/tier1_confianca_aprendizado_reconcile_cookie_v0440.plan.md` (`DASHBOARDS_COOKIE_PASSWORD` via flag CLI no compose; install.sh + guard no make; a allowlist de env do entrypoint não cobre `opensearch_security.*`) | — |

## Modelos custom / Ollama

| Item | O que é | Registrado em |
|---|---|---|
| ~~Seletores de modelo agrupados por provedor~~ | **Entregue na v0.46.0** — ver `planos_concluidos/seletores_agrupados_por_provedor_v0460.plan.md` (combo rápido com curadoria: atual + recentes + customs em `<optgroup>`; catálogo completo com busca segue no settings, também via "Todos os modelos…"; cascata rejeitada com critério) | — |
| ~~Estado vivo do modelo custom no seletor~~ | **Entregue na v0.45.0** — ver `planos_concluidos/ciclo1_confianca_acesso_naming_v0450.plan.md` (LED verde/vermelho com tooltip nos seletores de chat e triagem; cheque vivo a cada 60s enquanto abertos + ao focar a janela; storage com data e migração). Auto-start do daemon segue impossível do container — só instalador/agente no host. | — |

## E2E pendentes

| Item | O que é | Registrado em |
|---|---|---|
| ~~Chat Kimi (Moonshot) completo~~ | **Validado pelo usuário em 2026-07-25** com o Kimi K3 na stack de desenvolvimento ("testei com kimi k3 e tudo certo") — o gatilho era ter créditos na conta Moonshot. Sem plano próprio: a integração já existia desde a v0.36.0, o que faltava era a prova em conta real. | — |
| ~~`install.sh` com stack real no ar~~ | **Feito na v0.56.2** em VM Ubuntu 24.04 ARM64 (`lima`): instalação do zero, os cinco caminhos do `--uninstall`, e o ciclo `--keep-data` → reinstalação reusando volume e senha. Container Linux **não** precisa de virtualização aninhada — foi isso que destravou | — |
| `install.ps1` com stack real no ar | Instalar e desinstalar no Windows **com os 5 containers subindo**. Hoje só os caminhos sem daemon são validados (VM Parallels e CI) | **Gatilho atingido (2026-07-29): há um Windows 11 real disponível.** Roteiro de comandos pronto em `teste_windows_11_real.md` — zerar o WSL do absoluto zero, instalar, reinstalar por cima, os quatro caminhos de desinstalação e o ciclo `-KeepData` → reusar volume. Era bloqueado por hardware no Mac (exige Hyper-V → virtualização aninhada em convidado Windows, que nem Parallels nem UTM entregam em Apple Silicon; só convidado *Linux*, desde macOS 15 + M3) |

## Website

| Item | O que é | Registrado em |
|---|---|---|
| Eixo `doc_kind` no lead do catálogo | "classified by business domain and document type" está incompleto — existe o 3º eixo de formato (item 5 da auditoria). | 2026-07-23 |
| og:image no domínio próprio | Comentários `ABSOLUTE-URL: update on custom domain` a revisar quando o site migrar de GitHub Pages para domínio próprio (item 6 da auditoria). | 2026-07-23 |

## Direção de arte / visual

| Item | O que é | Estado |
|---|---|---|
| ~~Shader blackhole (item a do trio)~~ | **Redefinido pelo usuário e entregue na v0.47.0**: em vez de indicador de contexto do chat, o blackhole substituiu o halo arco-íris da **aura de processamento** (orb + respiração accent — ver `planos_concluidos/llm_type_aura_medidor_v0470.plan.md`). O medidor de contexto seguiu textual e ficou honesto (janela real do Ollama, recálculo na troca, tooltip com heurística). | — |
| Lensing "por cima do conteúdo" na aura e no ciclo | **REJEITADO com critério pelo usuário (2026-07-25), após benchmark real**: bancada com o card da triagem e 4 técnicas no Chrome real (`--headless=new`) mostrou que as duas variantes que de fato interagem com o conteúdo custam legibilidade — `backdrop-filter: blur+contrast` radial borra o texto no raio, e refração real (`feDisplacementMap`, só Chromium) curva o texto perto do centro. Performance NÃO era o problema (60 fps / ~16,4 ms por frame em todas, com mapa de deslocamento estático). Decisão: leitura vale mais que wow; a aura segue com o shader atrás. Gatilho para reavaliar: aparecer técnica que distorça só o fundo, preservando glifos (ver `w3c/svgwg#1142`). | 2026-07-25, benchmark arquivado em `~/Desktop/atlasfile_lensing_bench/` |

## Como usar este arquivo

- Adicione itens SEMPRE com gatilho explícito — roadmap sem critério vira lista de desejos.
- Ao executar um item: plano próprio em `planos_concluidos/` ao concluir, e o item sai daqui com um ponteiro para o plano.
