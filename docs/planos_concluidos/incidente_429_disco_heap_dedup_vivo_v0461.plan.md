# Incidente 429 — disco cheio, heap saturado e dedup contra fantasma (v0.46.1)

**Concluído em 2026-07-25.** Origem: FALHA na ingestão reportada pelo usuário com
`TransportError(429, 'circu…')` truncado na UI. O diagnóstico passou por DUAS correções
públicas até ficar factual — registrado aqui inteiro como lição de método.

## Linha do tempo do diagnóstico (com os erros de método)

1. **Chute nº 1 (errado)**: "arquivo pesado" — inferido do NOME do arquivo; era um PNG de
   2MB. **Chute nº 2 (impreciso)**: "falha no bulk de embeddings" sem ler onde a exceção
   nascia. O usuário cobrou: "NUNCA CHUTE — diagnósticos SEMPRE FACTUAIS a partir do
   código vigente" (regra agora permanente na memória do assistente).
2. **Fatos then coletados**: erro completo do histórico (`ingest_history.json`) revelou
   **DOIS** 429 distintos: `circuit_breaking_exception` ([parent] 502.6mb > 486.3mb — heap
   512m saturado de fato, 72 trips) e `cluster_block_exception` ("disk usage exceeded
   flood-stage watermark, index has read-only-allow-delete block").
3. **Medições**: VM Docker a **97%** (2GB livres); índice `atlasfile_documents` com
   `read_only_allow_delete: true` ATIVO; 235 imagens Docker (5 em uso).
4. **Causa dominante**: disco (flood-stage) — bloqueava TODA escrita; heap era secundária.
   O usuário liberou 5GB (`docker image prune -a`) → bloco auto-liberado pelo watermark →
   escrita confirmada com write-test real (201). Build cache (~36GB) apontado para prune.

## Bugs derivados encontrados pelos testes do usuário

- **Dedup contra fantasma**: o 429 deixou uma meta órfã; o self-healing a moveu para
  `rejected/`; o dedup por SHA varria `rejected/` e devolvia o tombstone como "original"
  → re-drops viravam "DUP compliance" (doc vivo estava em TI), e até **arquivo deletado +
  reconciliado** re-dropava como DUP.

## Entregue

- `_find_original_in_triage`: só documento VIVO — `pending/` exige o arquivo na fila,
  `resolved/` exige `final_path` existente, `rejected/` nunca vale;
  `_find_original_in_search_index` confere existência do path (janela deleção→reconcile).
- `_os_write_with_retry` no indexador (index + 3 bulks): `circuit_breaking` → retry
  backoff 1s/2s (rajada do parent breaker dura o bulk vizinho); `cluster_block` →
  `IndexWriteBlockedError` legível, sem retry (disco cheio não melhora esperando).
- Heap 1g default parametrizável (`OPENSEARCH_JAVA_OPTS`), `.env.example` documentado.
- ROADMAP: monitor de disco/bloco no item de alerting.

## Testes

8 novos (liveness do dedup nos cenários exatos do usuário + 4 do retry diferenciado);
2 testes antigos reescritos porque **codificavam o próprio bug** (rejected como original;
meta órfã como original). Backend 660/660.
