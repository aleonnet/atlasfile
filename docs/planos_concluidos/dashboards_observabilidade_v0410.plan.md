# dashboards_observabilidade_v0410 — dashboard "AtlasFile — Operação" auto-importado (v0.41.0)

Concluído em 2026-07-23. Atende ao pedido registrado no roadmap desde a discussão de observabilidade: "um dashboard atualizado completo para monitorar a operação, importado automaticamente desde o setup".

## Decisões de design

- **Conteúdo sobre os índices reais** (campos verificados por `_mapping` na instância viva): `atlasfile_documents` (time field `ingested_at`), `atlasfile_classification_usage` (`timestamp`), `atlasfile_chat_sessions` (`updatedAt`). Métricas de infraestrutura do cluster (JVM/CPU) ficaram FORA — não são consultáveis via saved objects; o caminho nativo do Dashboards cobre isso.
- **18 painéis em 4 linhas**: pulso (5 métricas: documentos, projetos, confiança média, custo LLM, sessões de chat); acervo (donuts domínio/doc_kind, barra de tipos, tabela por projeto com confiança média); fluxo e saúde (ingestão no tempo empilhada por decisão, pie de decisões, histograma de confiança 0.1, modo do classificador, saúde de extração e de embeddings); LLM e vocabulário (custo por dia × modelo, tabela de tokens/custo por modelo, tag cloud de tópicos).
- **Gerador determinístico** `backend/scripts/build_dashboards_ndjson.py`: única fonte da verdade; emite DOIS artefatos idênticos — `backend/app/data/dashboards.ndjson` (embarcado na imagem, fonte do auto-import) e `dashboards/atlasfile.ndjson` (import manual). Teste de sincronia falha se alguém editar o ndjson na mão.
- **Auto-import no boot** (`app/dashboards_setup.py`): thread daemon no lifespan; espera `GET /api/status` do Dashboards (que sobe mais devagar que a API), então `POST /api/saved_objects/_import?overwrite=true` com `osd-xsrf` e basic auth (`OPENSEARCH_USER/PASSWORD`); ids fixos tornam o import idempotente; ~30 tentativas × 5s; desistência é log de warning com instrução manual — startup NUNCA depende disso. Config: `DASHBOARDS_URL` (default `http://opensearch-dashboards:5601`), `DASHBOARDS_AUTO_IMPORT` (default true), propagadas no docker-compose.
- `overwrite=true` significa que personalizações do usuário nos NOSSOS objetos são sobrescritas a cada boot — documentado: para customizar, duplicar o dashboard ("Save as").

## Validação executada

- Import real na instância viva: **22/22 objetos** (3 index-patterns + 18 visualizações + 1 dashboard) — primeira tentativa.
- Caminho de código real: `import_dashboards_once()` executado do host contra `localhost:5601` → successCount 22.
- Prova visual: Playwright autenticado (cookie de sessão via arquivo — senha jamais em log/chat), screenshot full-page do dashboard renderizando com dados reais (7 docs no período, decisões 42% corrected, saúde ok/ok_ocr, tag cloud com os tópicos do acervo). Painéis de LLM exibem "No results found" com o índice de uso vazio — comportamento honesto até a primeira classificação LLM.
- 5 testes unit novos (`test_dashboards_setup.py`): integridade do ndjson (ids únicos, referências resolvem, dashboard cobre todas as visualizações), sincronia gerador↔artefatos, POST com headers/auth/params corretos, serviço fora do ar → None sem POST, retry desiste em silêncio e para no primeiro sucesso; toggle off → sem thread.

## Arquivos

`backend/scripts/build_dashboards_ndjson.py`, `backend/app/data/dashboards.ndjson`, `dashboards/atlasfile.ndjson` (substitui o conjunto mínimo antigo de 3 objetos com campo defasado `content_type`), `backend/app/dashboards_setup.py`, `backend/app/config.py`, `backend/app/main.py` (lifespan), `docker-compose.yml`, `backend/tests/unit/test_dashboards_setup.py`, READMEs + INSTALL.

## Limites conhecidos

- Painéis de custo LLM dependem do índice `atlasfile_classification_usage` (classificação LLM) — custo do CHAT vive em `usage_totals` das sessões (objeto aninhado, não agregável em visualização clássica); candidato a evolução: achatar custo de chat num índice de uso próprio.
- Performance de cluster (JVM/heap/latência) fora do escopo dos saved objects — usar o monitoramento nativo do OpenSearch.
