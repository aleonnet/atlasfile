# Workflow do documento — ponta a ponta

O caminho completo de um documento no AtlasFile, da chegada ao uso no chat, com o **ponto de observação** de cada etapa (UI, API, filesystem e índice). Para o roteiro de validação com score, ver [`plano_teste_e2e_v0.36.0.md`](plano_teste_e2e_v0.36.0.md).

```
arquivo → [1 drop] → _INBOX_DROP → [2 dedup SHA256] → [3 extração de texto]
  → [4 classificação bootstrap|sparse_logreg|llm] → [5 roteamento]
      ├─ confiança ≥ threshold → 02_AREAS/{business_domain}/{document_type}/ (nome canônico)
      └─ confiança < threshold → _TRIAGE_REVIEW/pending → triagem humana → training pool
  → [6 indexação OpenSearch] → [7 embeddings por chunk] → [8 busca lexical|híbrida|semântica]
  → [9 chat/RAG via MCP tools]
```

## 1. Drop (entrada)

| | |
|---|---|
| **Ação** | Arrastar arquivo em qualquer tela da UI (portal global) ou copiar para `$PROJECTS_HOST_ROOT/<projeto>/_INBOX_DROP/` |
| **O que acontece** | Portal: upload sequencial via `POST /api/ingest/upload/{project_id}` com progresso por arquivo; ao fim do lote, dispara 1 scan automaticamente. Pasta: o arquivo aguarda o próximo scan |
| **Observar** | Fila do portal (toasts com resultado por arquivo); `GET /api/ingest/inbox/{project_id}` lista o conteúdo da inbox antes do scan; orb da sidebar entra em estado *ingesting* durante a fila |

## 2. Ingestão + dedup

| | |
|---|---|
| **Ação** | Botão **Processar INBOX** (Painel ou Config → Classificador) ou `POST /api/ingest/scan/{project_id}` |
| **O que acontece** | Cada arquivo da inbox passa por hash SHA256; duplicata exata → decisão `duplicate` (nada é recriado); novo → segue o pipeline |
| **Observar** | `GET /api/ingest/status` (fase, progresso, arquivo atual; SSE em `/api/ingest/status/stream` — é o que a barra da UI consome); decisão `DUP` no histórico ao reenviar o mesmo arquivo |

## 3. Extração de texto

| | |
|---|---|
| **O que acontece** | `document_extractor.py` extrai texto de PDF (com OCR tesseract para escaneados), DOCX, XLSX, PPTX, MSG/EML, TXT |
| **Observar** | Conteúdo extraído: `GET /api/documents/{doc_id}` e `GET /api/documents/{doc_id}/chunks`; falha de extração aparece como `FALHA` com o motivo no histórico de processamentos |

## 4. Classificação

| | |
|---|---|
| **O que acontece** | O classificador **efetivo** do projeto (campeão global ou override) atribui `business_domain` + `document_type` + confiança. Modos: `bootstrap` (regras+aliases), `sparse_logreg` (TF-IDF+LogReg), `llm` (política por projeto). Opcional: enriquecimento LLM (tag_only/review/full_override) |
| **Observar** | Painel → **Processamentos**: linha por arquivo com domínio/tipo, decisão e confiança; clique expande o detalhe (modo usado, scores, contexto LLM). API: `GET /api/ingest/history/{project_id}`. Estado do classificador (campeão/efetivo/override/último ciclo): Config → Classificador ou `GET /api/classifier/status?project_id=...` |

## 5. Roteamento (auto vs triagem)

| | |
|---|---|
| **O que acontece** | Confiança ≥ threshold → arquivo movido para `02_AREAS/{business_domain}/{document_type}/` com **nome canônico**; abaixo → `_TRIAGE_REVIEW/pending` |
| **Observar** | Filesystem do projeto (o caminho canônico *é* o rótulo); fila **Triagem** na UI (aprovar/corrigir/rejeitar) ou `GET /api/triage/{project_id}`; decisões via `POST /api/triage/{project_id}/{doc_id}/decision` alimentam o **training pool** — é assim que o classificador aprende com o uso |

## 6. Indexação (OpenSearch)

| | |
|---|---|
| **O que acontece** | Documento indexado em `atlasfile_documents` (conteúdo + metadados + chunks aninhados), pesquisável imediatamente |
| **Observar** | `GET /api/documents?project_id=...`; rastreabilidade completa por doc: nome original → canônico → decisão → índice. Inspeção crua: Dashboards em `:5601` |

## 7. Embeddings por chunk

| | |
|---|---|
| **O que acontece** | Cada chunk vira vetor (OpenAI `text-embedding-3-small` 1536d ou fastembed local 384d) no índice separado `atlasfile_chunk_vectors`; incremental por SHA256+modelo; falha de embedding **nunca** bloqueia a ingestão (`embedding_status` marca pendências) |
| **Observar** | `embedding_status` no documento; contagem no índice de vetores (Dashboards); corpus legado: `backend/scripts/backfill_embeddings.py` (idempotente); custo rastreado em Uso e custo (script `embeddings_ingest`) |

## 8. Busca

| | |
|---|---|
| **O que acontece** | `GET /api/search?q=...&mode=lexical|hybrid|semantic` — híbrida (default) funde BM25 + kNN via RRF manual (k=60) com fallback automático para lexical se embeddings indisponíveis; rerank opcional por cross-encoder; nível chunk em `GET /api/search/chunks` |
| **Observar** | UI Painel: evidências com aura por match_type (laranja lexical, púrpura semântico). **Avaliação quantitativa**: `backend/scripts/benchmark_retrieval.py` roda o golden set e reporta recall@k/MRR por modo |

## 9. Chat / RAG

| | |
|---|---|
| **O que acontece** | O orchestrator conversa com o MCP server (tools `search_documents`, `list_documents`, `get_document_chunks`, `get_stats`...) e responde com evidências, citando `original_filename` |
| **Observar** | Bloco **Ferramentas usadas** sob a resposta (tool + preview do retorno); nomes de arquivo citados viram **chips clicáveis** que abrem o documento; custo por sessão/modelo em Uso e custo. Detalhe do fluxo agente↔tools: [`agent-tools-flow.md`](agent-tools-flow.md) |

## O ciclo de melhoria (o classificador evolui com o uso)

```
triagem humana (correções) → training pool → Rodar ciclo (benchmark + retreino)
  → promoção automática do campeão (gate: exact ≥ 80%) → ingestões seguintes classificam melhor
```

- Correções de triagem gravam exemplos rotulados no training pool (anti-leakage por SHA256 contra o validation set).
- **Rodar ciclo** (Config → Classificador ou `POST /api/classifier/cycle`) treina/benchmarka os modos habilitados e promove o melhor; relatórios ficam no registry e na tabela "Evolução recente".
- Datasets e splits: `_ATLASFILE/classifier/datasets/` (ver `10_classifier_design.md` e `11_scripts_and_operations.md`).
