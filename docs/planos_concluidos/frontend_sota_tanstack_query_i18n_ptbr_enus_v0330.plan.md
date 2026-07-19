# frontend_sota_tanstack_query_i18n_ptbr_enus_v0330 — Consolidação SOTA do frontend + i18n PT-BR/EN-US

## Contexto

O frontend funciona ("praticamente tudo do jeito esperado") mas cresceu por acreção: 5 mecanismos de estado coexistem (state local, 4 contexts, bus de CustomEvent, localStorage espalhado, polling/SSE por feature), App.tsx é um god component (~850 linhas, ~25 props drilladas para PainelView) e o keep-alive foi construído à mão em 3 camadas. Os bugs de reatividade corrigidos um a um nesta sessão (histórico stale, 3/3 congelado, orb tremendo, badge desatualizado) são a classe de defeito que uma camada de server-state formal elimina por construção. O usuário pediu: (1) confirmar se a proposta é de fato benchmark/SOTA para as necessidades de UX do AtlasFile (streaming, keep-alive, estado centralizado, shaders, reatividade, responsividade), (2) plano 100% de ajustes + testes, (3) estrutura de localização começando por PT-BR e incluindo EN-US.

Decisões do usuário (AskUserQuestion):
- i18n de mensagens do backend: **códigos estáveis + tradução na UI** (não Accept-Language, não PT-BR fixo).
- Seleção de idioma: **auto-detect do navegador + seletor persistido** (fallback PT-BR).
- Ordem: **estado primeiro, i18n depois** — condicionado à validação de que TanStack Query é mesmo o benchmark adequado (ver análise abaixo).

## Validação SOTA (o que é benchmark para CADA necessidade citada)

| Necessidade | Estado atual | SOTA para apps desta classe | Veredito |
|---|---|---|---|
| Estado de servidor (fetch/cache/invalidação) | bus manual + reloads por card | **TanStack Query v5** — padrão de facto (React Query), invalidação por chave, cache, refetch, devtools | ADOTAR (justificativa abaixo) |
| Reatividade pós-mutação | emitDataRefresh() artesanal | `queryClient.invalidateQueries()` | Substitui o bus |
| Polling (health, fases de decisão, telegram) | setInterval/setTimeout manuais | `refetchInterval` do Query (com pausa por aba oculta nativa) | Substitui os timers |
| Streaming (chat SSE/fetch-stream, upload XHR) | hooks próprios | **Manter hooks próprios** — streaming de chat NÃO é caso de Query (é fluxo imperativo); SOTA é exatamente hook dedicado + estado local | MANTER |
| SSE de progresso (reconcile, ciclo, ingest) | EventSource por feature | SSE alimentando `queryClient.setQueryData` (ponte única) | Unificar |
| Keep-alive | CSS hidden + forceMount + localStorage | Padrão Activity/tab-navigator (é o que já fizemos) + cache do Query torna remount barato | MANTER (formalizado) |
| Estado de cliente (tema, idioma, seleções) | contexts + localStorage ad-hoc | Contexts estão OK para o volume; SOTA "Zustand" só se justifica com mais escala — **não adotar** (evitar dependência sem dor real) | MANTER contexts, centralizar persistência num helper `storage.ts` |
| Shaders/arte (OrbGL WebGL, AuroraField canvas, auras CSS) | já é o diferencial do produto | Sem mudança — não há framework a adotar; manter tokens/keyframes | MANTER |
| Responsividade | Tailwind v4 | já é SOTA | MANTER |
| i18n | inexistente (PT-BR hardcoded) | **i18next + react-i18next** (padrão de facto, detecção + fallback + pluralização/interpolação ICU-like) vs Lingui/FormatJS — análise abaixo | ADOTAR i18next |

### Por que TanStack Query e não alternativas (resposta à condicional do usuário)
- **vs SWR**: SWR é mais minimalista, mas invalidação por prefixo de chave, mutations de primeira classe e devtools do TanStack são exatamente o que substitui nosso bus; SWR exigiria mais cola manual.
- **vs RTK Query/Redux**: traria um store global que NÃO precisamos (estado de cliente é pequeno) — custo de boilerplate sem ganho.
- **vs manter o bus artesanal**: o bus já provou o modelo (invalidar → recarregar). O Query é esse modelo com cache, dedupe de requests concorrentes, retry, e pausa de polling em aba oculta — grátis.
- **vs Zustand para tudo**: Zustand resolve estado de CLIENTE, não cache de servidor; nosso problema dominante é servidor.
- Fatores do AtlasFile que pesam A FAVOR: SPA de 3 telas keep-alive (cache por chave elimina refetch ao voltar), muitos dados derivados do servidor (stats, triagem, histórico, rejeitados, classificador, readiness), polling heterogêneo, testes com vi.mock de api.ts (Query preserva esse padrão: continua mockando api.ts; muda só o invólucro).
- Fator CONTRA (honesto): +~13kb gzip e uma curva de aprendizado de chaves/invalidations. Aceitável.

### Por que i18next e não alternativas
- **react-i18next**: padrão de facto, runtime maduro, `LanguageDetector` (auto navegador + localStorage), interpolação/plural nativos, namespaces por feature, zero SSR/extract-step obrigatório — encaixa em Vite SPA sem build extra.
- **vs Lingui**: DX ótima (macros + extração), mas exige passo de build/extract e macros Babel/SWC — atrito no Vite atual sem ganho proporcional num app com ~1 idioma extra.
- **vs FormatJS/react-intl**: forte em ICU, porém mais verboso; pluralização PT/EN simples não exige ICU completo.

## Inventário verificado (exploração 1 — arquitetura de estado)

- `App.tsx` 864 linhas; `api.ts` 1011 linhas com **68 wrappers** (~35 GET de leitura, 33 mutações) + 5 URLs de stream + 1 XHR de upload com progresso.
- **4 contexts** (Settings 198l com 10 chaves localStorage; Project — já assina o bus; Navigation — hash routing próprio, sem react-router; Processing — poll 1s da fase de decisão).
- **~14 componentes/hooks com fetch próprio** (useState+useEffect+bus): InboxQueueChips, InboxScanCard (useIngestMonitor SSE+poll 250ms), LabelConflictsCard, RejectedCard, IngestHistoryCard, ProfileLayoutWorkspace (api própria em features/profile-layout/api.ts), IngestTriageCard (5 fetches + SSE ciclo), TemplateEditorView, UsageView (Promise.all de 4), MoveDocumentModal, useSearch (14 useStates, elevado ao App → 16 props), useChatSession (13 useStates, elevado → 28 props).
- **3 cópias do padrão SSE+fallback-poll** (reconcile em App boot L323 E handler L415 — duplicado internamente; ingest; classifier-cycle).
- **Pollers**: decisão 1s, health 30s/5s adaptativo, telegram 15s, fallbacks 250ms/1.5s, debounce busca 220ms.
- **Chat NÃO faz streaming de tokens** — POST bloqueante com AbortController; SSE só para sync multicanal (Telegram). Upload é XHR (progresso). ⇒ "streaming" do requisito do usuário = manter/melhorar via hook dedicado; Query não toca nisso.
- **Bus** `atlas:data-refresh`: 6 assinantes, 7 emissores. `atlas:ingest-active`: orb. `atlas:pick-files`: portal.
- **15 chaves localStorage** espalhadas (2 dinâmicas), todas com try/catch próprio repetido.
- Keep-alive: telas via `visitedViews`+hidden (App L90-93, 623-688), abas Config via forceMount, colapsáveis via persistKey.

## Inventário verificado (exploração 2 — strings e visual)

- **i18n greenfield**: zero infra; PT-BR cravado como "contrato" em comentários (calendar.tsx, date-range-picker.tsx). Volume: **~1.100–1.600 strings** de UI em 30–45 arquivos; pesados: ChatPanel (992l), IngestTriageCard (939l), App, OnboardingWizard, PainelView, UsageView.
- **Padrões custosos**: interpolação `${…}` difusa (ex.: 16 no App, 14 no ChatPanel); pluralização literal "(s)"/"documento(s)" (App L252/315-318/405-408, SettingsContext, GlobalDropPortal) → precisa plural real para EN; dicionários de rótulos em constantes de módulo (PHASE_LABELS, formatPhaseLabel ×2, CHANNEL/GRANULARITY/TOKEN/PROCESS_LABELS, DATASET_LABELS, mapa de skip_reason em IngestTriageCard:77).
- **Formatação regional**: 46 usos de toLocale*/toFixed em 16 arquivos; 10 literais `"pt-BR"`; date-fns `ptBR` em UsageView/date-range-picker/calendar.
- **Strings do backend na tela** (4 categorias): (a) `HTTPException.detail` — ~80 literais PT-BR (com mistura EN técnica) em main.py, chegam via api.ts→toasts; (b) `blockers/suggestions[].message` do dataset_holdout.py — copy PT interpolada renderizada verbatim no IngestTriageCard (que já filtra por `code`!); (c) `skip_reason[]` — **já são códigos**, FE traduz (IngestTriageCard:77); (d) fases de decisão/ciclo/ingest — **já são códigos**, FE traduz. ⇒ A decisão do usuário (códigos+tradução na UI) significa: converter (a) e (b) para o padrão que (c) e (d) já usam.
- **Sistema visual intacto e agnóstico**: OrbGL (WebGL2 puro, shaders GLSL com uniforms por estado, tokens CSS→RGB, MutationObserver de data-theme), AuroraField (canvas 2D, mola/parallax), styles.css (tokens brutos + light via [data-theme]), theme.css (mapeamento semântico p/ Tailwind v4 + 12 keyframes atlas-*), reduced-motion sistemático (11 pontos JS + CSS). i18n não toca nada disso; único cuidado: layout tolerar expansão/contração EN↔PT.
- Deps atuais relevantes: Tailwind v4 via plugin Vite, framer-motion em 6 arquivos, date-fns v4, sem router (hash próprio no NavigationContext).

## Inventário verificado (exploração 3 — testes e restrições)

- **22 arquivos de teste**, padrão único: `vi.mock` no módulo `api` com factory de `vi.fn` (App.test.tsx: 1 mock com ~50 fns) — **permanece válido com TanStack Query** (a lib chama as mesmas funções de api.ts). Necessário: wrapper de render com `QueryClientProvider` (retry off, gcTime 0) e atenção a overrides pós-render que dependerão de refetch (ex.: reconcile progress em App.test.tsx:184).
- **279 text-queries; ~60-75% asseriam strings PT-BR literais** em 13 arquivos (OnboardingWizard concentra 80). Estratégia: PT-BR permanece idioma default nos testes → asserções viram golden strings de regressão do catálogo; poucos testes novos trocam para EN-US validando existência de chave.
- Sem MSW, sem ESLint; setup.ts com 3 polyfills (ResizeObserver, scrollIntoView, matchMedia); Recharts testado sem geometria (quirk conhecido).
- **Build/deploy**: Dockerfile do web roda `npm run dev` (Vite dev server; sem nginx, sem bundle budget, sem CSP); `VITE_API_URL` é env de runtime via compose. `npm run build` existe mas não é usado no Docker — o peso das novas deps não tem gate hoje (fato, não impedimento).
- Roteiro E2E canônico: 27 estágios (A instalação/auth, B ingestão/triagem, C ciclo, D busca/chat, E catálogo, F taxonomia, G rejeitados/concorrência) — zero regressão permitida; strings PT-BR do roteiro são golden.
- Convenções: nome único → `frontend_sota_tanstack_query_i18n_ptbr_enus_v0330`; versão alvo **0.33.0** (minor).

## Estratégia de branch (decisão do usuário)

- Todo o plano evolui na branch **`feature/frontend-sota-i18n-v0330`**, criada a partir do `main` atual. O `main` permanece estável e continua sendo a fonte do instalador/rodadas de teste do usuário (hotfixes das rodadas seguem entrando direto no main).
- Cada fase F1–F6 = um ou mais commits na branch (mensagens por fase); ao fim de cada fase, `merge main → branch` para absorver hotfixes e manter o desvio pequeno.
- Smoke E2E das fases roda no **stack dev local** (dev repo com a branch, `docker compose up` local) ou com a instância de teste temporariamente apontada para a branch (`git -C ~/AtlasFileNovo checkout <branch>` + rebuild) — sempre retornando a instância ao `main` depois.
- Merge final para `main` somente após os gates da F6 (27 estágios verdes + compat + auditoria de rede), com autorização explícita do usuário.

## Fases de execução (estado → i18n, cada fase com suíte verde + smoke E2E antes da próxima)

**Fora de escopo em todas as fases (fica como está):** streaming de chat (POST + AbortController), upload XHR com progresso, OrbGL/AuroraField/shaders/tokens, keep-alive (visitedViews + forceMount + persistKey), hash routing do NavigationContext.

### F1 — Fundação TanStack Query + migração das leituras (menor → maior risco)
- Dep `@tanstack/react-query@^5`; `QueryClientProvider` em `main.tsx` ACIMA dos 4 contexts; novos `lib/queryClient.ts` (singleton importável), `lib/queryKeys.ts` (factory), `lib/queries.ts` (hooks finos sobre os wrappers de `api.ts` — api.ts vira transporte puro; `vi.mock` dos testes permanece válido).
- **Adaptador transitório no refreshBus**: subscriber interno traduz `atlas:data-refresh` → `invalidateQueries` (emissores seguem funcionando; assinantes migrados param de escutar).
- Ordem de migração: (1) folhas isoladas — MoveDocumentModal, LabelConflictsCard, RejectedCard, IngestHistoryCard, InboxQueueChips, UsageView, TemplateEditorView, ProfileLayoutWorkspace (converter `features/profile-layout/api.ts`); (2) contexts de leitura — Settings (models), Project (projects); (3) IngestTriageCard só as 7 leituras (SSE do ciclo intacto).
- Não muda: mutações, bus emissores, App.tsx, useSearch/useChatSession, ProcessingContext, strings.

### F2 — Mutações → useMutation + invalidations; aposentar o bus
- `lib/mutations.ts`: 33 mutações com `onSuccess: invalidateQueries` por recurso (aprovar triagem → invalida triage+stats+inboxFiles; mover doc → profile+history+search…).
- `triageItems`/`dashboardStats` do App viram `useQuery` (mata o subscriber do bus no App).
- Remover 7 emits + 6 subscribers; `refreshBus.ts` reduz-se ao canal `atlas:ingest-active` do orb (sinal de UI puro, permanece).

### F3 — App slim, unificação SSE, fim do prop-drilling, storage.ts
- Novo `hooks/useSseChannel.ts` genérico (evento SSE → `setQueryData`; terminal → `invalidateQueries`; fallback-poll vira `refetchInterval` **condicional** ligado só com SSE caído). Três instâncias: `useReconcileMonitor` (deduplica os blocos duplicados do App L285-363/L387-459), `useIngestMonitor`, `useClassifierCycleMonitor`.
- Polls do App viram queries com `refetchInterval` (health 30s/5s condicional, telegram 15s) com `refetchIntervalInBackground: false`.
- `useSearch` desce para PainelView (elimina 16 props; resultados = query `['search', p, params]` com enabled no submit); `useChatSession` desce para AssistenteView (elimina 28 props; sessões CRUD = queries/mutations; **streaming da mensagem ativa intocado**). O keep-alive por forceMount preserva o estado deles — era o único motivo da elevação.
- Novo `lib/storage.ts`: registro tipado das 15 chaves localStorage (MESMOS nomes — compat), get/set com JSON safe-parse; migrar SettingsContext + 5 pontos avulsos.
- App.tsx resultante: shell + navegação + modais + pill + onboarding, consumindo queries.

### F4.5 — Classificador promovido a view da sidebar (adição do usuário, 2026-07-19)
- O Classificador é um agente operacional como o Assistente: sai da aba de Configuração e vira item de primeiro nível na sidebar (`ViewKind` ganha "classificador"; keep-alive igual às demais views; IngestTriageCard vira o conteúdo de `ClassificadorView`). Configuração fica com Perfil/Templates/Acesso.

### F4 — Fundação i18n + extração PT-BR 1:1 (zero mudança visual)
- Deps `i18next`, `react-i18next`, `i18next-browser-languagedetector`; init síncrono com recursos bundled (sem lazy-HTTP, sem flash de chave); `I18nextProvider` em main.tsx.
- Namespaces por feature: `common, painel, triage, ingest, chat, settings, usage, onboarding, templates, profileLayout, labels, errors` em `src/i18n/locales/{pt-BR,en-US}/<ns>.json`. Chaves semânticas `ns:bloco.elemento` (nunca a frase como chave); interpolação `{{count}}`; plural `_one/_other` (mata os "(s)").
- Extração em ondas, folhas → monólitos: common → triage+painel → ingest (IngestTriageCard por último da onda) → usage+settings+templates+profileLayout → onboarding → chat (ChatPanel 992l por último de todos). **PT-BR = cópia 1:1 do texto atual** — roteiro E2E golden e as 279 asserções passam por construção.
- Dicionários de módulo (PHASE_LABELS, formatPhaseLabel ×2, CHANNEL/GRANULARITY/TOKEN/PROCESS/DATASET_LABELS, mapa skip_reason) viram `labels:phase.<code>` etc. — códigos já vêm do backend, o mapa só muda de casa.
- Ainda NÃO: toLocale*/date-fns/EN-US (F5).

### F5 — Códigos de erro do backend + EN-US + formatação regional
- **Contrato aditivo** no backend: `HTTPException.detail` → `{code: "SCREAMING_SNAKE", params: {...}, message: "<texto PT-BR atual>"}` (~80 em `main.py`); `blockers/suggestions[]` de `dataset_holdout.py` ganham `params` (já têm `code`; `message` continua preenchido). Logs/formatos de sucesso intocados.
- Novo `lib/apiError.ts`: parse central — code conhecido → `t('errors:'+code, params)`; code ausente/desconhecido → exibe `message`/detail cru (passthroughs dinâmicos `str(exc)` do backend, que seguem crus por design). Zero gate de versão. Decisão do usuário (2026-07-19): NÃO existe "backend antigo" a suportar — nada em produção, front+back saem juntos; shims de compat por texto foram removidos e lógica condicional usa exclusivamente `ApiError.code`.
- EN-US completo de todos os namespaces + script de paridade de chaves (falha se divergirem).
- Seletor de idioma no ConfigView (persistido via storage.ts; detector do navegador no primeiro acesso; `fallbackLng: 'pt-BR'`).
- Novo `lib/format.ts`: `formatNumber/Date/Percent/Bytes` com `Intl.*(i18n.language)` memoizado — substitui os 46 `toLocale*` (16 arquivos) e 10 literais `"pt-BR"`; date-fns via mapa `{pt-BR: ptBR, en-US: enUS}` (UsageView, date-range-picker, calendar).

### F6 — QA, E2E e release 0.33.0
- Roteiro canônico completo (27 estágios) em PT-BR; smoke EN-US (login→ingest→triagem→chat→config); auditoria de rede em idle com todas as views visitadas (Network parado exceto polls intencionais); greps de guarda (zero `toLocale*` fora de format.ts, zero `atlas:data-refresh`, zero literal `"pt-BR"` fora de i18n/format, zero decisão por texto de mensagem — só `ApiError.code`). Item removido por decisão do usuário: teste de compat com backend antigo (não existe backend antigo). Item adicionado (candidato): severidade explícita no canal de status (`onStatus(msg, severity)`) substituindo o sniffing por regex em App.tsx:110.

## Decisões de design (fechadas)

- **queryKeys**: factory única, `[recurso, projectId?, params?]`; chaves de projeto SEMPRE carregam projectId (troca de projeto segrega cache sem invalidation manual). Nunca strings soltas em componentes.
- **QueryClient**: defaults `staleTime: 30s`, `gcTime: 5min`, `retry: 1`, `refetchOnWindowFocus: false` (keep-alive + focus-refetch causaria rajadas). staleTime por recurso: quase-estáticos (taxonomy/models/templates) 5min; listas vivas 15-30s.
- **SSE→Query**: `useSseChannel` é a única ponte; snapshot idempotente via setQueryData; poll de fallback exclusivo (nunca SSE e poll simultâneos — elimina a corrida das 3 cópias atuais).
- **refreshBus**: F1 adaptador → F2 morto → F3 arquivo reduzido ao `atlas:ingest-active`.
- **i18n**: PT-BR fonte e fallback; bundled síncrono; testes rodam em PT-BR (golden strings preservadas).
- **Erros backend**: aditivo, `message` legado sempre presente; fallback cru no cliente; catálogo em `errors.json` dos dois idiomas.

## Testes (por fase)

- **Infra (F1)**: `test/setup.ts` ganha `createTestQueryClient()` (`retry: false`, `staleTime: 0`, `gcTime: Infinity` — gcTime 0 no v5 causa cancelamentos espúrios) e `renderWithProviders()` (QueryClientProvider; + I18nextProvider pt-BR a partir de F4). Os 22 arquivos migram para o wrapper conforme cada componente é tocado, não em big-bang. Overrides pós-render (App.test.tsx reconcile L184): alterar mock + `act(() => queryClient.invalidateQueries(...))` + waitFor — tratar no mesmo commit do componente.
- **Novos por fase**: F1 factory de keys + adaptador bus→invalidation; F2 mutações representativas invalidam os recursos certos; F3 useSseChannel com EventSource mockado (evento→setQueryData; queda→poll liga; volta→poll desliga) + storage.ts + smoke das views sem props; F4 script de chaves órfãs/inexistentes + plural `_one/_other`; F5 paridade pt-BR×en-US + apiError (code→tradução; ausente→cru) + format.ts por idioma.
- **Smoke E2E real por fase** (browser, instância viva): F1 painel/triagem/uso/histórico carregam e atualizam; F2 aprovar/rejeitar/mover refletem sem reload; F3 reconcile progride via SSE, busca/chat funcionam das views, keep-alive preservado; F4 passada visual (nada muda); F5 trocar EN-US → erro de backend traduzido → PT-BR persiste; F6 os 27 estágios.

## Riscos e mitigações (top 5)

1. **Tempestade de refetch com keep-alive** (todas as views montadas = todas as queries ativas) → focus-refetch off global, staleTime por recurso, refetchInterval só onde já havia poll; gate: Network em idle parado (verificar desde F1).
2. **Corrida SSE × poll × invalidation** (pior caso: ingest 250ms) → fonte exclusiva no useSseChannel, snapshot idempotente, useIngestMonitor por último na F3, teste de failover dedicado.
3. **Testes com override pós-render quebrando silenciosamente** → staleTime 0 no client de teste + helper de invalidation; regra: suíte completa verde antes de cada novo grupo.
4. **Typo na extração de ~1.500 strings regredindo golden strings** → extração 1:1 literal (copiar, não reescrever), 279 asserções como rede por feature, script de chaves em F4, 27 estágios como gate final; ChatPanel/IngestTriageCard por último.
5. **Skew backend×frontend nos códigos de erro** → contrato aditivo com `message` sempre presente, fallback cru, teste de compat contra imagem do backend anterior; nenhum gate por versão.

## Verificação final (F6, resumida)

1. `make test` completo (backend + frontend) verde.
2. Roteiro E2E canônico dos 27 estágios em PT-BR no browser real — zero regressão.
3. Smoke EN-US: seletor troca idioma, telas principais e um erro de backend traduzidos, persistência após reload, volta a PT-BR.
4. Auditoria de rede em idle + greps de guarda.
5. (removido — decisão do usuário 2026-07-19: sem compat com backend antigo; front+back versionam juntos)

## Checklist de conclusão (CLAUDE.md)

1. Salvar este plano em `docs/planos_concluidos/frontend_sota_tanstack_query_i18n_ptbr_enus_v0330.plan.md` e atualizar o README de planos.
2. Bump `frontend/package.json` + lock **0.32.1 → 0.33.0** (minor).
3. CHANGELOG com as mudanças; revisar README/INSTALL (seção de idiomas nova).
4. Staging + proposta de commit; commit somente com autorização explícita; sem trailers.

---

## Registro de execução (2026-07-19)

Executado integralmente na branch `feature/frontend-sota-i18n-v0330` (F1–F6). Resultados por fase:

- **F1–F3** (estado): TanStack Query v5 como única camada de server-state; bus `atlas:data-refresh` aposentado; `useSseChannel` unifica os 3 padrões SSE+poll; App.tsx de 864→~670 linhas com busca/chat nas views; `lib/storage.ts` com 15 chaves tipadas.
- **F4** (extração PT-BR): 6 ondas (1 inline + 5 subagentes paralelos com namespaces pré-registrados), ~1.000 chaves em 12 namespaces; golden strings preservadas por extração literal; gate de integridade (`src/i18n/i18n.test.ts`) valida toda chave `t()` contra o catálogo.
- **F4.5**: Classificador promovido a view da sidebar (decisão do usuário mid-flight).
- **F5** (erros + EN-US + formatação): backend com 62 codes (`app/http_errors.py`, 89 raises convertidos; passthroughs `str(exc)` seguem crus por design); `lib/apiError.ts` resolve code→catálogo com `ApiError.code` para lógica condicional; `lib/format.ts` com Intl por idioma; EN-US completo com teste de paridade; seletor em Preferências + `LanguageQuickSwitch` no gate/wizard; prompts LLM respondem no idioma do usuário (prompt canônico único).
- **Decisões tomadas em execução**: sem suporte a "backend antigo" (nada em produção; front+back versionam juntos — shims textuais removidos, compat test descartado); severidade de status estrutural (`onStatus(msg, severity)`) substituiu regex; catálogo PT corrigido ortograficamente (47 strings sem acento + 9 em inglês herdadas da UI legada); tokenType/tabelas de uso traduzidos (Saída/Entrada).
- **Validação**: pytest 575/575; vitest 28+ arquivos / 209+ testes; tsc limpo; smokes reais no browser contra a instância (PT e EN, incluindo erro codificado servido pelo backend da branch); roteiro E2E atualizado em `docs/plano_teste_e2e_v0.33.0.md` (execução completa do 27 estágios: ritual do usuário pós-merge com instância zerada via installer).
