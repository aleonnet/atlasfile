# Reconcile restaura os fatos do evento — fim do dashboard cego após rebuild (v0.50.5)

**Concluído em 2026-07-25.** Origem: pergunta do usuário — "por qual motivo o
dashboard está quase vazio, temos apenas Uso LLM por modelo, mesmo com a
conciliação e aparente reingestão de 108 documentos?".

## Diagnóstico (cadeia factual, medida no stack dev com 108 docs)

1. `_build_doc_payload` do reconcile **zerava as datas na mão**
   (`"ingested_at": None, "processed_at": None`). O index pattern do dashboard
   usa `ingested_at` como time field → **todo painel temporal cego**
   (medido: 0/108 docs com data). O único painel vivo — "Uso LLM por modelo" —
   lê outro índice, com timestamps próprios.
2. Mesmo padrão em `classifier_mode` (0/108) e `entities`: campos que o
   reconcile não deriva do disco e não repunha de lugar nenhum.
3. `embedding_status` 0/108 **apesar de 10k+ vetores presentes**:
   `index_document_chunks_embeddings` devolvia `up_to_date` sem gravar a flag.
   Como o delete do doc principal não apaga os vetores, todo doc reindexado
   perdia o status e nunca o recuperava.

Impacto de produto: quem reconstruísse o índice via reconcile — o fluxo de
recuperação que o próprio produto promove — ficava com o dashboard
permanentemente cego. Bug antigo, exposto agora porque foi a primeira vez que
um índice inteiro nasceu de reconcile.

## Decisões

- **O disco continua sendo a fonte da verdade** do que o layout expressa
  (`business_domain`, `document_type`, `path`, `sha256`): isso o reconcile
  deriva e deve seguir derivando. O que o rebuild perde são os **fatos do
  evento original** — e esses vivem em dois artefatos de filesystem que
  sobrevivem a qualquer perda de índice: `_PROFILE/ingest_history.json` e as
  metas de `_TRIAGE_REVIEW/resolved/*.json`.
- `_RESTORABLE_FIELDS = (ingested_at, processed_at, classifier_mode, entities)`
  com **merge por campo** (resolved primeiro, history por último — é o registro
  do evento e vence onde tem valor, sem apagar o que só a meta conhece).
  Terceira fonte só para data: prefixo `YYYYMMDD__` do nome canônico.
- **Nunca inventar**: doc sem nenhuma fonte fica com `None`/`[]` — a mesma
  régua de zero defaults arbitrários que vale no resto do projeto.
- **Backfill sem loop**: o caminho incremental reindexa quando um campo está
  ausente no índice E disponível na fonte. Detalhe que evita reescrever os
  mesmos docs em todo ciclo: os campos restauráveis entraram no `_source` do
  `client.get` do skip — sem isso pareceriam sempre ausentes (teste dedicado).
- `embedding_status` regravado no retorno `up_to_date` (idempotente; na
  ingestão normal esse ramo nem é atingido, pois doc novo nunca está em dia).

## Validações

- Backend **691/691** (novos: fatos do history, fatos do meta resolvido, merge
  campo a campo, "sem fonte não inventa", backfill dispara para doc sem data,
  guarda anti-loop com doc completo, embedding_status regravado em up_to_date,
  embeddings desligados não tocam o índice).
- Medições vivas no stack dev (108 docs): `ingested_at` 0 → **108/108**, com
  **83 na janela default de 30 dias** do dashboard (os 25 restantes são de
  março/abril — datas reais, corretamente fora da janela); `classifier_mode`
  0 → **73/108** (69 bootstrap + 4 sparse_logreg); `embedding_status` 0 →
  108/108 (76 no ciclo que reindexou + 32 repostos no skip).
- **Correção de uma projeção minha**: estimei "104/108 recuperáveis" contando
  doc_ids com `classifier_mode` nas fontes — mas esse conjunto não é o mesmo do
  índice (o history é FIFO de 50 entradas de scan e perde os ciclos antigos;
  parte dos doc_ids das fontes já nem está indexada). O número real medido é
  73/108; os demais não têm fonte e ficam honestamente vazios.
- Prova anti-loop ao vivo: segundo reconcile imediato → `indexed_docs` = 0 e
  `skipped_docs` = 108.

## Limitações honestas

- Doc sem nenhuma fonte (nome fora do padrão canônico **e** ausente do history
  e do resolved — ex.: colocado à mão em `02_AREAS`) segue sem data e sem modo.
- `ingest_history.json` é FIFO com cap de 50 **entradas de scan**: a cobertura
  decai com o tempo; as metas do `resolved` não têm cap.
- Chats e eventos de custo LLM continuam sem redundância fora do índice — item
  próprio no ROADMAP ("Durabilidade de chats e eventos de custo").
