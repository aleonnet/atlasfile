# Plano de teste E2E — AtlasFile v0.27.x (instância zerada, com autenticação)

> Roteiro canônico de regressão fim-a-fim. Cada estágio vale 1 ponto (total **27**).
> Pré-requisito: 6 arquivos reais — **4 do mesmo tipo/área** (ex.: 4 contratos jurídicos)
> + **2 planilhas XLSX** com colunas categóricas (ex.: CMDB e status de contratos).
> Numa máquina que também roda o repo dev: parar a dev antes (`docker compose down`)
> e usar `--dir` com nome distinto (o guard barra se esquecer).

## Fase A — Instalação e acesso (4 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 1 | Instalador com auth | `curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh \| bash -s -- --dir ~/AtlasFileNovo --enable-auth` | Sobe em <60s (cache quente); prompt da pasta funciona; **API key exibida ao final** |
| 2 | AuthGate primeiro | Abrir `localhost:5173` em **janela anônima** | Gate assume a tela pedindo a key; key errada → erro; key certa → entra |
| 3 | Onboarding | Após o gate | Wizard abre sozinho (backend zerado); passo 1 mostra a **pasta física** escolhida (não `/projects`); criar projeto + key OpenAI. Key digitada mostra ✓/✗ **sem travar o avançar** (testar uma key errada antes da certa); com key ✓, o final confirma "Classificação LLM ativada (tag_only)" e a primeira ingestão já traz linha `llm:` nos detalhes |
| 4 | Auth na API | `curl localhost:8000/api/projects` sem/com `Authorization: Bearer` | 401 sem key; 200 com; `/health` público |

## Fase B — Ingestão e triagem (6 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 5 | Portal global | Arrastar os 6 arquivos de uma vez em qualquer tela | Fila com progresso por arquivo; scan automático ao final |
| 6 | Fila da INBOX visível | Deixar 1 arquivo sem processar (ou colocar via filesystem) e abrir o Painel | Chips "Na fila da INBOX" com remoção pelo × |
| 7 | Triagem + criação de tipo | Num item de triagem, "Aprovar com correção" → "+ Criar novo tipo ou domínio" | Tipo criado, catálogo recarrega com ele **pré-selecionado**, aprovação conclui |
| 8 | Painel auto-atualiza | Aprovar/corrigir itens | Stats do painel refletem **sem F5** |
| 9 | Hold-out semente | Após 2+ decisões humanas, Configuração → Classificador | `validação rotulada ≥ 1` (a partir da 2ª decisão, uma vai para validação) |
| 10 | Autos fora dos datasets | Comparar nº de decisões humanas vs registros (treino+validação) | Docs auto-roteados não geram registros |

## Fase C — Ciclo do classificador (3 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 11 | Auto-cura | Se validação 0 com pool ≥2: botão Rodar ciclo HABILITADO com nota "reservará automaticamente" | Clique reserva sozinho e roda ("N reservado(s) automaticamente") |
| 12 | Benchmark LLM com key do navegador | Checkbox `llm` marcado + key OpenAI configurada → Rodar ciclo | `llm` com score real (sem skip); campeão eleito |
| 13 | Skip explicado | Observar linha `sparse_logreg` | "skip — treino insuficiente" (motivo legível, nunca skip mudo) |

## Fase D — Busca e chat (5 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 14 | Busca lexical + híbrida | ⌘K: termo exato e uma paráfrase | Exato acha; paráfrase acha via híbrida (embeddings ativos) |
| 15 | Chat com citações | Pergunta sobre um documento | Resposta com citação clicável abrindo o arquivo |
| 16 | Tools de planilha | "Tabela de contagem por <colunaA> e <colunaB> da <planilha>, dados exatos" | Ferramentas `spreadsheet_schema`→`spreadsheet_query`; tabela renderizada; 2–3 células conferidas contra o Excel |
| 17 | Linha de Total | Observar a tabela do estágio 16 | Última linha **Total** em negrito (só somas que fazem sentido) |
| 18 | Gráfico 3 dimensões | "Gráfico de quantidades por domínio por tipo por formato" | **`bubble`** (default): x=domínio, y=tipo, cor=formato, tamanho=quantidade; facets/heatmap só se pedir por painel |

## Fase E — Catálogo de modelos (3 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 19 | Combobox próprio | Focar o campo de modelo (Firefox incluso) | Lista estilizada nossa (filtro, ↑↓/Enter) — nunca "Manage Passwords" |
| 20 | Validação de modelo custom | Digitar modelo inventado → Validar; digitar um real | Inventado: erro do provedor; real: ✓ e utilizável |
| 21 | Aba Catálogo | "Catálogo de modelos": Testar fonte, Atualizar agora | ~46 modelos com preços/contexto/origem; refresh atualiza a data |

## Fase F — Governança de taxonomia (3 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 22 | Migração dry-run + apply | Templates → "Migrar / remover": criar tipo novo, migrar um tipo com docs | Simulação com contagens exatas; apply move arquivo físico + índice + datasets; origem vira alias; **pasta vazia da origem removida** |
| 23 | Remoção guardada | Tentar remover tipo com uso ativo; depois um vazio | Com uso: recusa com contagens; vazio: remove |
| 24 | Bootstrap reconhece alias | Ingerir doc com termos do tipo antigo migrado | Classifica no tipo NOVO (via alias herdado) |

## Fase G — Rejeitados e concorrência (3 pts)

| # | Estágio | Como testar | Passa se |
|---|---------|-------------|----------|
| 25 | Seção Rejeitados | Rejeitar um doc na triagem | Card "Rejeitados (N)" aparece no Painel **sem reload**; expandir mostra arquivo, motivo e data |
| 26 | Restaurar e excluir | "Restaurar" o rejeitado; rejeitar de novo; "Excluir" (confirma popover) | Restaurar devolve à fila de triagem na hora; excluir apaga arquivo + registro; órfão (sem arquivo) só oferece Excluir |
| 27 | Duplo-clique seguro | Clicar 2x rápido em Aprovar (ou 2 abas na mesma decisão) | Uma só decisão processa; a 2ª recebe 409; **nunca** aparece registro órfão fantasma em rejeitados |

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
