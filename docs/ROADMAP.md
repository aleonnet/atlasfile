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

| Item | O que é | Registrado em |
|---|---|---|
| Scoring de domínio sem diluição √N | O score de alias é `hits/√(nº de aliases do domínio)`: um domínio rico (~20 aliases) quase não se move com 2 termos novos de 1 ocorrência — no teste real do kit marítimo, 4 aliases aprovados deixaram `juridico` abaixo de `operacoes` 46%. Proposta a estudar: saturação por hit (cada acerto contribui com ganho decrescente) em vez de normalização por tamanho do léxico. | 2026-07-23, teste E2E do aprendizado |
| Aliases por projeto vs globais | Aprovar alias hoje propaga ao template default e a TODOS os projetos; o usuário esperava aprendizado por projeto. Discutir opção de escopo na aprovação. | 2026-07-23 |
| Escopo do reconcile visível na UI | "Reconciliar INDEX" com projeto selecionado roda o reconcile POR PROJETO (sem limpeza global de órfãos, por design); com "Todos os projetos", o global. O usuário não tem como saber a diferença — deixar explícito no botão/tooltip. | 2026-07-23, teste destrutivo |
| Órfão em `_TRIAGE_REVIEW/pending` | Arquivo físico órfão (sem JSON de metadados) pode sobrar em pending após decisão — invisível na UI, sem efeito, mas é lixo em disco; varrer no reconcile. | 2026-07-23 |

## Instalação / onboarding

| Item | O que é | Gatilho para executar |
|---|---|---|
| ~~Instalador bootstrapa os próprios pré-requisitos~~ | **Entregue na v0.43.0** — ver `planos_concluidos/installer_bootstrap_prereqs_v0430.plan.md` (bootstrap com confirmação, `--install-deps`, Ollama opt-in `--with-ollama`, en-US, step 0 do site removido) | — |

## Dashboard / observabilidade

| Item | O que é | Registrado em |
|---|---|---|
| Heatmap hora × dia da ingestão | Exige campo derivado na INDEXAÇÃO (`ingested_hour`/`ingested_weekday`) — scripted fields via ndjson apagam o cache de campos do index-pattern (aprendido em campo, v0.42.0). | 2026-07-23 |
| Alerting nativo do OpenSearch | Monitores: extração `failed` acima de N, custo LLM diário acima de teto, fila de triagem acumulando — pendente de o usuário definir canal de notificação (e-mail/webhook). | 2026-07-23 |
| Reporting PDF agendado | Relatório periódico do dashboard "AtlasFile — Operação" via plugin de reporting. | 2026-07-23 |

## E2E pendentes

| Item | O que é | Registrado em |
|---|---|---|
| Chat Kimi (Moonshot) completo | Integração validada até o erro de saldo; falta E2E de chat com tool-call quando a conta Moonshot tiver créditos. | v0.36.0 |

## Website

| Item | O que é | Registrado em |
|---|---|---|
| Eixo `doc_kind` no lead do catálogo | "classified by business domain and document type" está incompleto — existe o 3º eixo de formato (item 5 da auditoria). | 2026-07-23 |
| og:image no domínio próprio | Comentários `ABSOLUTE-URL: update on custom domain` a revisar quando o site migrar de GitHub Pages para domínio próprio (item 6 da auditoria). | 2026-07-23 |

## Decisões aguardando o usuário

| Item | O que é |
|---|---|
| `frontend/vite.e2e.config.ts` | Entrou no repo por acidente na v0.40.4 (era bancada temporária untracked de E2E) — remover do rastreamento (política de bancadas fora do repo público) ou adotar oficialmente. |

## Direção de arte / visual

| Item | O que é | Estado |
|---|---|---|
| Shader blackhole como **indicador de contexto do chat** | Item (a) restante do trio: buraco negro cresce com o % de contexto da sessão (análogo do MODE_TOKENS do shader original; o dado já existe no botão "Contexto da sessão"). **Restrição de design do usuário: não pode ficar muito pequeno** — presença visual desde o início (semente já legível), não um ícone tímido. Base pronta: `BlackholeGL` entregue na v0.34.0 (itens b — fundo do gate/wizard — e c — orb no ciclo do classificador — já em produção) | Aguardando plano com mockups (o `uIntensity` do componente já aceita o fill 0..1) |

## Como usar este arquivo

- Adicione itens SEMPRE com gatilho explícito — roadmap sem critério vira lista de desejos.
- Ao executar um item: plano próprio em `planos_concluidos/` ao concluir, e o item sai daqui com um ponteiro para o plano.
