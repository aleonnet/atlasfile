# Plano de Teste E2E — AtlasFile 0.7.0

## Objetivo

Validar o AtlasFile pelo frontend no estado real do produto:

- projeto novo com template `default`;
- layout `PARA` com `02_AREAS/{business_domain}/{document_type}`;
- ingestão por `_INBOX_DROP`;
- classificação operacional via `bootstrap`;
- triagem humana com `Aprovar`, `Corrigir` e `Rejeitar`;
- reconcile, busca, suggest e highlight no índice real;
- chat web com escopo por projeto e busca por nome exato;
- configuração de canais/Telegram, templates, profile/layout e uso/custo;
- benchmark oficial com `validation_set` e `training_pool` disjuntos.

## Regras deste plano

- O agente de teste deve operar pelo frontend sempre que existir superfície de UI.
- Passos marcados como `Host` exigem preparo fora do browser.
- `bootstrap` é o classificador operacional atual.
- `sparse_logreg` e `sparse_linear_svc` são candidatos de benchmark, não produção.
- O LLM do chat consulta o índice; ele não é o classificador principal.
- O LLM de classificação deve permanecer desativado no smoke base, salvo teste explícito do toggle.
- `validation_set` e `training_pool` devem permanecer disjuntos.

## Pré-requisitos

```bash
# 1. Stack limpo
make docker-update RESET_INDEX=1 RESET_CHAT=1

# 2. Projeto de teste
export $(grep PROJECTS_HOST_ROOT .env | xargs)
mkdir -p "$PROJECTS_HOST_ROOT/taxonomia_e2e_v070"

# 3. Lote de smoke disjunto de validation_set/training_pool
# Separar 10 arquivos reais e copiar depois para _INBOX_DROP
```

## Lote de smoke recomendado

Cobertura mínima:

- `contrato` de `ti`
- `aditivo` de `ti` ou `societario`
- `apresentacao` de `operacoes`
- `planilha` de `financeiro` ou `societario`
- `email` de `pessoas`, `ativos` ou `suprimentos`
- `relatorio`, `plano` ou `edital`
- pelo menos um arquivo ambíguo para cair em triagem

## Bloco 1 — Setup e shell

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 1.1 | Abrir `http://localhost:5173` | App carrega sem erro fatal |
| 1.2 | Ver seletor global de projetos | Projeto `taxonomia_e2e_v070` aparece como não inicializado até ser criado |
| 1.3 | Ver card `Controle operacional` | Métricas carregam sem erro; tabela de projetos mostra apenas projetos indexados |
| 1.4 | Abrir onboarding se exibido | Wizard abre sem quebrar a shell e pode ser fechado ou concluído |
| 1.5 | Alternar tema claro/escuro | Tema muda sem quebrar header, cards e modais |

## Bloco 2 — Projeto, template e profile

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 2.1 | Selecionar `taxonomia_e2e_v070` e inicializar com template `default` | Projeto inicializado sem erro |
| 2.2 | Abrir aba de profile/layout do projeto | Profile carrega com `project_id`, `paths`, `layout` e `classification` |
| 2.3 | Verificar `paths.inbox` | Valor é `_INBOX_DROP` |
| 2.4 | Verificar `classification.business_domains` | Catálogo presente e coerente com a taxonomia atual |
| 2.5 | Verificar `classification.document_types` | Catálogo presente e não vazio |
| 2.6 | Verificar layout de áreas | `areas_root` é `02_AREAS` e o destino deriva de `business_domain/document_type` |
| 2.7 | Abrir card de ingestão do projeto | Toggle de classificação LLM aparece e inicia desativado |

## Bloco 3 — Ingestão e triagem

### Passo `Host`

```bash
cp <lote_smoke> "$PROJECTS_HOST_ROOT/taxonomia_e2e_v070/_INBOX_DROP/"
```

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 3.1 | Clicar `Processar INBOX` | Processamento executa sem erro |
| 3.2 | Abrir `Processamentos` | Cada linha mostra arquivo, `business_domain / document_type`, decisão e confiança |
| 3.3 | Validar auto-route | Arquivos de alta confiança ficam com badge `auto` |
| 3.4 | Validar triagem | Arquivos ambíguos ficam com badge `triagem` e entram em `Itens pendentes de triagem` |
| 3.5 | Clicar `Aprovar` em um item pendente | Item sai da fila, é movido para o destino sugerido e deixa de aparecer como pendente |
| 3.6 | Clicar `Corrigir` em outro item | Modal abre com catálogos válidos de domínio e tipo; após confirmar, o item sai da fila e é movido para o novo destino |
| 3.7 | Clicar `Rejeitar` em um item pendente | Item sai da fila e vai para `_TRIAGE_REVIEW/rejected` |
| 3.8 | Reabrir o card após decisões | `Itens pendentes` reflete apenas a fila real, não o histórico resolvido |

## Bloco 4 — Histórico, reconcile e dashboard

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 4.1 | Recarregar a página com o mesmo projeto selecionado | Histórico do projeto continua visível |
| 4.2 | Ver `Processamentos` paginados | Histórico mostra apenas execuções já ocorridas, com paginação estável |
| 4.3 | Clicar `Reconciliar INDEX` | Reconcile termina sem erro fatal |
| 4.4 | Voltar ao `Controle operacional` | Contagem de docs e extensões do projeto aparece no índice |
| 4.5 | Ver mini-tabela de projetos | O projeto recém-indexado aparece com a contagem correta de docs |
| 4.6 | Ver footer de reconciliação | Última reconciliação e status ficam coerentes com a execução |

## Bloco 5 — Busca, suggest e highlight

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 5.1 | Abrir a busca global/modal e pesquisar um termo de conteúdo | Resultados retornam hits do projeto correto com highlights |
| 5.2 | Pesquisar pelo nome original exato de um arquivo | O documento exato sobe para o topo |
| 5.3 | Pesquisar por prefixo curto no suggest/autocomplete | Suggest retorna nomes coerentes com o índice |
| 5.4 | Filtrar pelo projeto selecionado | Resultados não misturam documentos de outros projetos |
| 5.5 | Validar `business_domain` e `document_type` nos resultados | Metadados exibidos batem com o índice atual |

## Bloco 6 — Assistente web

Pré-requisito: chave válida do provedor LLM configurada no modal do assistente.

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 6.1 | Abrir aba `Assistente` e criar nova conversa | Sessão nova criada sem erro |
| 6.2 | Com o projeto `taxonomia_e2e_v070` selecionado, perguntar `Quantos documentos temos neste projeto?` | Resposta reflete apenas o projeto atual |
| 6.3 | Perguntar `Liste os documentos deste projeto` | Resposta usa nomes originais e não mistura projetos |
| 6.4 | Perguntar por um nome de arquivo exato | Assistente encontra o documento correto quando ele existe no projeto |
| 6.5 | Trocar o seletor global para `Geral (todos os projetos)` e repetir a pergunta | Escopo passa a ser global |
| 6.6 | Voltar ao projeto e perguntar por um arquivo inexistente | Assistente responde que não encontrou evidência suficiente |

## Bloco 7 — Uso e custo

Pré-requisito: ter feito ao menos uma conversa com resposta do LLM.

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 7.1 | Abrir aba `Uso e custo` | Totais carregam sem erro |
| 7.2 | Ver tabela por modelo | Modelo usado na conversa aparece com tokens e custo |
| 7.3 | Ver tabela de sessões | Sessão criada no bloco 6 aparece listada |
| 7.4 | Aplicar filtro de período/projeto | Agregações permanecem coerentes |
| 7.5 | Voltar ao chat e observar pressão de contexto | Indicador de contexto renderiza sem quebrar a UI |

## Bloco 8 — Canais e Telegram

Pré-requisitos:

- `CHANNELS_ENABLED=true`
- `TELEGRAM_ENABLED=true`
- `TELEGRAM_BOT_TOKEN` configurado

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 8.1 | Abrir configurações do assistente | Seção de canais aparece |
| 8.2 | Ver status do Telegram | Backend expõe status sem erro |
| 8.3 | Salvar configuração de canal | Alteração persiste e a UI recarrega o status |
| 8.4 | Validar comando externo `/projeto taxonomia_e2e_v070` no Telegram | Chat do Telegram passa a consultar o projeto correto |
| 8.5 | Validar `/novo` no Telegram | Nova sessão é criada sem contaminar a sessão web anterior |

## Bloco 9 — Templates

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 9.1 | Abrir aba `Templates` | Template `default` aparece listado |
| 9.2 | Criar um template de usuário | Template novo aparece na lista |
| 9.3 | Editar `business_domains`, `document_types` e política LLM do template | Alterações salvam sem perder campos |
| 9.4 | Reabrir o template salvo | Round-trip preserva os dados |
| 9.5 | Excluir o template de usuário | Template some da lista |
| 9.6 | Tentar excluir o `default` | Operação é bloqueada |

## Bloco 10 — Profile e layout

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 10.1 | Abrir editor de profile do projeto | Formulário carrega com versão e histórico |
| 10.2 | Alterar campo simples e salvar | Versão incrementa |
| 10.3 | Abrir histórico do profile | Entrada nova aparece com timestamp |
| 10.4 | Gerar `Simular` do layout | Plano é gerado sem aplicar mudanças irreversíveis |
| 10.5 | Em projeto novo/vazio, aplicar o plano | Aplicação conclui sem erro e mantém o layout coerente |

## Bloco 11 — Complementos fora do frontend

Esses pontos continuam obrigatórios para aceite, mas não têm superfície completa na UI.

```bash
# Testes
cd backend && .venv/bin/pytest -q
cd ../frontend && npm test

# Benchmark oficial
cd ../backend
.venv/bin/python scripts/benchmark_classification.py --mode all --json
```

Resultado esperado:

- `validation_set` e `training_pool` sem sobreposição;
- `bootstrap` aparece como classificador operacional atual;
- `baseline`, `bootstrap` e candidatos `sparse_*` são medidos quando elegíveis;
- métricas por eixo incluem accuracy, macro-F1, recall por classe e matriz de confusão.

## Checklist final

```text
[x] Stack sobe com make docker-update RESET_INDEX=1 RESET_CHAT=1
[x] Projeto novo inicializa com template default
[x] Inbox operacional em _INBOX_DROP
[x] Classificação usa business_domain + document_type
[x] Triagem Aprovar/Corrigir/Rejeitar funciona
[x] Reconcile conclui sem erro
[x] Dashboard mostra métricas coerentes
[x] Busca, suggest e highlight funcionam no projeto correto
[x] Chat web respeita escopo por projeto e nome exato de arquivo
[x] Uso e custo registra a sessão de teste
[x] Configuração de canais/Telegram funciona end-to-end
[x] Templates e profile/layout fazem round-trip sem drift
[x] Backend e frontend passam nos testes automatizados
[x] Benchmark oficial roda com validation_set/training_pool disjuntos
```

Observação do checklist:

- `8.1-8.3` passaram na UI e no backend.
- `8.4-8.5` foram concluídos depois por validação manual externa em cliente Telegram autenticado, com confirmação por `curl` de status, sessão e usage.

## Execução realizada em 2026-03-18

### Pré-requisitos

Shell usado:

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
make docker-update RESET_INDEX=1 RESET_CHAT=1
curl -fsS http://localhost:8000/health && echo OK
ls "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects" && mkdir -p "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/taxonomia_e2e_v070"
```

Resultado:

- Stack rebuildada com sucesso.
- `docker-update` executou os testes do pipeline e recriou `opensearch`, `dashboards`, `api`, `mcp` e `web`.
- `curl /health` retornou `{"status":"ok"}`.
- O diretório do projeto `taxonomia_e2e_v070` foi criado antes da inicialização pelo frontend.

### Lote smoke usado

Shell usado:

```bash
python3 - <<'PY'
# enumerou candidatos reais disjuntos em PROJECTS_HOST_ROOT e _Projetos,
# excluindo validation_set, training_pool e lixo técnico
PY

python3 - <<'PY'
# copiou o lote curado para
# /Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/taxonomia_e2e_v070/_INBOX_DROP
PY
```

Arquivos copiados para `_INBOX_DROP`:

1. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/TVCo/SPA/Status contratos 5 fornecedores.xlsx`
2. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/2 - Documentos Assinados/[Projeto Twist] Contratos Acessórios/[Projeto Twist] Contrato de Licenca de Uso de Marca Oi (Assinado).pdf`
3. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/2 - Documentos Assinados/[Projeto Twist] Contratos Acessórios/[Projeto Twist] 2° Aditivo ao Contrato FTTH (Assinado).pdf`
4. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/_SteeringCo Vtal/2024.10.21 - Programa Twist - Status Executivo Compartilhado1 - Projetos TI.pptx`
5. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/_Reunião Executiva das Frentes/Projeto Twist2 Plano de Trabalho e Governanca Reuniao 07.05.2024 v2.pdf`
6. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/3. Societário e Tributário/Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário.docx`
7. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/TVCo/Edital/Projeto TV - Edital do Procedimento Competitivo (PMA 7.1.2025).docx`
8. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/10. TSA/TSA_-_Contrato_Principal Oi Services_ClientCo_241104 LR.docx`
9. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/TVCo/Societário/RE- UPI TV -  Oi + Mileto - Status Societário e Regulatório.eml`
10. `/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Venus II/__Base Fee e Solo_Venus II/5_Mai-23/RE Faturamento - Contrato de compartilhamento (C1 e C3) - GARLIAVA - Competˆncia 0523.msg`

### Bloco 1 — Setup e shell

Status: `PASSOU`

UI registrada:

- Abri `http://localhost:5173`.
- Confirmei o seletor global de projetos com `taxonomia_e2e_v070 (nao inicializado)`.
- Verifiquei `Controle operacional` sem erro fatal.
- Abri e fechei o onboarding.
- Alternei tema claro e escuro sem quebra visual.

### Bloco 2 — Projeto, template e profile

Status: `PASSOU`

UI registrada:

- Selecionei `taxonomia_e2e_v070`.
- O modal de inicialização abriu automaticamente.
- Inicializei com o template `default`.
- Confirmei `paths.inbox = _INBOX_DROP`.
- Confirmei `areas_root = 02_AREAS`.
- No editor de template, chequei 11 `business_domains` e 14 `document_types`.
- Voltei ao card de ingestão e confirmei o toggle de classificação LLM iniciando desativado.

Catálogo observado:

- `business_domains`: `societario`, `juridico`, `ativos`, `financeiro`, `fiscal`, `pessoas`, `ti`, `operacoes`, `regulatorio`, `compliance`, `suprimentos`
- `document_types`: `contrato`, `aditivo`, `fato_relevante`, `parecer`, `procuracao`, `ata`, `relatorio`, `especificacao`, `edital`, `plano`, `apresentacao`, `planilha`, `email`, `nota_fiscal`

### Bloco 3 — Ingestão e triagem

Status: `PASSOU`

UI registrada:

- Cliquei `Processar INBOX`.
- Abri `Processamentos`.
- Conferi 10 linhas com arquivo, domínio/tipo, decisão e confiança.
- Cliquei `Aprovar` em um pendente.
- Cliquei `Corrigir` em outro pendente e troquei `juridico / procuracao` para `societario / contrato`.
- Cliquei `Rejeitar` em outro pendente.
- Reabri o card e confirmei que a fila caiu de 6 para 3 pendentes reais.

Resultado observado por arquivo:

- `2024.10.21 - Programa Twist - Status Executivo Compartilhado1 - Projetos TI.pptx` → `financeiro / apresentacao` → `triagem` → pendente
- `[Projeto Twist] 2° Aditivo ao Contrato FTTH (Assinado).pdf` → `juridico / aditivo` → `triagem` → aprovado
- `[Projeto Twist] Contrato de Licenca de Uso de Marca Oi (Assinado).pdf` → `societario / contrato` → `triagem` → rejeitado
- `Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário.docx` → `juridico / procuracao` → `triagem` → corrigido para `societario / contrato`
- `Projeto TV - Edital do Procedimento Competitivo (PMA 7.1.2025).docx` → `societario / edital` → `auto`
- `Projeto Twist2 Plano de Trabalho e Governanca Reuniao 07.05.2024 v2.pdf` → `operacoes / contrato` → `auto`
- `RE Faturamento - Contrato de compartilhamento (C1 e C3) - GARLIAVA - Competˆncia 0523.msg` → `operacoes / email` → `triagem` → pendente
- `RE- UPI TV -  Oi + Mileto - Status Societário e Regulatório.eml` → `societario / email` → `auto`
- `Status contratos 5 fornecedores.xlsx` → `suprimentos / planilha` → `auto`
- `TSA_-_Contrato_Principal Oi Services_ClientCo_241104 LR.docx` → `societario / contrato` → `triagem` → pendente

### Bloco 4 — Histórico, reconcile e dashboard

Status: `PASSOU`

UI registrada:

- Recarreguei a página.
- Reselecionei `taxonomia_e2e_v070`.
- Confirmei o histórico de `Processamentos`.
- Cliquei `Reconciliar INDEX`.
- Voltei ao dashboard e conferi a mini-tabela de projetos e o rodapé de reconciliação.

Resultado observado:

- Reconcile concluído em `18/03/2026 17:56:42`.
- Resumo exibido: `Ajustes: 6`, `Reindexados: 2`, `Skip: 4`.
- Dashboard global exibiu `3 projetos inicializados` e `8 documentos indexados`.
- A mini-tabela mostrou `taxonomia_e2e_v070` com `6 docs`.

### Bloco 5 — Busca, suggest e highlight

Status: `PASSOU`

Shell de apoio usado:

```bash
python3 - <<'PY'
# GET /api/search?q=contrato&project_id=taxonomia_e2e_v070
# GET /api/search?q=twist&project_id=taxonomia_e2e_v070
# GET /api/search/suggest?q=con&project_id=taxonomia_e2e_v070
# GET /api/stats?project_id=taxonomia_e2e_v070
PY
```

UI registrada:

- Abri a busca global.
- Pesquisei `contrato`.
- Validei highlights e hits do projeto correto.
- Pesquisei pelo nome exato `Status contratos 5 fornecedores.xlsx`.
- Validei o suggest por prefixo curto.

Resultado observado:

- `contrato` retornou `6` hits na API e resultados coerentes na UI.
- O documento exato `Status contratos 5 fornecedores.xlsx` subiu ao topo.
- O suggest de `con` retornou nomes coerentes do índice.
- Os resultados respeitaram o projeto selecionado.
- Os metadados exibidos bateram com `business_domain` e `document_type` atuais.

### Bloco 6 — Assistente web

Status: `PASSOU`

UI registrada:

- Abri `Assistente`.
- Configurei a chave do provedor no modal do assistente.
- Criei uma nova sessão.
- Perguntei `Quantos documentos temos neste projeto?`.
- Perguntei `Liste os documentos deste projeto`.
- Testei nome exato primeiro com `TSA_-_Contrato_Principal Oi Services_ClientCo_241104 LR.docx` e depois com `Status contratos 5 fornecedores.xlsx`.
- Troquei o seletor global para `Geral (todos os projetos)` e repeti a consulta.
- Voltei ao projeto e perguntei por `Relatorio_Financeiro_2025.pdf`.

Resultado observado:

- Com o projeto selecionado, o assistente respondeu `6 documentos`.
- Em escopo global, respondeu `8 documentos`.
- O arquivo ainda em triagem (`TSA_-_Contrato_Principal...`) não foi encontrado, o que bateu com o estado do índice.
- O arquivo indexado `Status contratos 5 fornecedores.xlsx` foi encontrado corretamente.
- O arquivo inexistente `Relatorio_Financeiro_2025.pdf` retornou resposta de falta de evidência.

### Bloco 7 — Uso e custo

Status: `PASSOU`

UI registrada:

- Abri `Uso e custo`.
- Cliquei `Atualizar`.
- Conferi a tabela por modelo.
- Conferi a tabela de sessões.
- Alterei o filtro de projeto/período.
- Voltei ao chat para observar o indicador de contexto.

Resultado observado:

- Totais carregados sem erro.
- Totais exibidos na execução: `42k` tokens, custo estimado `US$ 0.00`, `2` sessões.
- Modelo listado: `openai/gpt-4o-mini`.
- As duas sessões de teste apareceram na grade.
- O indicador `Contexto: 0% utilizado` renderizou sem quebrar a UI.

### Bloco 8 — Canais e Telegram

Status: `PASSOU`

Shell de apoio usado:

```bash
python3 - <<'PY'
# leu TELEGRAM_BOT_TOKEN do .env
# chamou https://api.telegram.org/bot<TOKEN>/getMe
# chamou https://api.telegram.org/bot<TOKEN>/getUpdates
PY

curl -s http://localhost:8000/api/channels/status | jq
curl -s "http://localhost:8000/api/chat/sessions?channel=telegram" | jq '.[0] | {id, title, project_id, channel, channel_chat_id, updatedAt}'
curl -s "http://localhost:8000/api/usage/sessions?start_date=2026-03-01&end_date=2026-03-31&channel=telegram" | jq '.[0] | {id, title, project_id, channel, updatedAt}'
curl -s "http://localhost:8000/api/chat/sessions?channel=telegram" | jq 'map({id, project_id, channel, channel_chat_id, updatedAt})[:5]'
```

UI registrada:

- Abri `Configuração (modelo e API Key)`.
- Verifiquei a seção `Canais de comunicação`.
- Reabri o modal para validar persistência do status.

Browser extra usado:

- Abri `https://t.me/AtlasFileBot`.
- Tentei seguir para `https://web.telegram.org/`.

Validação manual externa posterior:

- No Telegram autenticado, enviei `/projeto taxonomia_e2e_v070`.
- Enviei `/projeto`.
- Perguntei `Quantos documentos temos neste projeto?`.
- Perguntei `Você encontra o arquivo "Status contratos 5 fornecedores.xlsx"?`.
- Perguntei `Liste os documentos deste projeto`.
- Enviei `/novo`.
- Enviei `/projeto`.
- Perguntei novamente `Quantos documentos temos neste projeto?`.
- Enviei `/projeto limpar`.
- Perguntei `Quantos documentos temos?`.

Resultado observado:

- `8.1 PASSOU`: seção de canais apareceu no modal.
- `8.2 PASSOU`: a UI exibiu Telegram como `Conectado`.
- `8.3 PASSOU`: o status persistiu ao fechar/reabrir o modal.
- `8.4 PASSOU`: `/projeto taxonomia_e2e_v070` respondeu `Projeto ativo definido para taxonomia_e2e_v070. Envie a próxima pergunta.`.
- `8.4 PASSOU`: `/projeto` respondeu `Projeto ativo: taxonomia_e2e_v070`.
- `8.4 PASSOU`: `Quantos documentos temos neste projeto?` respondeu `6 documentos`.
- `8.4 PASSOU`: `Você encontra o arquivo "Status contratos 5 fornecedores.xlsx"?` encontrou o arquivo correto com tipo `planilha` e área `suprimentos`.
- `8.4 PASSOU`: `Liste os documentos deste projeto` retornou a lista coerente dos `6` documentos do projeto.
- `8.5 PASSOU`: `/novo` respondeu `Nova sessão iniciada. Envie sua próxima pergunta.`.
- `8.5 PASSOU`: após `/novo`, `/projeto` ainda respondeu `Projeto ativo: taxonomia_e2e_v070`, confirmando que a nova sessão não limpou o escopo do projeto.
- `8.5 PASSOU`: após `/projeto limpar`, o bot respondeu `Escopo de projeto limpo. A próxima pergunta volta ao modo global.`.
- `8.5 PASSOU`: depois de limpar o escopo, `Quantos documentos temos?` respondeu `8 documentos no repositório`, coerente com modo global.
- No backend, `getMe` respondeu `200` para `@AtlasFileBot` e `getUpdates` veio vazio.
- `curl /api/channels/status` retornou `channels_enabled: true` e `telegram.running: true`, `telegram.connected: true`.
- `curl /api/chat/sessions?channel=telegram` retornou a sessão `3a92cfaa-c7b6-4377-ab92-5a025a2bcc5c` com `project_id: taxonomia_e2e_v070`, `channel: telegram` e `channel_chat_id: 8530811008`.
- `curl /api/usage/sessions?...&channel=telegram` confirmou a mesma sessão com `project_id: taxonomia_e2e_v070`.
- A lista posterior de sessões Telegram mostrou duas sessões distintas para o mesmo `channel_chat_id`: `3a92cfaa-c7b6-4377-ab92-5a025a2bcc5c` e `f2ea4ad5-8c7d-4a03-a4b7-91d80bb25869`.
- Isso confirma que `/novo` abriu uma nova sessão sem perder o escopo do projeto ativo.

### Bloco 9 — Templates

Status: `PASSOU COM RESSALVA`

UI registrada:

- Abri `Templates`.
- Confirmei o `default` listado.
- Dupliquei o `default`.
- Editei o template novo para `M&A / Carve-out E2E` com slug `ma_carveout_e2e`.
- Alterei a descrição.
- Editei `business_domains` adicionando `smoke_e2e` aos aliases de `societario`.
- Editei `document_types` adicionando `contrato_smoke` aos aliases de `contrato`.
- Salvei.
- Reabri o template e confirmei round-trip dos campos alterados.
- Excluí o template de usuário.
- Confirmei que o `default` não expôs ação de exclusão.

Ressalva factual:

- A superfície do editor não expôs uma seção visível/pesquisável de política LLM durante esta execução. Eu procurei na própria página por `LLM`, `classificação`, `provider`, `gpt-4.1` e `tag_only` e não houve match visível.
- Mesmo assim, o round-trip efetivo de `business_domains` e `document_types` passou sem drift.

### Bloco 10 — Profile e layout

Status: `PASSOU`

Shell usado:

```bash
ls "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects" && mkdir -p "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/taxonomia_layout_apply_v070"

python3 - <<'PY'
# conferiu em disco as pastas de
# /Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/taxonomia_layout_apply_v070/02_AREAS
PY
```

UI registrada:

- No projeto principal `taxonomia_e2e_v070`, abri o editor de profile.
- Alterei `Project label` para `taxonomia_e2e_v070 smoke`.
- Validei e salvei.
- Confirmei `Versão: 2`, `Última: frontend:profile-workspace` e `Histórico (2)`.
- Depois restaurei o `Project label` para `taxonomia_e2e_v070`.
- Criei o projeto auxiliar vazio `taxonomia_layout_apply_v070`.
- Inicializei esse projeto auxiliar com o `default`.
- No auxiliar, alterei a pasta de `suprimentos` para `suprimentos_layout`.
- Cliquei `Simular`.
- Conferi o preview de migração com `1` operação `rename`.
- Marquei a confirmação e cliquei `Aplicar migração`.

Resultado observado:

- `10.1 PASSOU`: editor abriu com versão e histórico.
- `10.2 PASSOU`: salvar alteração simples incrementou a versão.
- `10.3 PASSOU`: histórico passou a mostrar nova entrada.
- `10.4 PASSOU`: simulação gerou preview sem aplicar de imediato.
- `10.5 PASSOU`: aplicação foi feita no projeto vazio auxiliar e terminou com `Layout aplicado com sucesso`.
- A verificação em disco mostrou `02_AREAS/suprimentos_layout` no projeto auxiliar.

### Bloco 11 — Complementos fora do frontend

Status: `PASSOU`

Shell usado:

```bash
cd backend && .venv/bin/pytest -q
cd ../frontend && npm test
cd ../backend && .venv/bin/python scripts/benchmark_classification.py --mode all --json

python3 - <<'PY'
# extraiu do JSON do benchmark:
# operational_classifier_mode, dataset_integrity e sumário por benchmark
PY
```

Resultado observado:

- Backend: `378 passed in 12.92s`
- Frontend: `67 passed (67)` em `7` arquivos de teste
- `operational_classifier_mode`: `bootstrap`
- `dataset_integrity.status`: `ok`
- `validation_files`: `66`
- `training_records`: `100`
- `overlap_sha256`: `[]`

Síntese do benchmark oficial:

| modo | papel | business_domain_accuracy | business_domain_macro_f1 | document_type_accuracy | document_type_macro_f1 | exact_match_accuracy |
|---|---|---:|---:|---:|---:|---:|
| `baseline` | `legacy_reference` | 0.3636 | 0.3226 | 0.0000 | 0.0000 | 0.0000 |
| `bootstrap` | `operational_baseline` | 0.5000 | 0.4295 | 0.8485 | 0.6437 | 0.4545 |
| `sparse_logreg` | `benchmark_candidate` | 0.2576 | 0.2417 | 0.6667 | 0.2736 | 0.2121 |
| `sparse_linear_svc` | `benchmark_candidate` | 0.2879 | 0.2614 | 0.6515 | 0.2554 | 0.2273 |

Leitura factual:

- O benchmark rodou até o fim com `exit_code 0`.
- `bootstrap` permaneceu como baseline operacional e ficou acima de `baseline`, `sparse_logreg` e `sparse_linear_svc` nos três eixos principais de síntese mostrados acima.
- O JSON completo também trouxe recall por classe e matriz de confusão por eixo.
- Houve warnings de parser (`Ignoring wrong pointing object`, `openpyxl ... Conditional Formatting/Data Validation extension`) durante a leitura de arquivos, mas sem abortar a execução.

## Estado final deixado em disco

- `taxonomia_e2e_v070` foi mantido.
- `taxonomia_layout_apply_v070` foi criado e mantido como artefato do subteste seguro de layout.
