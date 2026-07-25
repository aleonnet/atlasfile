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
| ~~Instalador bootstrapa os próprios pré-requisitos~~ | **Entregue na v0.43.0** — ver `planos_concluidos/installer_bootstrap_prereqs_v0430.plan.md` (bootstrap com confirmação, `--install-deps`, Ollama opt-in `--with-ollama`, en-US, step 0 do site removido) | — |

## Extração

| Item | O que é | Registrado em |
|---|---|---|
| ~~OCR de imagens embutidas em DOCX/PPTX/XLSX~~ | **Entregue na v0.48.0** — ver `planos_concluidos/ocr_imagens_embutidas_office_v0480.plan.md` (OCR de `word/media/*`, `ppt/media/*`, `xl/media/*` quando o documento não tem texto próprio; cap de 10 imagens registrado em metadata; validado no docx-envelope real que motivou o item: 1.698 chars extraídos) | — |
| Causa real na mensagem da triagem "sem texto extraível" | O extrator agora registra `embedded_images_found`/`embedded_images_ocr` no metadata — insumo pronto para a UI dizer "contém apenas imagem embutida sem texto legível" em vez do genérico. Falta plumbing metadata → meta da triagem → `TriageItem` → i18n. Caso ficou raro (scans legíveis agora classificam normalmente). | 2026-07-25, observação da v0.48.0 |
| OCR embutido em Office legado (.doc/.xls/.ppt) | Legados são binários OLE2, não zip — `_ocr_embedded_images` (zipfile) não os alcança; exigiria parser OLE dedicado (ex.: olefile). Gatilho: aparecer envelope legado real na triagem. | 2026-07-25, limitação registrada na v0.48.0 |

## Dashboard / observabilidade

| Item | O que é | Registrado em |
|---|---|---|
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
| Chat Kimi (Moonshot) completo | Integração validada até o erro de saldo; falta E2E de chat com tool-call quando a conta Moonshot tiver créditos. | v0.36.0 |

## Website

| Item | O que é | Registrado em |
|---|---|---|
| Eixo `doc_kind` no lead do catálogo | "classified by business domain and document type" está incompleto — existe o 3º eixo de formato (item 5 da auditoria). | 2026-07-23 |
| og:image no domínio próprio | Comentários `ABSOLUTE-URL: update on custom domain` a revisar quando o site migrar de GitHub Pages para domínio próprio (item 6 da auditoria). | 2026-07-23 |

## Direção de arte / visual

| Item | O que é | Estado |
|---|---|---|
| ~~Shader blackhole (item a do trio)~~ | **Redefinido pelo usuário e entregue na v0.47.0**: em vez de indicador de contexto do chat, o blackhole substituiu o halo arco-íris da **aura de processamento** (orb + respiração accent — ver `planos_concluidos/llm_type_aura_medidor_v0470.plan.md`). O medidor de contexto seguiu textual e ficou honesto (janela real do Ollama, recálculo na troca, tooltip com heurística). | — |

## Como usar este arquivo

- Adicione itens SEMPRE com gatilho explícito — roadmap sem critério vira lista de desejos.
- Ao executar um item: plano próprio em `planos_concluidos/` ao concluir, e o item sai daqui com um ponteiro para o plano.
