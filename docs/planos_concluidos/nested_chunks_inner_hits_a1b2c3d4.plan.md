# Plano: Nested chunks + inner_hits (múltiplos pontos por documento)

Objetivo: na **busca completa**, retornar todos os pontos relevantes do documento (ex.: Planilha1 linha 12 e linha 13) usando nested + inner_hits, sem quebrar autocomplete nem índice existente.

---

## 1. Resumo das mudanças

| Arquivo | Alteração |
|---------|-----------|
| `document_extractor.py` | Adicionar `chunks: list[dict]` em `ExtractionResult` e preencher em todos os extractors |
| `opensearch_client.py` | Adicionar mapping `content_chunks` (nested) |
| `indexer.py` | Gravar `content_chunks` a partir de `chunks`; backfill para `extractor_version` 3 |
| `models.py` | Novos campos em `SearchHit`: `evidences`, `total_evidences`, `omitted_evidences` |
| `main.py` | Query: cláusula nested + inner_hits; resposta: popular `evidences` a partir de inner_hits |
| `reconcile.py` | Sem mudança de contrato; reindex continua usando `index_document` (já enriquecido) |
| `frontend/types.ts` | Tipos para `SearchHit.evidences`, etc. |
| `frontend/App.tsx` | Na lista de resultados completos, exibir múltiplas evidências por hit |

**Reindexação:** Sim. Após deploy, é necessário rodar **reconciliação completa** (ou backfill) para preencher `content_chunks` nos documentos já indexados. Docs novos passam a ter nested automaticamente.

---

## 2. Diffs por arquivo

### 2.1 `backend/app/document_extractor.py`

- Adicionar campo `chunks` em `ExtractionResult` (lista de `{ "location": str, "text": str }`).
- Helper para derivar texto puro a partir do formato `[location] text`.
- Em cada `_extract_*`, preencher `chunks` a partir dos mesmos `chunk_rows`; manter `chunk_text` e `chunk_locations` como hoje (retrocompatível).

```diff
--- a/backend/app/document_extractor.py
+++ b/backend/app/document_extractor.py
@@ -8,6 +8,7 @@ from typing import Any
 @dataclass
 class ExtractionResult:
     text_excerpt: str
     chunk_text: str
     chunk_locations: list[str]
+    chunks: list[dict[str, str]]  # [{"location": str, "text": str}]
     content_type: str
     extraction_status: str
     metadata: dict[str, Any]
@@ -33,6 +34,14 @@ def _format_chunks(tag: str, index: int, text: str) -> list[tuple[str, str]]:
     return out
 
 
+def _chunks_from_rows(chunk_rows: list[tuple[str, str]]) -> list[dict[str, str]]:
+    out: list[dict[str, str]] = []
+    for loc, raw in chunk_rows:
+        text = re.sub(r"^\[[^\]]+\]\s*", "", raw).strip() if raw else ""
+        if loc or text:
+            out.append({"location": loc, "text": text or raw})
+    return out
+
 def _extract_plain_text(path: Path, max_chars: int) -> ExtractionResult:
@@ -52,6 +61,7 @@ def _extract_plain_text(path: Path, max_chars: int) -> ExtractionResult:
         chunk_text="\n".join(chunk for _, chunk in chunks),
         chunk_locations=[loc for loc, _ in chunks],
+        chunks=_chunks_from_rows(chunks),
         content_type="plain_text",
```

Repetir o padrão em todos os `return ExtractionResult(...)`: adicionar `chunks=_chunks_from_rows(chunk_rows)` (ou `chunks` onde a variável for `chunks`). Nos casos que hoje usam `chunk_rows`, usar `_chunks_from_rows(chunk_rows)`; em plain_text e legacy onde se usa `chunks`, usar `_chunks_from_rows(chunks)`.

- PDF: após construir `chunk_rows`, adicionar `chunks=_chunks_from_rows(chunk_rows)`.
- DOCX: idem.
- XLSX: idem (já tem `chunk_rows`).
- PPTX: idem.
- Legacy: `chunks=_chunks_from_rows(chunks)`.
- Nos `return ExtractionResult` de erro/unsupported: `chunks=[]`.

---

### 2.2 `backend/app/opensearch_client.py`

Adicionar o mapping nested; não remover campos atuais.

```diff
--- a/backend/app/opensearch_client.py
+++ b/backend/app/opensearch_client.py
@@ -32,6 +32,7 @@ def ensure_index(client: OpenSearch) -> None:
         "content_chunks_text": {"type": "text"},
         "content_chunks_normalized": {"type": "text"},
         "chunk_locations": {"type": "keyword"},
+        "content_chunks": {
+            "type": "nested",
+            "properties": {
+                "location": {"type": "keyword"},
+                "text": {"type": "text"},
+                "text_normalized": {"type": "text"},
+            },
+        },
         "content_type": {"type": "keyword"},
```

Nota: em índices já existentes, `put_mapping` adiciona a propriedade; documentos antigos ficam sem `content_chunks` (ou array vazio) até reindex/backfill.

---

### 2.3 `backend/app/indexer.py`

- Em `_enrich_search_fields`, após obter `extracted` do `extract_document_content`:
  - Se `extracted.chunks` existir e não for vazio, montar `content_chunks = [ {"location": c["location"], "text": c["text"], "text_normalized": normalize_text(c["text"])} for c in extracted.chunks ]` e fazer `enriched["content_chunks"] = content_chunks`.
  - Manter `content_chunks_text` e `content_chunks_normalized` como hoje (para suggest e fallback).
- No backfill, considerar `extractor_version` "3" quando existir `content_chunks`; incluir `content_chunks` na lista de campos que disparam re-enriquecimento (e aumentar versão para "3" no metadata), para que após deploy o backfill preencha nested nos docs antigos.

```diff
--- a/backend/app/indexer.py
+++ b/backend/app/indexer.py
@@ -38,6 +38,7 @@ def _enrich_search_fields(payload: dict[str, Any]) -> dict[str, Any]:
     current_extractor_version = "2"
+    # "3" = nested content_chunks populated
     extraction_metadata["extractor_version"] = current_extractor_version
     if path_value:
@@ -51,6 +51,12 @@ def _enrich_search_fields(payload: dict[str, Any]) -> dict[str, Any]:
             extraction_metadata["extractor_version"] = current_extractor_version

     enriched["content"] = extracted_text
     enriched["content_chunks_text"] = chunk_text
     enriched["chunk_locations"] = chunk_locations
+    chunks_raw = getattr(extracted, "chunks", None) if path_value else None
+    if chunks_raw:
+        enriched["content_chunks"] = [
+            {"location": c["location"], "text": c["text"], "text_normalized": normalize_text(c.get("text", ""))}
+            for c in chunks_raw
+        ]
+    else:
+        enriched["content_chunks"] = []
     enriched["content_type"] = content_type
```

E no backfill, tratar versão 3: exigir que `content_chunks` exista e não esteja vazio quando há `content_chunks_text`; caso contrário, re-enriquecer. Usar `current_extractor_version = "3"` e na condição `needs_backfill` incluir `"content_chunks"` e versão != "3".

---

### 2.4 `backend/app/models.py`

```diff
--- a/backend/app/models.py
+++ b/backend/app/models.py
@@ -4,9 +4,15 @@ from pydantic import BaseModel, Field
 class SearchHit(BaseModel):
     doc_id: str
     project_id: str
     area_key: str
     original_filename: str
     canonical_filename: str
     path: str
     score: float
     highlights: list[str] = Field(default_factory=list)
     match_locations: list[str] = Field(default_factory=list)
+    evidences: list[dict[str, str]] = Field(default_factory=list)  # [{"location": str, "snippet": str}]
+    total_evidences: int = 0
+    omitted_evidences: int = 0
     content_type: str | None = None
```

---

### 2.5 `backend/app/main.py` (busca completa)

- Adicionar uma cláusula `should` com **nested** query em `content_chunks` (match_phrase em `content_chunks.text_normalized`, ou em `content_chunks.text`), com **inner_hits** nomeados (ex.: `"chunks"`), `size` limitado (ex.: 10), e `highlight` em `content_chunks.text` (fragment_size ~200).
- Ao montar cada `SearchHit`:
  - Se o hit tiver `inner_hits` e `inner_hits.chunks`, construir `evidences` a partir dos hits internos: para cada nested hit, `location = _source.location`, `snippet = highlight["content_chunks.text"][0] se existir, senão trecho de `_source.text`; `total_evidences` = total do inner_hits; `omitted_evidences` = max(0, total_evidences - len(evidences)).
  - Se não houver inner_hits, manter comportamento atual: `evidences` vazio ou derivado dos highlights atuais (um snippet por doc), `total_evidences`/`omitted_evidences` 0.

Exemplo de corpo de query (fragmento):

```python
# Na lista should, adicionar:
{
    "nested": {
        "path": "content_chunks",
        "query": {
            "bool": {
                "should": [
                    {"match_phrase": {"content_chunks.text_normalized": {"query": normalized_q, "slop": 0}}},
                    {"match_phrase": {"content_chunks.text": {"query": q, "slop": 2}}}
                ],
                "minimum_should_match": 1
            }
        },
        "inner_hits": {
            "name": "chunks",
            "size": 10,
            "highlight": {
                "fields": {"content_chunks.text": {"fragment_size": 220, "number_of_fragments": 1}},
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"]
            }
        }
    }
}
```

Na montagem do hit:

```python
evidences: list[dict[str, str]] = []
total_evidences = 0
omitted_evidences = 0
inner = h.get("inner_hits", {}).get("chunks", {})
if inner:
    ihits = inner.get("hits", {}).get("hits", [])
    total_evidences = inner.get("hits", {}).get("total", {}).get("value", len(ihits))
    for nh in ihits:
        loc = (nh.get("_source") or {}).get("location", "")
        hl = (nh.get("highlight") or {}).get("content_chunks.text")
        snippet = (hl[0] if hl else (nh.get("_source") or {}).get("text", "")[:220])
        evidences.append({"location": loc, "snippet": snippet})
    omitted_evidences = max(0, total_evidences - len(evidences))
# ... SearchHit(..., evidences=evidences, total_evidences=total_evidences, omitted_evidences=omitted_evidences)
```

- Autocomplete/suggest: não usar nested; manter como está (um item por documento, usando campos flat).

---

### 2.6 `frontend/src/types.ts`

```diff
 export interface SearchHit {
   ...
   match_locations: string[];
+  evidences?: { location: string; snippet: string }[];
+  total_evidences?: number;
+  omitted_evidences?: number;
   content_type?: string | null;
 }
```

---

### 2.7 `frontend/src/App.tsx` (resultados completos)

- Para cada hit, se `hit.evidences?.length > 0`, exibir uma lista de evidências (cada uma com `formatLocationLabel(evidence.location)` e snippet com `dangerouslySetInnerHTML` do snippet).
- Se houver `omitted_evidences > 0`, mostrar texto do tipo “+ N outros trechos”.
- Se não houver evidências, manter o bloco atual (highlights + match_locations).

Exemplo de estrutura:

```tsx
{hit.evidences && hit.evidences.length > 0 ? (
  <>
    {hit.evidences.map((ev, i) => (
      <div key={`ev-${hit.doc_id}-${i}`} className="evidence">
        <span className="evidence-location">{formatLocationLabel(ev.location)}</span>
        <div className="snippet" dangerouslySetInnerHTML={{ __html: ev.snippet }} />
      </div>
    ))}
    {hit.omitted_evidences > 0 && (
      <div className="sub">+ {hit.omitted_evidences} outro(s) trecho(s)</div>
    )}
  </>
) : (
  /* bloco atual com extractSnippets(hit.highlights) e topLocations */
)}
```

---

## 3. Ordem de aplicação (sem quebrar nada)

1. **document_extractor.py** – adicionar `chunks` e preencher em todos os retornos; manter `chunk_text`/`chunk_locations`.
2. **opensearch_client.py** – adicionar mapping `content_chunks` (nested).
3. **indexer.py** – gravar `content_chunks` a partir de `chunks`; backfill para versão 3.
4. **models.py** – novos campos em `SearchHit`.
5. **main.py** – nested + inner_hits na busca; preencher `evidences`, `total_evidences`, `omitted_evidences`.
6. **frontend types.ts** – tipos para evidências.
7. **frontend App.tsx** – UI de evidências na busca completa.

Depois do deploy: rodar **reconciliação completa** (ou backfill) para preencher `content_chunks` nos documentos já existentes. Até lá, documentos antigos continuam retornando via highlights flat; documentos novos já terão múltiplas evidências quando a query bater no nested.

---

## 4. Reindexação

- **Sim, é necessário reindexar** (ou rodar backfill que re-enriquece cada doc a partir do path) para que documentos já indexados passem a ter `content_chunks` preenchido e a busca completa retorne múltiplos pontos por documento.
- **Reconciliar todos os projetos** (botão “Reconciliar agora” com escopo “Todos os projetos”) faz rebuild completo do índice e chama `index_document` para cada linha do _INDEX, o que já usa `_enrich_search_fields` e passará a gravar `content_chunks`.
- Alternativa: manter índice e rodar apenas backfill (re-enriquecer todos os docs pelo path); isso exige que o backfill em `indexer.py` seja acionado (ex.: no startup ou por endpoint) e use `extractor_version` 3 para preencher nested.

---

## 5. Referências OpenSearch

- [Nested type](https://opensearch.org/docs/latest/field-types/supported-field-types/nested/)
- [Nested query](https://opensearch.org/docs/latest/query-dsl/joining/nested/)
- [Inner hits](https://opensearch.org/docs/latest/query-dsl/joining/nested/#inner-hits)
