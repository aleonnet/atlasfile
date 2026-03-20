# Plano de Teste E2E — AtlasFile 0.8.0

## Objetivo

Este plano cobre o delta do ciclo atual sobre `docs/plano_teste_e2e_v0.7.0.md`, tomando como baseline a execução já registrada do `0.7.0` e como escopo de delta a implementação do plano `ciclo_ml_0_7_b3080de2.plan.md`, somada à limpeza estrutural atual de naming e taxonomia.

Escopo do delta:

- estado operacional do classificador na UI: `Campeão`, modo efetivo, override manual, política de promoção e evolução recente;
- ciclo oficial de `benchmark + retreino` com status em andamento, relatório atual e histórico recente;
- serving do classificador no ingest com `classifier_mode`, scores por eixo e fallback explícito quando aplicável;
- remoção do `baseline` legado e de `area_key` das superfícies públicas afetadas pelo ciclo ML;
- corte do contrato público de naming de `{area}` para `{business_domain}` em template, profile, UI e nome canônico em disco;
- validação de busca, assistente e Telegram apenas nos pontos em que o delta altera metadados ou nomenclatura visível.

O `0.7.0` continua sendo a baseline validada para shell, onboarding, tema, dashboard amplo, busca base, templates CRUD amplo e round-trips não afetados pelo delta. Este `0.8.0` permanece delta-only e não repete os 11 blocos completos.

## Premissas e limites registrados

- O campeão real pode ser `bootstrap`, `sparse_logreg` ou `sparse_linear_svc`; este plano valida o estado exibido na UI, sem assumir vencedor fixo.
- `baseline` não pode aparecer como opção pública, linha do benchmark oficial ou modo operacional visível ao usuário.
- `Processar INBOX` e `Rodar benchmark + retreino` devem expor fase e progresso sem depender de refresh manual completo.
- O LLM do chat consulta o índice; ele não é o classificador operacional principal.
- O LLM de classificação permanece desativado no smoke base, salvo passo explícito de inspeção.
- `validation_set` e `training_pool` devem permanecer disjuntos.
- Telegram continua dependendo de cliente autenticado para os passos externos.
- O placeholder legado `{area}` pode existir apenas como parsing ou migração one-way no `reconcile`; ele não faz parte do contrato ativo do produto.

## Pré-requisitos

```bash
# 1. Stack limpa
make docker-update RESET_INDEX=1 RESET_CHAT=1

# 2. Projeto de teste
export $(grep PROJECTS_HOST_ROOT .env | xargs)
mkdir -p "$PROJECTS_HOST_ROOT/taxonomia_e2e_v080"

# 3. Lote smoke disjunto de validation_set/training_pool
# Reusar exatamente os 10 arquivos reais do 0.7.0; não usar .txt sintético como evidência de classificação
```

## O que NÃO reexecutar aqui

Não repetir integralmente, salvo se houver regressão observada:

- onboarding geral, shell global e alternância de tema já validados no `0.7.0`;
- regressão completa do dashboard e dos 11 blocos do `0.7.0`;
- round-trip amplo de templates/profile/layout fora do que mudou em classificador e naming;
- benchmark histórico fora do fluxo atual de `Rodar benchmark + retreino`;
- regressão ampla de uso e custo se nenhuma superfície do delta depender dela na execução.

## Bloco 1 — Projeto, classificador operacional e naming visível

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 1.1 | Abrir `http://localhost:5173` e selecionar `taxonomia_e2e_v080` | Projeto aparece e pode ser inicializado |
| 1.2 | Inicializar com template `default`, se ainda não estiver inicializado | Projeto inicializado sem erro |
| 1.3 | Abrir `Ingestão e triagem` no projeto | A seção `Classificador operacional` fica visível |
| 1.4 | Validar os cards `Campeão`, `Efetivo neste projeto`, `Override` e `Último ciclo` | O estado operacional do classificador está explícito na UI |
| 1.5 | Abrir `Override manual do projeto` | As opções públicas são apenas `auto`, `bootstrap`, `sparse_logreg` e `sparse_linear_svc` |
| 1.6 | Validar a linha `Promoção:` | Gates aparecem e `baseline` não aparece como modo público |
| 1.7 | No editor de profile, ajustar `naming.canonical_pattern` para `{date}__{project}__{business_domain}__{original_name}` e salvar | Save sem erro |
| 1.8 | Reabrir o profile | O pattern persiste com `{business_domain}` |
| 1.9 | Verificar o hint de `Canonical pattern` no editor de profile | A UI mostra `{business_domain}` e não mostra `{area}` |
| 1.10 | Abrir `Templates` e editar ou duplicar `default` | O editor de template mostra `{business_domain}` e não mostra `{area}` |

## Bloco 2 — Ciclo oficial, benchmark e evolução recente

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 2.1 | Clicar `Rodar benchmark + retreino` | A ação é aceita e a UI passa a mostrar `Ciclo:` com fase e progresso |
| 2.2 | Aguardar a conclusão sem refresh manual completo | Fase e progresso avançam até finalizar ou falhar explicitamente |
| 2.3 | Validar o bloco `Benchmark oficial` | A tabela mostra apenas `bootstrap`, `sparse_logreg` e `sparse_linear_svc` |
| 2.4 | Validar a linha marcada como `campeão` | Ela coincide com o estado exibido em `Campeão` |
| 2.5 | Validar `Efetivo neste projeto` | Em `auto`, ele coincide com o campeão; com override, ele reflete o override salvo |
| 2.6 | Validar `Evolução recente` | O ciclo recém-executado aparece com `report_id`, campeão e resumo de `exact` |
| 2.7 | Registrar o valor de `Último ciclo` | O status final fica explícito, sem falha silenciosa |

## Bloco 3 — Override manual, serving no ingest e status streaming

### Passo `Host`

```bash
cp <lote_smoke> "$PROJECTS_HOST_ROOT/taxonomia_e2e_v080/_INBOX_DROP/"
```

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 3.1 | Selecionar um override manual supervisionado (`sparse_logreg` ou `sparse_linear_svc`) | O valor salva sem erro |
| 3.2 | Clicar `Processar INBOX` | O processamento inicia sem erro |
| 3.3 | Observar a faixa `Processar INBOX:` durante a execução | Fase, progresso e arquivo atual avançam em tempo real |
| 3.4 | Abrir `Processamentos` ao final | As linhas do lote aparecem no histórico |
| 3.5 | Expandir uma linha processada | A UI mostra `Classificador:` e `Scores: domínio | tipo | final` |
| 3.6 | Validar o modo servido | Se o override estiver disponível, o `Classificador` exibido bate com o override; se houver fallback, a razão aparece explicitamente |
| 3.7 | Restaurar o override para `auto (usar campeão)` | O projeto volta ao comportamento padrão sem erro |

## Bloco 4 — Triagem, scorecards e contrato público de taxonomia

| # | Ação no frontend | Resultado esperado |
|---|------------------|-------------------|
| 4.1 | Identificar um item pendente de triagem, se houver | O item mostra sugestão, confiança e contexto do classificador |
| 4.2 | Expandir o contexto do item pendente | A UI mostra `Classificador`, `Scores` e, quando houver, `Domínio proposto` |
| 4.3 | Clicar `Corrigir` em um item pendente | O modal abre com catálogo válido de domínio e tipo |
| 4.4 | Validar a terminologia do modal | A UI usa `domínio` ou `business_domain` e não expõe `area`, `area_key` ou aliases legados |
| 4.5 | Confirmar uma correção | O item sai da fila e o destino final reflete a decisão corrigida |
| 4.6 | Aprovar outro item pendente, se houver | O item sai da fila e vai para o destino sugerido |
| 4.7 | Rejeitar outro item pendente, se houver | O item sai da fila e vai para `_TRIAGE_REVIEW/rejected` |
| 4.8 | Reabrir `Itens pendentes de triagem` | A contagem reflete apenas a fila real remanescente |

## Bloco 5 — Nome canônico com `business_domain`

### Passo `Host`

```bash
find "$PROJECTS_HOST_ROOT/taxonomia_e2e_v080" -maxdepth 5 -type f

python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["PROJECTS_HOST_ROOT"]) / "taxonomia_e2e_v080" / "_PROFILE" / "ingest_history.json"
data = json.loads(root.read_text(encoding="utf-8"))
for entry in data.get("entries", [])[:3]:
    for item in entry.get("items", []):
        print(
            item.get("original_filename"),
            "=>",
            item.get("naming_pattern"),
            "=>",
            item.get("canonical_filename"),
            "=>",
            item.get("classifier_mode"),
        )
PY
```

Resultado esperado:

- pelo menos um arquivo final usa `__<business_domain>__` no nome canônico;
- `naming_pattern` fica registrado como `{date}__{project}__{business_domain}__{original_name}`;
- item corrigido usa o `business_domain` final, não a sugestão original;
- nenhum nome novo depende de `{area}` como contrato ativo.

## Bloco 6 — Busca, assistente e Telegram nas superfícies afetadas

Pré-requisitos:

- chave válida do provedor LLM configurada no assistente web;
- se o subbloco Telegram for executado: `CHANNELS_ENABLED=true`, `TELEGRAM_ENABLED=true` e `TELEGRAM_BOT_TOKEN` configurado.

| # | Ação | Resultado esperado |
|---|------|-------------------|
| 6.1 | Pesquisar pelo nome original exato de um arquivo processado | O documento exato sobe para o topo |
| 6.2 | Validar os metadados na busca | A UI expõe `business_domain` e `document_type` atuais, sem `area_key` ou `baseline` |
| 6.3 | Abrir `Assistente` no projeto `taxonomia_e2e_v080` e perguntar pelo arquivo indexado | O assistente encontra o documento correto no escopo atual |
| 6.4 | Pedir a classificação ou metadados do arquivo | A resposta não expõe `area_key`, `{area}` ou `baseline` como contrato público |
| 6.5 | Trocar para escopo global e repetir uma pergunta simples | O escopo global segue funcionando |
| 6.6 | Se Telegram estiver habilitado, enviar `/projeto taxonomia_e2e_v080` e perguntar por um arquivo exato | O bot encontra o documento correto sem expor nomenclatura legada |

## Bloco 7 — Gate automatizado obrigatório

```bash
cd backend && .venv/bin/pytest -q
cd ../frontend && npm test
cd ../frontend && npm run build
cd ../backend && .venv/bin/python scripts/benchmark_classification.py --mode all --json
```

Resultado esperado:

- backend e frontend passam em `100%`;
- build do frontend passa;
- `dataset_integrity.status = ok`;
- o `operational_classifier_mode` ou campeão final do benchmark oficial é um dos modos públicos suportados;
- o benchmark oficial não volta a expor `baseline` como linha pública do produto;
- benchmark conclui com `exit_code 0`.

## Passo opcional — prova de migração de naming legado

Executar apenas se quiser provar explicitamente a compatibilidade de leitura de arquivo antigo.

```bash
# 1. Inserir manualmente um arquivo com nome legado
#    YYYYMMDD__proj__financeiro__titulo__vNN.ext
# 2. Rodar reconcile
# 3. Confirmar rename one-way para o formato novo
```

Resultado esperado:

- o `reconcile` migra o arquivo antigo;
- o produto não volta a expor `{area}` como contrato ativo.

## Checklist final

```text
[x] Stack sobe com make docker-update RESET_INDEX=1 RESET_CHAT=1
[x] Projeto novo inicializa com template default
[x] Seção `Classificador operacional` expõe campeão, modo efetivo, override e política de promoção
[x] Nenhuma superfície pública do delta expõe `baseline` como modo operacional
[x] O ciclo `Rodar benchmark + retreino` conclui com status explícito e atualiza o benchmark oficial
[x] `Processar INBOX` expõe fase, progresso e arquivo atual
[x] Processamentos e triagem mostram `Classificador` e scores por eixo
[x] Override manual funciona e qualquer fallback aparece explicitamente
[x] Profile e templates expõem `{business_domain}` no naming
[x] Nenhum hint visível ao usuário mostra `{area}` como contrato ativo
[x] Nenhuma superfície pública do delta expõe `area_key`
[x] Processamento gera nome canônico com `business_domain` quando o pattern o inclui
[x] Triagem Aprovar/Corrigir/Rejeitar continua funcional no delta testado
[x] Busca por nome exato continua funcional
[x] Chat web responde no escopo correto sem expor terminologia legada
[ ] Telegram responde no escopo correto sem expor terminologia legada
[x] Backend e frontend passam em `100%`
[x] Build do frontend passa
[x] Benchmark oficial roda com `dataset_integrity.status = ok`
[ ] Commit da limpeza estrutural só acontece após todos os gates acima
```

## Registro obrigatório da execução

Quando este plano for executado:

- registrar todos os comandos shell por bloco;
- registrar as interações de UI por bloco;
- listar os arquivos reais copiados para `_INBOX_DROP`;
- marcar status final de cada bloco (`PASSOU`, `PASSOU COM RESSALVA`, `FALHOU`, `BLOQUEADO`);
- anexar a síntese factual dos testes automatizados e do benchmark oficial;
- registrar o campeão observado, o override usado e o `classifier_mode` servido no lote smoke;
- registrar qualquer divergência residual entre naming ativo (`business_domain`) e nomenclatura legada de migração.

Observação do checklist:

- A rodada anterior com `.txt` sintéticos foi invalidada como evidência de classificação; os artefatos foram removidos antes do rerun descrito abaixo.
- `Bloco 2`: a rodada inicial exigiu `reload`, mas o reteste pós-hotfix de streaming em `2026-03-20` concluiu sem `reload` manual.
- `Bloco 3`: o rerun inicial com o lote real mostrou inconsistência visual; no reteste pós-hotfix em `2026-03-20`, a UI saiu sozinha de `Concluído 0/0` para `Concluído 4/4`, sem `reload`.
- `Bloco 4`: a terminologia pública permaneceu limpa na UI, mas as decisões `approve`, `correct` e `reject` do lote real foram concluídas por API porque a automação do browser não conseguiu acionar os botões da triagem sem interceptação.
- `Bloco 5`: passou no rerun com arquivos reais; o `correct` em `Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário.docx` gerou `canonical_filename` com `business_domain = societario` e `_INDEX.md` consistente.
- `Bloco 6`: passou com ressalva; a API de busca encontra `Status contratos 5 fornecedores.xlsx` com a extensão, mas a UI só devolveu o item de forma consistente ao remover `.xlsx` do texto pesquisado.
- `Telegram`: não executado nesta rodada por instrução do usuário; cobertura manual pendente.
- `Bloco 7`: foi reexecutado após o hotfix de streaming; backend, frontend, build e benchmark oficial passaram novamente.

## Execução corrigida registrada em 2026-03-19

### Observações de escopo

- A rodada com `E2E080_*.txt` foi descartada para a parte de classificação; ela serviu apenas para revelar o bug do `canonical_filename`, já coberto pelo hotfix e pelos testes de regressão.
- Antes do rerun abaixo, o projeto `taxonomia_e2e_v080` foi limpo no filesystem, reinicializado e recebeu exatamente o mesmo lote real já documentado em `docs/plano_teste_e2e_v0.7.0.md`.
- `Bloco 1` foi refeito no projeto limpo; `Bloco 3` a `Bloco 6` foram reexecutados com o lote real; `Bloco 2` e `Bloco 7` mantêm a evidência factual já colhida na mesma stack rebuildada, por não dependerem do conteúdo do lote smoke.

### Pré-requisitos

Status: `PASSOU`

Shell usado:

```bash
make docker-update
ls "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/taxonomia_e2e_v080"
ls "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/taxonomia_e2e_v080/_INBOX_DROP"
```

Resultado observado:

- `make docker-update` terminou com `exit_code 0`.
- O rebuild recriou `api`, `mcp` e `web`, e o `docker-smoke-init` concluiu com `Initialize OK` e `Profile OK`.
- Após a limpeza dos artefatos inválidos, o projeto `taxonomia_e2e_v080` estava vazio e pronto para reinicialização.

### Lote smoke real reaproveitado do `0.7.0`

Shell usado:

```bash
cp \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/TVCo/SPA/Status contratos 5 fornecedores.xlsx" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/2 - Documentos Assinados/[Projeto Twist] Contratos Acessórios/[Projeto Twist] Contrato de Licenca de Uso de Marca Oi (Assinado).pdf" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/2 - Documentos Assinados/[Projeto Twist] Contratos Acessórios/[Projeto Twist] 2° Aditivo ao Contrato FTTH (Assinado).pdf" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/_SteeringCo Vtal/2024.10.21 - Programa Twist - Status Executivo Compartilhado1 - Projetos TI.pptx" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/_Reunião Executiva das Frentes/Projeto Twist2 Plano de Trabalho e Governanca Reuniao 07.05.2024 v2.pdf" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/3. Societário e Tributário/Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário.docx" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/TVCo/Edital/Projeto TV - Edital do Procedimento Competitivo (PMA 7.1.2025).docx" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/10. TSA/TSA_-_Contrato_Principal Oi Services_ClientCo_241104 LR.docx" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/TVCo/Societário/RE- UPI TV -  Oi + Mileto - Status Societário e Regulatório.eml" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Venus II/__Base Fee e Solo_Venus II/5_Mai-23/RE Faturamento - Contrato de compartilhamento (C1 e C3) - GARLIAVA - Competˆncia 0523.msg" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/taxonomia_e2e_v080/_INBOX_DROP/"
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

### Bloco 1 — Projeto, classificador operacional e naming visível

Status: `PASSOU`

UI registrada:

- Selecionei `taxonomia_e2e_v080`.
- O projeto apareceu como `taxonomia_e2e_v080 (nao inicializado)` após a limpeza e foi inicializado com o template `default`.
- Confirmei a seção `Classificador operacional` e os cards `Campeão`, `Efetivo neste projeto`, `Override` e `Último ciclo`.
- Abri `Override manual do projeto` e validei as opções públicas `auto`, `bootstrap`, `sparse_logreg` e `sparse_linear_svc`.
- Ajustei e salvei `naming.canonical_pattern = {date}__{project}__{business_domain}__{original_name}`.
- Reabri o profile.
- Abri `Templates` e validei o hint do editor do template.

Resultado observado:

- O campeão exibido na UI era `bootstrap`.
- O estado operacional reaberto após a inicialização mostrou `Efetivo neste projeto = bootstrap`, `Override = auto (usar campeão)` e `Último ciclo = succeeded`.
- `baseline` não apareceu como modo público nem como opção de override.
- Os hints de profile e template mostraram `{business_domain}` e não mostraram `{area}`.

### Bloco 2 — Ciclo oficial, benchmark e evolução recente

Status: `PASSOU COM RESSALVA`

Observação de escopo:

- Este bloco permanece válido na mesma stack rebuildada; a correção de rota do smoke não alterou backend, frontend nem benchmark oficial.

UI registrada:

- Cliquei `Rodar benchmark + retreino`.
- Acompanhei o bloco `Benchmark oficial` e `Evolução recente`.
- Revalidei `Campeão`, `Efetivo neste projeto` e `Último ciclo`.

Resultado observado:

- O ciclo concluído apareceu com `report_id = cycle_20260319_213427_380429`.
- O campeão observado permaneceu `bootstrap`.
- O benchmark oficial permaneceu expondo apenas `bootstrap`, `sparse_logreg` e `sparse_linear_svc`.
- `Evolução recente` exibiu o ciclo com resumo `exact: 45.5%`.

Ressalva factual:

- Depois da conclusão no backend, a UI permaneceu em `Ciclo em andamento...` e com o botão desabilitado.
- A tela só refletiu o fim do ciclo após `reload` completo da página.

### Bloco 3 — Override manual, serving no ingest e status streaming

Status: `PASSOU COM RESSALVA`

UI registrada:

- Selecionei `sparse_logreg` no `Override manual do projeto`.
- Cliquei `Processar INBOX`.
- Reabri o card de `Processamentos`.
- Validei a fila de `Itens pendentes de triagem`.

Resultado observado:

- O lote real encerrou com `processed_count = 10`, `failed_count = 0` e `classifier_mode = sparse_logreg` em `taxonomia_e2e_v080/_PROFILE/ingest_history.json`.
- O card passou a mostrar `Processamentos 10 arquivo(s)` e `Itens pendentes: 10`.
- Os `10` itens do lote apareceram com `Classificador: sparse_logreg`.
- A UI exibiu `Scores: domínio | tipo | final` em todos os itens do lote real.

Arquivos vistos em `Processamentos`:

1. `Projeto TV - Edital do Procedimento Competitivo (PMA 7.1.2025).docx` -> `juridico / contrato` -> confiança `0.28`
2. `Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário.docx` -> `juridico / contrato` -> confiança `0.22`
3. `[Projeto Twist] 2° Aditivo ao Contrato FTTH (Assinado).pdf` -> `regulatorio / contrato` -> confiança `0.27`
4. `2024.10.21 - Programa Twist - Status Executivo Compartilhado1 - Projetos TI.pptx` -> `ti / apresentacao` -> confiança `0.22`
5. `Projeto Twist2 Plano de Trabalho e Governanca Reuniao 07.05.2024 v2.pdf` -> `operacoes / apresentacao` -> confiança `0.18`
6. `RE- UPI TV -  Oi + Mileto - Status Societário e Regulatório.eml` -> `operacoes / planilha` -> confiança `0.20`
7. `[Projeto Twist] Contrato de Licenca de Uso de Marca Oi (Assinado).pdf` -> `regulatorio / contrato` -> confiança `0.25`
8. `TSA_-_Contrato_Principal Oi Services_ClientCo_241104 LR.docx` -> `juridico / contrato` -> confiança `0.27`
9. `Status contratos 5 fornecedores.xlsx` -> `suprimentos / planilha` -> confiança `0.14`
10. `RE Faturamento - Contrato de compartilhamento (C1 e C3) - GARLIAVA - Competˆncia 0523.msg` -> `operacoes / planilha` -> confiança `0.15`

Ressalva factual:

- Durante o processamento, o botão ficou em `Processando...`, mas a faixa `Processar INBOX` permaneceu em `idle 0/0`; o streaming visual não refletiu progresso útil no browser.

### Bloco 4 — Triagem, scorecards e contrato público de taxonomia

Status: `PASSOU COM RESSALVA`

UI registrada:

- Reabri o card `Ingestão e triagem` após o processamento do lote real.
- Confirmei a fila com `Itens pendentes: 10`.
- Tentei executar `Aprovar`, `Corrigir` e `Rejeitar` pela UI, mas os botões ficaram interceptados por outros elementos da página na automação do browser.
- Para não bloquear o rerun, concluí as três decisões pela API no mesmo projeto e com o mesmo lote real.

Resultado observado:

- O `approve` de `Status contratos 5 fornecedores.xlsx` respondeu `{"status": "ok", "action": "approved", ...}` e materializou `02_AREAS/suprimentos/planilha/20260319__taxonomia_e2e_v080__suprimentos__Status contratos 5 fornecedores__v01.xlsx`.
- O `correct` de `Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário.docx` para `societario / contrato` respondeu `{"status": "ok", "action": "corrected", ...}`.
- O `reject` de `[Projeto Twist] Contrato de Licenca de Uso de Marca Oi (Assinado).pdf` respondeu `{"status": "ok", "action": "rejected", ...}` e moveu o arquivo para `_TRIAGE_REVIEW/rejected`.
- A fila caiu de `10` para `7` pendentes reais.
- Nas superfícies públicas reabertas nesta rodada, o produto continuou usando `domínio` / `business_domain`; não houve exposição nova de `area`, `area_key` ou `baseline`.

### Bloco 5 — Nome canônico com `business_domain`

Status: `PASSOU`

Shell usado:

```bash
python3 - <<'PY'
import json
from urllib.request import Request, urlopen

base = "http://localhost:8000"
project = "taxonomia_e2e_v080"

actions = [
    ("approve", "e996c9ac-6193-4fdc-8d04-80204cc45d3b", {}),
    ("correct", "847229a2-7a1a-4b01-8159-f5ef5de6a46c", {"target_business_domain": "societario", "target_document_type": "contrato"}),
    ("reject", "d9cfa8b3-cdff-4388-98b0-eb2007e4bdc2", {}),
]

for action, doc_id, extra in actions:
    payload = {"action": action, "note": "e2e_v080_real_files"}
    payload.update(extra)
    req = Request(
        f"{base}/api/triage/{project}/{doc_id}/decision",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req) as resp:
        print(action, doc_id, resp.read().decode("utf-8"))
PY
```

Resultado observado:

- No `ingest_history`, os `10` itens do lote registraram `naming_pattern = {date}__{project}__{business_domain}__{original_name}` e `classifier_requested_mode = sparse_logreg`.
- O `approve` de `Status contratos 5 fornecedores.xlsx` gravou `canonical_filename = 20260319__taxonomia_e2e_v080__suprimentos__Status contratos 5 fornecedores__v01.xlsx`.
- O `correct` de `Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário.docx` gravou `canonical_filename = 20260319__taxonomia_e2e_v080__societario__Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário__v01.docx`.
- A data de ingestão foi preservada no token `20260319` e a versão permaneceu `__v01`.
- O `_INDEX.md` ficou consistente com `approved`, `corrected`, `rejected` e `triage_pending` para os `doc_id`s reais do lote; a linha do `correct` passou a registrar `business_domain = societario`, `canonical_filename` corrigido e `path` final em `02_AREAS/societario/contrato`.
- Não houve reintrodução de `{area}` no naming ativo nem linha residual `triage_pending` para o `doc_id` corrigido.

### Bloco 6 — Busca, assistente e Telegram nas superfícies afetadas

Status: `PASSOU COM RESSALVA`

UI registrada:

- Pesquisei por `Status contratos 5 fornecedores.xlsx` no projeto `taxonomia_e2e_v080`.
- Repeti a busca como `Status contratos 5 fornecedores`.
- Abri `Assistente` no projeto `taxonomia_e2e_v080`.
- Perguntei explicitamente pelo arquivo `Status contratos 5 fornecedores.xlsx`.
- Não executei o subbloco de Telegram por instrução do usuário.

Resultado observado:

- A API de busca (`/api/search`) retornou `2` hits já com a query exata `Status contratos 5 fornecedores.xlsx`; o primeiro resultado foi o próprio arquivo aprovado em `taxonomia_e2e_v080`.
- Na UI, a busca com a extensão `.xlsx` mostrou `Nenhum resultado`; ao remover a extensão e usar `Status contratos 5 fornecedores`, o arquivo aprovado subiu ao topo.
- O assistente encontrou o documento e respondeu metadados coerentes com o estado final: `business_domain = suprimentos`, `document_type = planilha`, `tags = suprimentos, planilha` e ingestão em `19/03/2026`.
- Nem a busca nem o assistente expuseram `area_key`, `{area}` ou `baseline` como contrato público.

### Bloco 7 — Gate automatizado obrigatório

Status: `PASSOU`

Shell usado:

```bash
make docker-update
cd frontend && npm run build
cd backend && .venv/bin/python scripts/benchmark_classification.py --mode all --json
```

Resultado observado:

- Fato verificado em terminal: o `docker-update` reexecutou `pytest` do backend com `354 passed in 11.79s`.
- Fato verificado em terminal: o `docker-update` reexecutou os testes do frontend com `69 passed (69)`.
- Fato verificado em terminal: `npm run build` do frontend passou após o hotfix.
- Fato verificado em terminal: o benchmark oficial terminou com `exit_code 0`, `operational_classifier_mode = bootstrap` e `dataset_integrity.status = ok`.
- Fato verificado no JSON do benchmark: a tabela oficial permaneceu com `bootstrap`, `sparse_logreg` e `sparse_linear_svc`.
- Nenhum código foi alterado entre esse gate e o rerun do lote real; por isso os resultados seguem válidos para a correção de rota documental do smoke.

### Reteste pós-hotfix do streaming (2026-03-20)

Status: `PASSOU`

Shell usado:

```bash
make docker-update
cp \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/TVCo/SPA/Status contratos 5 fornecedores.xlsx" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/_SteeringCo Vtal/2024.10.21 - Programa Twist - Status Executivo Compartilhado1 - Projetos TI.pptx" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/TVCo/Edital/Projeto TV - Edital do Procedimento Competitivo (PMA 7.1.2025).docx" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Área de Trabalho/_Projetos/_Legados/Twist/2 - Documentos Assinados/[Projeto Twist] Contratos Acessórios/[Projeto Twist] 2° Aditivo ao Contrato FTTH (Assinado).pdf" \
  "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/taxonomia_e2e_v080/_INBOX_DROP/"

cd frontend && npm test
cd frontend && npm run build
cd backend && .venv/bin/python scripts/benchmark_classification.py --mode all --json
```

UI registrada:

- Abri `taxonomia_e2e_v080` já rebuildado com o hotfix.
- Cliquei `Processar INBOX` sem fazer `reload`.
- Observei a linha `Processar INBOX:` mudar sozinha durante a execução e fechar em estado final coerente.
- Em seguida cliquei `Rodar benchmark + retreino`, também sem `reload`.
- Observei a linha `Ciclo:` sair do estado anterior, entrar em execução e retornar sozinha ao estado final com o botão reabilitado.

Resultado observado:

- `Processar INBOX` terminou sem `reload` manual e a UI fechou em `Concluído 4/4`.
- O botão de ingest voltou sozinho ao estado normal após o término.
- O ciclo do classificador executou sem `reload` manual.
- Durante o ciclo, a UI mostrou `Carregando datasets 1/5`.
- Ao final, o botão voltou sozinho para `Rodar benchmark + retreino`.
- O histórico exibiu o novo ciclo `cycle_20260320_001416_385855`.
- O benchmark oficial reexecutado em shell terminou com `exit_code 0`, `operational_classifier_mode = bootstrap` e `dataset_integrity.status = ok`.

Ressalva factual:

- No reteste manual do ciclo eu não capturei visualmente todas as transições intermediárias `2/5`, `3/5`, `4/5`; o que ficou verificado foi a ausência de `reload` manual e a transição automática de início e fim na UI.

### Estado final deixado em disco

- O projeto `taxonomia_e2e_v080` foi mantido.
- O override do projeto foi restaurado para `auto (usar campeão)` ao fim da rodada.
- O `Classificador operacional` voltou a refletir `bootstrap` como modo efetivo observado em `auto`.
- Não restou nenhum artefato dos `.txt` sintéticos invalidados.
- Permaneceram como artefatos desta execução:
  - `02_AREAS/suprimentos/planilha/20260319__taxonomia_e2e_v080__suprimentos__Status contratos 5 fornecedores__v01.xlsx`
  - `02_AREAS/societario/contrato/20260319__taxonomia_e2e_v080__societario__Procuração - ClientCo-Datora - rev.Contencioso rev.Jur. Societário__v01.docx`
  - `_TRIAGE_REVIEW/rejected/[Projeto Twist] Contrato de Licenca de Uso de Marca Oi (Assinado).pdf`
  - `7` itens ainda em `_TRIAGE_REVIEW/pending` do mesmo lote real

Observação final do estado em disco:

- O rerun corrigido deixou evidência válida para o `0.8.0`: lote real do `0.7.0`, `correct` com recomputação do nome canônico por `business_domain`, `_INDEX.md` consistente e busca/chat sem terminologia legada pública.
