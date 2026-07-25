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
| Órfão em `_TRIAGE_REVIEW/pending` | Arquivo físico órfão (sem JSON de metadados) pode sobrar em pending após decisão — invisível na UI, sem efeito, mas é lixo em disco; varrer no reconcile. | 2026-07-23 |

## Instalação / onboarding

| Item | O que é | Gatilho para executar |
|---|---|---|
| ~~Instalador bootstrapa os próprios pré-requisitos~~ | **Entregue na v0.43.0** — ver `planos_concluidos/installer_bootstrap_prereqs_v0430.plan.md` (bootstrap com confirmação, `--install-deps`, Ollama opt-in `--with-ollama`, en-US, step 0 do site removido) | — |

## Dashboard / observabilidade

| Item | O que é | Registrado em |
|---|---|---|
| Link "Observabilidade" na UI | Não há como abrir o OpenSearch Dashboards a partir do AtlasFile — o usuário precisa saber a URL :5601 de cor. Um link no Painel (com o host derivado da config) fecha o buraco. | 2026-07-24, pergunta do usuário no teste da v0.44.0 |
| Heatmap hora × dia da ingestão | Exige campo derivado na INDEXAÇÃO (`ingested_hour`/`ingested_weekday`) — scripted fields via ndjson apagam o cache de campos do index-pattern (aprendido em campo, v0.42.0). | 2026-07-23 |
| Alerting nativo do OpenSearch | Monitores: extração `failed` acima de N, custo LLM diário acima de teto, fila de triagem acumulando — pendente de o usuário definir canal de notificação (e-mail/webhook). | 2026-07-23 |
| Reporting PDF agendado | Relatório periódico do dashboard "AtlasFile — Operação" via plugin de reporting. | 2026-07-23 |
| ~~Cookie password por instalação no Dashboards~~ | **Entregue na v0.44.0** — ver `planos_concluidos/tier1_confianca_aprendizado_reconcile_cookie_v0440.plan.md` (`DASHBOARDS_COOKIE_PASSWORD` via flag CLI no compose; install.sh + guard no make; a allowlist de env do entrypoint não cobre `opensearch_security.*`) | — |

## Modelos custom / Ollama

| Item | O que é | Registrado em |
|---|---|---|
| Estado vivo do modelo custom no seletor | O selo "(validado por você)" é localStorage estático: validou uma vez, nunca re-verifica — o usuário pode achar que tem um modelo up quando o Ollama nem está rodando, e a culpa parece dele. Proposta: re-validação ao selecionar/abrir o chat (chamada barata ao `/v1/models`), selo honesto com data e estado ("indisponível agora — Ollama parado?" com dica `ollama serve`/`ollama pull`). Auto-start do daemon NÃO é possível do container (Ollama roda no host); só via instalador/agente no host (`--with-ollama` já existe). | 2026-07-24, achado do usuário no teste da v0.44.0 |

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
| Shader blackhole como **indicador de contexto do chat** | Item (a) restante do trio: buraco negro cresce com o % de contexto da sessão (análogo do MODE_TOKENS do shader original; o dado já existe no botão "Contexto da sessão"). **Restrição de design do usuário: não pode ficar muito pequeno** — presença visual desde o início (semente já legível), não um ícone tímido. Base pronta: `BlackholeGL` entregue na v0.34.0 (itens b — fundo do gate/wizard — e c — orb no ciclo do classificador — já em produção) | Aguardando plano com mockups (o `uIntensity` do componente já aceita o fill 0..1) |

## Como usar este arquivo

- Adicione itens SEMPRE com gatilho explícito — roadmap sem critério vira lista de desejos.
- Ao executar um item: plano próprio em `planos_concluidos/` ao concluir, e o item sai daqui com um ponteiro para o plano.
