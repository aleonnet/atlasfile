# Journal local-first de chats e eventos de custo (v0.53.0)

**Concluído em 2026-07-25.** Origem: incidente real do mesmo dia — dois resets
de volume do OpenSearch levaram **todos** os chats e eventos de custo LLM do
período. Documentos, profiles, taxonomia e histórico de ingestão sobreviveram
porque moram no filesystem; esses eram os únicos dados sem origem fora do
índice, e a perda foi permanente.

## Decisões

- **Journal em `_ATLASFILE/journal/`** (a raiz global que já hospeda
  `classifier/`, `llm/` e `templates/`), não em cada projeto: chats e custos
  são transversais.
- **Eventos append-only** (`chat_usage`, `classification_usage`,
  `training_usage`): um NDJSON por tipo e por mês. Append é barato, resiste a
  queda no meio da escrita e é trivial de reler. Linha corrompida é pulada na
  leitura — um append interrompido não pode inutilizar o journal inteiro
  (teste cobre).
- **Sessões de chat** são mutáveis: em vez de event-sourcing, snapshot do
  documento inteiro por sessão (`journal/chat_sessions/<id>.json`), gravado
  com `os.replace` (atômico: leitor nunca vê arquivo pela metade). Nos updates
  o doc completo já está em memória, então não custa releitura do índice.
- **Exclusão respeitada**: apagar uma sessão remove o snapshot — senão a
  restauração ressuscitaria o que o usuário apagou de propósito.
- **Journal antes do índice**: o disco passa a ser a fonte durável e o índice,
  a projeção consultável. Falha de escrita no journal **nunca** derruba a
  operação (mesmo princípio do cache de excerpt).
- **Restauração no reconcile**, `only_if_empty=True`: age no cenário de perda
  (índice vazio) e **nunca** sobrescreve índice vivo. Id determinístico por
  sha256 do conteúdo canônico ⇒ reimportar não duplica.
- **Visível**: `journal_sessions_restored` / `journal_events_restored` entram
  no summary, contam como "correção" (o run automático anuncia quando corrige)
  e ganham segmento próprio no resumo, nos dois idiomas.
- **Snapshots nativos do OpenSearch rejeitados como solução primária**: exigem
  repositório configurado e política operacional — contrariam o local-first, e
  o journal cobre o caso real que aconteceu.

## Validações

- Backend **725/725** (8 testes novos: NDJSON por mês, tipo desconhecido,
  falha de escrita silenciosa, snapshot atômico + delete, linha corrompida,
  restauração de eventos e sessões, índice vivo nunca sobrescrito,
  idempotência do id).
- Frontend 252/252 + `tsc` limpo.
- **E2E do incidente, ao vivo**: criei uma sessão real pela API → snapshot
  apareceu em `_ATLASFILE/journal/chat_sessions/` → **apaguei o índice de
  sessões** → reconcile → **1 sessão restaurada** e o índice de volta com ela.
  As 2 sessões anteriores ao journal não voltaram — não têm origem, e isso é
  a limitação honesta: o journal protege do momento em que entrou em diante.
