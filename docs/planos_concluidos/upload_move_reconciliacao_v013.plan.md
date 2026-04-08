# Plano: Upload de Arquivos via Frontend + Move de Documentos com Reconciliação

## Versão: 0.13.0

## Escopo

### Backend
- **`_relocate_document()`** — função extraída do triage para reuso pelo move (zero mudança funcional na triagem)
- **`POST /api/ingest/upload/{project_id}`** — upload multipart de múltiplos arquivos para `_INBOX_DROP/`
- **`GET /api/ingest/inbox/{project_id}`** — listar arquivos pendentes na inbox
- **`DELETE /api/ingest/upload/{project_id}/{filename}`** — deletar arquivo da inbox
- **`POST /api/documents/{project_id}/{doc_id}/move`** — mover documento entre business_domain/document_type com training pool
- **`DocumentMoveRequest`** model em `models.py`
- **`update_history_item()`** em `ingest_history.py` — atualiza bd/dt/decision no histórico de ingestão
- **Fix reconcile**: `sync_search_index_for_project` inclui `path` na comparação de skip incremental
- **Fix `build_corpus.py`**: `_load_existing_labels` usa último registro por SHA256 (não primeiro)
- Triage approve/correct/reject agora atualiza `ingest_history.json` via `update_history_item`

### Frontend
- **`FileUploadZone`** — drag-and-drop + file picker, lista de arquivos enviados com botão × para deletar, persiste estado carregando inbox do backend
- **`MoveDocumentModal`** — modal compartilhado com seletores de bd/dt, mensagem de erro inline
- **`IngestHistoryCard`** — tabela Processamentos extraída do IngestTriageCard, movida para o PainelView
- **`PainelView`** — extraído do App.tsx (~280 linhas), integra FileUploadZone + IngestHistoryCard + botão Mover nos resultados de busca
- **`api.ts`** — `uploadToInbox`, `deleteInboxFile`, `fetchInboxFiles`, `moveDocument`
- **`types.ts`** — `UploadResult`, `MoveResult`, `UploadedFile`
- Decisão `"moved"` exibida como badge azul na tabela Processamentos
- Botão mover habilitado para todas as decisões exceto DUP e error
- App.tsx simplificado (~280 linhas removidas)

### Testes
- Backend: +11 testes (upload, delete, move, build_corpus)
- Frontend: +15 testes (api, FileUploadZone, MoveDocumentModal)
