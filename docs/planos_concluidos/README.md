# Planos Concluídos — AtlasFile

Registro dos planos de implementação executados, organizados por versão.

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
