# Plano de Teste E2E v0.20.0 — workflow com score por etapa

Roteiro **conciso e executável por agente** (curl + filesystem + browser) que valida o valor central do AtlasFile — *documento entra bagunçado, sai organizado, encontrável e conversável* — e **realimenta o classificador** com as correções da execução. Substitui o `plano_teste_e2e_v0.8.0.md` como roteiro ativo (baseline de UI: v2/0.19.0+; inclui embeddings, busca híbrida e chat com citações).

## Método de score

Cada etapa recebe **0, 1 ou 2**:

- **2** — critério objetivo pleno (comportamento e dado corretos)
- **1** — funciona com ressalva (ex.: rótulo parcial, fallback acionado)
- **0** — falha do critério

Score máximo **20** (9 etapas + evolução). Veredito: ≥ 17 saudável · 13–16 degradado (investigar antes de fechar release) · < 13 bloqueia.

## Preparação (uma vez por execução)

```bash
# Stack no ar + suites verdes (pré-condição, não pontua)
make docker-up && make test

# Projeto de teste dedicado e lote com GROUND TRUTH:
# copiar 6 documentos reais já classificados de projetos existentes —
# o caminho de origem 02_AREAS/{business_domain}/{document_type}/ É o rótulo esperado.
# Anotar num manifest: arquivo → bd_esperado/dt_esperado.
export $(grep PROJECTS_HOST_ROOT .env | xargs)
PROJ=e2e_v0200
curl -X POST "http://localhost:8000/api/projects/$PROJ/initialize?template=default"
# escolher 6 docs de ≥3 domínios distintos (mín. 1 PDF, 1 DOCX, 1 XLSX/PPTX):
find "$PROJECTS_HOST_ROOT"/taxonomia_e2e_v0*/02_AREAS -type f | shuf | head -20  # candidatos
cp <6 escolhidos> "$PROJECTS_HOST_ROOT/$PROJ/_INBOX_DROP/"
```

> Regra de ouro: nenhum arquivo sintético (.txt gerado) como evidência de classificação — só documentos reais.

## Etapas e critérios

| # | Etapa | Como executar | Critério de score |
|---|-------|---------------|-------------------|
| 1 | **Drop** | Arrastar 1 dos 6 pela UI (portal global) e conferir os demais via pasta; `GET /api/ingest/inbox/$PROJ` | **2**: portal mostra progresso e conclui; inbox lista todos os arquivos. **1**: upload ok mas sem feedback correto. **0**: arquivo não chega |
| 2 | **Dedup** | Após o primeiro scan, reenviar 1 arquivo idêntico e re-scanear | **2**: decisão `DUP` no histórico, nenhum doc novo no índice. **0**: duplicata reprocessada/duplicada |
| 3 | **Extração** | `GET /api/documents/{id}` de cada doc ingerido | **2**: todos com conteúdo não-vazio coerente com o arquivo (amostrar 2). **1**: 1 falha explicada no histórico. **0**: conteúdo vazio/lixo sem erro declarado |
| 4 | **Classificação** | `GET /api/ingest/history/$PROJ` → comparar `business_domain`/`document_type` de cada decisão com o manifest | **2**: ≥ 4/6 exact match (bd+dt). **1**: ≥ 4/6 acertam bd (dt divergente). **0**: abaixo |
| 5 | **Roteamento** | Conferir filesystem: alta confiança em `02_AREAS/{bd}/{dt}/` com nome canônico; baixa em `_TRIAGE_REVIEW/pending` + fila da UI | **2**: 100% dos arquivos no lugar correspondente à sua decisão. **0**: arquivo em local incoerente com a decisão |
| 6 | **Indexação** | `GET /api/documents?project_id=$PROJ` | **2**: todos os processados presentes com metadados (bd, dt, original_filename). **1**: presentes com metadado faltante. **0**: ausentes |
| 7 | **Embeddings** | `embedding_status` dos docs + contagem no `atlasfile_chunk_vectors` | **2**: 100% `ok` e chunks vetorizados. **1**: pendências marcadas mas ingestão não bloqueou. **0**: erro silencioso |
| 8 | **Busca** | 3 queries parafraseadas sobre o conteúdo real do lote (sem palavras exatas do texto), em `mode=lexical` vs `hybrid` | **2**: híbrida traz o doc esperado no top-3 em ≥ 2/3 queries e ≥ empata com lexical nas demais. **1**: híbrida = lexical. **0**: híbrida pior que lexical |
| 9 | **Chat** | 3 perguntas golden no Assistente: (a) quantitativa ("quantos docs por domínio?"), (b) de localização ("encontre <tema do lote>"), (c) de conteúdo ("o que diz <doc> sobre <ponto>?") | **2**: 3/3 usam a tool certa (bloco Ferramentas), citam `original_filename` correto com chip clicável funcionando, sem URL inventada. **1**: 2/3. **0**: ≤ 1/3 ou link fabricado |

## Etapa 10 — Evolução do classificador (o teste vira treino)

O objetivo é fechar o loop: **as interações do teste melhoram o produto**.

```bash
# 1. Para cada item que caiu em triagem (etapa 5), decidir com o rótulo do manifest:
POST /api/triage/$PROJ/{doc_id}/decision   # approve/correct com bd/dt corretos
# 2. Registrar o tamanho do training pool antes/depois (a triagem deve crescê-lo).
# 3. Rodar o ciclo oficial:
POST /api/classifier/cycle                  # ou Config → Classificador → Rodar ciclo
# 4. Comparar o benchmark do campeão com o relatório anterior (Evolução recente).
```

**Score** — **2**: correções entraram no training pool, ciclo concluiu `succeeded` e o exact match do campeão **não regrediu** (≥ anterior − 1pt; melhorar conta como destaque). **1**: pool cresceu mas ciclo não rodou/skip. **0**: correções não viram treino ou benchmark regrediu além da tolerância.

> Se nenhum item cair em triagem na etapa 5, forçar 1: corrigir via triagem um doc auto-classificado com dt divergente do manifest (move para training pool igualmente). Sem divergência alguma: registrar N/A e pontuar pela execução do ciclo apenas.

## Scorecard (modelo de registro)

```
Data: ____  Executor: ____  Commit: ____
1 Drop __/2 · 2 Dedup __/2 · 3 Extração __/2 · 4 Classificação __/2 · 5 Roteamento __/2
6 Indexação __/2 · 7 Embeddings __/2 · 8 Busca __/2 · 9 Chat __/2 · 10 Evolução __/2
TOTAL __/20 → veredito: saudável ≥17 | degradado 13–16 | bloqueia <13
Observações por etapa com evidência (path/response/screenshot): ...
```

## Execução de referência — 2026-07-17 (executor: agente, commit 7f00698)

```
1 Drop 2/2 · 2 Dedup 2/2 · 3 Extração 2/2 · 4 Classificação 0/2 · 5 Roteamento 2/2
6 Indexação 2/2 · 7 Embeddings 2/2 · 8 Busca 2/2 · 9 Chat 2/2 · 10 Evolução 2/2
TOTAL 18/20 → saudável
```

Evidências e observações:

- **Lote**: 6 docs reais de 6 domínios/6 formatos, ground truth = rótulos curados do `taxonomia_e2e_v080`; projeto `e2e_v0200` mantido como fixture.
- **4 Classificação (0/2)**: 2/6 exact match, mas **5/6 acertaram o `document_type`** e 3 dos 4 misses de domínio coincidem com o rótulo de *outra versão curada* do mesmo corpus (v070/v071 ≠ v080 para o mesmo arquivo — ex.: Edital é `societario` no v070/v071 e `juridico` no v080). Ação: o ground truth herdado é inconsistente; consolidar rótulos-canônicos antes da próxima execução.
- **8 Busca (destaque)**: 3 queries parafraseadas — lexical **0/3** no top-3, híbrida **3/3 em #1**.
- **9 Chat**: 3/3 corretas (distribuição exata, arquivo certo nomeado, "competência 05/23" extraída do conteúdo); chip de citação abriu download real; zero URLs fabricadas.
- **10 Evolução**: pool 28→30 com as 2 decisões de triagem; ciclo `completed`; campeão manteve exact 82.3%. **Ressalva**: `bootstrap`/`sparse_logreg` estavam desabilitados no benchmark (só `llm` rodou) — habilitar os modos treináveis no próximo ciclo para as correções virarem modelo.
- Observabilidade: `embedding_status` não é exposto em `GET /api/documents` (verificação foi via índice `atlasfile_chunk_vectors`: 242 chunks/4 docs) — candidato a melhoria.

## Limpeza

- Excluir sessões de chat criadas pelo teste (via UI, histórico → excluir).
- O projeto `e2e_v0200` pode ser mantido como fixture de regressão (recomendado) ou removido do filesystem + `make reset-index` parcial via reconcile.
- **Não** remover as correções do training pool — elas são o ganho permanente da execução.
