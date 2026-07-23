# Plano de teste E2E — AtlasFile v0.36.x (instância zerada, com autenticação)

> Roteiro canônico de regressão fim-a-fim. Cada estágio vale 1 ponto (total **34**).
> Pré-requisitos:
> - 6 arquivos reais — **4 do mesmo tipo/área** (ex.: 4 contratos jurídicos) + **2 planilhas
>   XLSX** com colunas categóricas (ex.: CMDB e status de contratos).
> - **Ollama instalado no host** com um modelo baixado (`ollama pull gemma4:12b`) — Fase I.
> - **Chave Moonshot** (com saldo, se quiser o chat completo; sem saldo o estágio 32 valida
>   a integração pelo erro legível do provedor) — Fase I.
> - Numa máquina que também roda o repo dev: parar a dev antes (`docker compose down`)
>   e usar `--dir` com nome distinto (o guard barra se esquecer).
>
> **Para testar um branch antes do merge** (ex.: este v0.36.0): o clone lê commits, então
> o branch precisa estar commitado; instale do checkout local:
> ```bash
> curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- \
>   --dir ~/AtlasFileNovo --enable-auth \
>   --repo-url ~/Development/AtlasFile --branch feature/llm-providers-responses-v0360
> ```
>
> Novidades da 0.36.0 refletidas aqui (**Fase I**, nova): modelos OpenAI pós-gpt-5.2
> (exclusive — 5.3+) via **Responses API** (fix do 400 tools+reasoning), providers
> **Moonshot (Kimi)** e **Ollama local**, **validação automática de chaves** no modal,
> modelos custom no seletor do chat, erro dedicado `LLM_MODEL_NEEDS_RESPONSES_API`
> (coberto por teste de integração) e **snapshot LiteLLM embarcado**: instância nova já
> nasce com o catálogo completo (~68 modelos, incl. `Kimi K3` mantido em seção do
> usuário com preços reais) + refresh automático em background no primeiro boot.

## Fase A — Instalação e acesso (4 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 1 | Instalador com auth | `curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh \| bash -s -- --dir ~/AtlasFileNovo --enable-auth` (ou a variante `--repo-url/--branch` acima) | Sobe em <60s (cache quente); prompt da pasta funciona; **API key exibida ao final** |
| 2 | AuthGate primeiro | Abrir `localhost:5173` em **janela anônima** | Gate assume a tela pedindo a key; key errada → erro; key certa → entra. **Alternador de idioma visível no rodapé do card** |
| 3 | Onboarding | Após o gate | Wizard abre sozinho (backend zerado); passo 1 mostra a **pasta física** escolhida (não `/projects`); criar projeto + key OpenAI. Key digitada mostra ✓/✗ **sem travar o avançar** (testar uma key errada antes da certa); com key ✓, o final confirma "Classificação LLM ativada (tag_only)" e a primeira ingestão já traz linha `llm:` nos detalhes. Alternador de idioma no rodapé do wizard |
| 4 | Auth na API | `curl localhost:8000/api/projects` sem/com `Authorization: Bearer` | 401 sem key; 200 com; `/health` público. Erro 401/403 do detail vem como `{code, params, message}` |

## Fase B — Ingestão e triagem (6 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 5 | Portal global | Arrastar os 6 arquivos de uma vez em qualquer tela | Fila com progresso por arquivo; scan automático ao final |
| 6 | Fila da INBOX visível | Deixar 1 arquivo sem processar (ou colocar via filesystem) e abrir o Painel | Chips "Na fila da INBOX" com remoção pelo × |
| 7 | Triagem + criação de tipo | Num item de triagem, "Aprovar com correção" → "+ Criar novo tipo ou domínio" | Tipo criado, catálogo recarrega com ele **pré-selecionado**, aprovação conclui |
| 8 | Painel auto-atualiza | Aprovar/corrigir itens | Stats do painel refletem **sem F5** |
| 9 | Hold-out semente | Após 2+ decisões humanas, abrir **Classificador (sidebar)** | `validação rotulada ≥ 1` (a partir da 2ª decisão, uma vai para validação) |
| 10 | Autos fora dos datasets | Comparar nº de decisões humanas vs registros (treino+validação) | Docs auto-roteados não geram registros |

## Fase C — Ciclo do classificador (3 pts) — tela Classificador (sidebar)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 11 | Auto-cura | Se validação 0 com pool ≥2: botão Rodar ciclo HABILITADO com nota "reservará automaticamente" | Clique reserva sozinho e roda (mensagem de N documentos reservados automaticamente) |
| 12 | Benchmark LLM com key do navegador | Checkbox `llm` marcado + key OpenAI configurada → Rodar ciclo | `llm` com score real (sem skip); campeão eleito |
| 13 | Skip explicado | Observar linha `sparse_logreg` | "skip — treino insuficiente" (motivo legível, nunca skip mudo); "Último ciclo" traduzido (concluído/falhou), nunca código cru |

## Fase D — Busca e chat (5 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 14 | Busca lexical + híbrida | ⌘K: termo exato e uma paráfrase | Exato acha; paráfrase acha via híbrida (embeddings ativos). Grupo Navegação da paleta lista **Painel/Assistente/Classificador/Configuração** |
| 15 | Chat com citações | Pergunta sobre um documento | Resposta com citação clicável abrindo o arquivo |
| 16 | Tools de planilha | "Tabela de contagem por <colunaA> e <colunaB> da <planilha>, dados exatos" | Ferramentas `spreadsheet_schema`→`spreadsheet_query`; tabela renderizada; 2–3 células conferidas contra o Excel |
| 17 | Linha de Total | Observar a tabela do estágio 16 | Última linha **Total** em negrito (só somas que fazem sentido) |
| 18 | Gráfico 3 dimensões | "Gráfico de quantidades por domínio por tipo por formato" | **`bubble`** (default): x=domínio, y=tipo, cor=formato, tamanho=quantidade; facets/heatmap só se pedir por painel |

## Fase E — Catálogo de modelos (3 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 19 | Combobox próprio | Focar o campo de modelo (Firefox incluso) | Lista estilizada nossa (filtro, ↑↓/Enter) — nunca "Manage Passwords" |
| 20 | Validação de modelo custom | Digitar modelo inventado → Validar; digitar um real | Inventado: erro do provedor; real: ✓ e utilizável. Hint de **prefixo explícito** (`moonshot/…`, `ollama/…`) aparece para modelo fora do catálogo |
| 21 | Aba Catálogo | "Catálogo de modelos": Testar fonte, Atualizar agora | **~68 modelos** com preços/contexto/origem (inclui **Moonshot**, nomes SEM prefixo duplicado tipo `moonshot/moonshot/...`); "Atualizar agora" atualiza a data (a lista já veio completa do snapshot embarcado + refresh do 1º boot) |

## Fase F — Governança de taxonomia (3 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 22 | Migração dry-run + apply | Configuração → Templates → "Migrar / remover": criar tipo novo, migrar um tipo com docs | Simulação com contagens exatas; apply move arquivo físico + índice + datasets; origem vira alias; **pasta vazia da origem removida** |
| 23 | Remoção guardada | Tentar remover tipo com uso ativo; depois um vazio | Com uso: recusa com contagens; vazio: remove |
| 24 | Bootstrap reconhece alias | Ingerir doc com termos do tipo antigo migrado | Classifica no tipo NOVO (via alias herdado) |

## Fase G — Rejeitados e concorrência (3 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 25 | Seção Rejeitados | Rejeitar um doc na triagem | Card "Rejeitados (N)" aparece no Painel **sem reload**; expandir mostra arquivo, **motivo traduzido** e data |
| 26 | Restaurar e excluir | "Restaurar" o rejeitado; rejeitar de novo; "Excluir" (confirma popover) | Restaurar devolve à fila de triagem na hora; excluir apaga arquivo + registro; órfão (sem arquivo) só oferece Excluir |
| 27 | Duplo-clique seguro | Clicar 2x rápido em Aprovar (ou 2 abas na mesma decisão) | Uma só decisão processa; a 2ª recebe 409 com `code` estável; **nunca** aparece registro órfão fantasma em rejeitados |

## Fase I — Providers LLM e Responses API (6 pts) — NOVA na 0.36.0

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 28 | Catálogo de fábrica (snapshot embarcado) | Instância recém-instalada, **sem clicar em nada** na aba Catálogo | Seletor do chat já lista **~68 modelos** (não 6!), incluindo `Moonshot Kimi K3`; aba Catálogo mostra o K3 com **$3.00 / $15.00** (cache $0.30) e a data de atualização preenchida sozinha (refresh automático do primeiro boot). O code `LLM_MODEL_NEEDS_RESPONSES_API` (catálogo desatualizado) é coberto por teste de integração |
| 29 | Responses API (pós-5.2 exclusive) | Selecionar `gpt-5.6` no seletor do chat → Brain (thinking) ligado → pergunta que dispara busca | Responde normalmente **com tool calls** (Tools used lista `search_documents` etc.) — era o cenário do 400 "use /v1/responses". `gpt-5.2` (inclusive) permanece no caminho clássico |
| 30 | Regressão OpenAI clássico | Mesma pergunta com `gpt-4o-mini` e `gpt-5.1` | Respondem como antes (caminho chat/completions intocado) |
| 31 | Validação de chave no modal | Configurações do assistente: apagar e redigitar a key OpenAI errada; depois a certa | Badge automático ~700ms após parar de digitar: **✗ inválida** (errada) → **✓ válida** (certa); nada bloqueia o modal; com o backend fora do ar, o badge diz "não foi possível verificar" (≠ inválida) |
| 32 | Moonshot Kimi K3 | Selecionar `moonshot/kimi-k3` (já na lista, sem digitar) → campo **Moonshot API Key** aparece no modal → colar a chave | Badge ✓ ao vivo; chat com o K3 responde (com saldo) — sem saldo, o erro do provedor aparece **legível** no chat (integração validada: auth + base_url ok). Uso registra custo com os preços do K3 |
| 33 | Ollama local | Com `ollama serve` rodando no host e `gemma4:12b` baixado: combobox custom `ollama/gemma4:12b` → Validar | ✓ "disponível na Ollama" + hint "**roda localmente — não precisa de chave**" (sem campo de chave); o modelo **aparece no seletor do chat** (custom) e a conversa responde com o modelo local. No Docker o default `host.docker.internal:11434` já funciona sem configurar nada |

## Fase J — Resiliência da raiz de projetos (1 pt) — NOVA na 0.38.0

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 34 | Perda e recuperação da pasta de projetos | Com o stack no ar: `rm -rf` da pasta de projetos do host → aguardar ≤20s → recriar a pasta → `docker compose down && docker compose up -d` → completar o wizard → Reconcile INDEX | Banner claro "Pasta de projetos inacessível" (**nunca** "NetworkError" mudo); wizard NÃO abre com a raiz quebrada; após recriar+restart, wizard reabre COM o template default na lista; reconcile mostra órfãos removidos e os docs fantasmas somem do Dashboard |

## Fase H — Internacionalização (smoke, não pontuado)

| Item | Como testar | Passa se |
|------|-------------|----------|
| Auto-detect | Janela anônima com navegador em inglês | Gate/wizard/app sobem em EN-US sem configuração |
| Seletor | Configuração → Preferências → English (US) | Página recarrega inteira em EN (sidebar, paleta, tabelas, datas em formato US, moeda `$`) |
| Persistência | Reload + fechar/abrir o navegador | EN-US persiste; voltar a PT-BR funciona |
| Erro traduzido | Provocar um erro do backend (ex.: chat sem API key) em EN e em PT | Mensagem do catálogo do idioma ativo, nunca o `message` cru do backend. Inclui os codes novos (`LLM_MODEL_NEEDS_RESPONSES_API`, `MOONSHOT_*`, `OLLAMA_REQUEST_FAILED`) |
| Paridade | `npx vitest run src/i18n/parity.test.ts` | Verde (chaves e interpolações idênticas PT×EN) |

## Observação contínua (bônus, não pontuado)

- O **orb da sidebar não treme** com blips de rede; se a API cair, o app se recupera sozinho em ≤5s quando ela voltar.
- Custos: modelos sem preço na tabela aparecem com `cost_tracked=false` (custo 0 sinalizado), nunca um número inventado.

## Encerramento

```bash
cd ~/AtlasFileNovo && docker compose down -v   # volumes da instância de teste apenas
rm -rf ~/AtlasFileNovo <pasta-de-projetos-do-teste>
cd <repo-dev> && docker compose up -d
```

## Histórico de execuções

| Data | Versão | Score | Notas |
|------|--------|-------|-------|
| — | — | — | — |
