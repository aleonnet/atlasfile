# Plano de Teste E2E — AtlasFile 0.4.0

## Pré-requisitos

```bash
# 1. Carregar PROJECTS_HOST_ROOT e criar pasta de teste
export $(grep PROJECTS_HOST_ROOT .env | xargs)
mkdir -p "$PROJECTS_HOST_ROOT/teste_e2e"

# 2. Reset do índice OpenSearch
make docker-update RESET_INDEX=1

# 3. Preparar arquivos de teste variados (copiar para o inbox depois de inicializar)
```

### Arquivos de teste sugeridos (5-8 arquivos cobrindo diferentes tipos)

| # | Arquivo | Tipo esperado | Área esperada (pelo template default) |
|---|---------|---------------|---------------------------------------|
| 1 | `Contrato_Servicos_TI.pdf` | contrato | contratos_comunicacao |
| 2 | `Nota_Fiscal_2026_001.pdf` | nota_fiscal | financeiro |
| 3 | `Ata_Reuniao_Board.docx` | ata | societario_fiscal |
| 4 | `Relatorio_Due_Diligence.pdf` | relatorio | juridica |
| 5 | `Planilha_Orcamento.xlsx` | planilha | financeiro |
| 6 | `Apresentacao_Projeto.pptx` | apresentacao | estrategia |
| 7 | `DocuSign_SPA__Anexos_v_A.pdf` | contrato | juridica |
| 8 | `Contrato_Servicos_TI.pdf` (cópia idêntica do #1) | dedup | — |

---

## BLOCO 1 — Pipeline Core (Crítico)

> Sem isso nada funciona. É o fluxo principal de valor.

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 1.1 | Health check | `curl http://localhost:8000/health` | `{"status": "ok"}` |
| 1.2 | Setup status | `curl http://localhost:8000/api/setup/status` | `onboarding_suggested: true` (sem projetos inicializados) |
| 1.3 | Listar projetos | UI: verificar seletor de projetos no header | `teste_e2e` aparece como não inicializado; `_ATLASFILE` e `.DS_Store` **não** aparecem |
| 1.4 | Inicializar projeto | UI: selecionar `teste_e2e` → modal de template → selecionar "default" → Confirmar | Pastas criadas: `_PROFILE/`, `_INBOX/`, `_TRIAGE_REVIEW/`, subpastas de áreas. Profile gravado com `project_id` normalizado (lowercase, sem acentos) |
| 1.5 | Verificar profile | UI: aba Operacional → seção Profile/Layout | Profile carregado, `project_id: "teste_e2e"`, seção `naming` presente com `canonical_pattern: "{date}__{project}__{original_name}"` |
| 1.6 | Copiar arquivos para inbox | `cp <arquivos 1-8> "$PROJECTS_HOST_ROOT/teste_e2e/_INBOX/"` | Arquivos presentes na pasta |
| 1.7 | Processar inbox (scan) | UI: card Ingestão → "Processar INBOX" | Status mostra processamento. Arquivos classificados e movidos para áreas ou `_TRIAGE_REVIEW/pending/` |
| 1.8 | Verificar canonical filename | Verificar nomes dos arquivos nas pastas de área | Formato: `YYYYMMDD__teste_e2e__NomeOriginal__v01.ext` (nome original preservado com case/acentos, sem `area_key` no nome) |
| 1.9 | Verificar dedup | Arquivo #8 (cópia idêntica do #1) | Não deve ser duplicado. Deve logar skip por SHA256 idêntico **ou** versionar como `__v02` se SHA diferir |
| 1.10 | Verificar `_INDEX.md` | `cat "$PROJECTS_HOST_ROOT/teste_e2e/_INDEX.md"` | Todas as linhas presentes com `original_filename` = nome original real (ex: `Contrato_Servicos_TI.pdf`), `canonical_filename` no novo formato |
| 1.11 | Histórico de ingestão | UI: card Ingestão → ver histórico paginado | Entradas para cada arquivo processado com decision (auto/triage_pending), confidence, area_key |

---

## BLOCO 2 — Reconciliação (Crítico)

> Garante consistência entre filesystem, `_INDEX.md` e OpenSearch.

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 2.1 | Reconciliação do projeto | UI: botão "Reconciliar INDEX" com `teste_e2e` selecionado | Reconciliação executa, SSE mostra progresso, summary com docs indexados |
| 2.2 | Verificar indexação | `curl "http://localhost:8000/api/stats?project_id=teste_e2e"` | `total_documents > 0`, distribuição por `by_doc_kind`, `by_area_key`, `by_document_type` |
| 2.3 | Reconciliação incremental (idempotência) | Rodar reconciliação novamente sem alterar nada | Modo incremental (default): compara SHA256 + metadados. `skipped_docs` = total (nenhum doc reindexado), `indexed_docs` = 0 |
| 2.4 | Forçar reindexação por metadado | Editar `project_id` de um doc manualmente em `_INDEX.md` e reconciliar | Doc reindexado (sync incremental detecta `project_id` diferente) |
| 2.5 | Reconstrução de `_INDEX.md` | Deletar `_INDEX.md` e reconciliar | `_INDEX.md` recriado. `original_filename` reconstruído via `extract_original_name_from_canonical()` |
| 2.6 | Cleanup de órfãos (automático) | Deletar pasta de um projeto do disco e rodar reconciliação de qualquer outro projeto | Orphans do projeto deletado removidos automaticamente do índice (cleanup executa ao final do `run_reconcile`). Summary mostra `orphan_docs_deleted > 0` |
| 2.7 | Mensagem de reconciliação | UI: barra de status inferior | Mostra ajustes, docs indexados, skipped, falhas e órfãos removidos |
| 2.8 | Scan de PARA roots | Colocar um arquivo em `03_RESOURCES/` e outro em `04_ARCHIVE/` do projeto `teste_e2e`, reconciliar | Ambos aparecem no `_INDEX.md` com `area_key` = `resources` e `archive` respectivamente |
| 2.9 | `area_key` em `02_AREAS` | Verificar arquivo processado em `02_AREAS/financeiro/` | `area_key` = `financeiro` (inferido da subpasta, não "areas") |
| 2.10 | `_WORK/` ignorado | Criar pasta `_WORK/` com um arquivo dentro, reconciliar | Arquivo **não** incluído no `_INDEX.md` (legacy removido) |

---

## BLOCO 3 — Busca, Listagem e Estatísticas (Alto)

> Interface primária de consulta para o usuário e para o LLM.

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 3.1 | Busca full-text | UI: Ctrl+K → digitar "contrato" → Enter | Resultados com highlights, score, doc_id. `Contrato_Servicos_TI` e `DocuSign_SPA` devem aparecer |
| 3.2 | Busca com filtros | API: `curl "http://localhost:8000/api/search?q=contrato&project_id=teste_e2e&doc_kind=pdf"` | Apenas PDFs do projeto `teste_e2e` |
| 3.3 | Listagem sem query | `curl "http://localhost:8000/api/documents?project_id=teste_e2e"` | Lista paginada com `original_filename`, `doc_kind`, `area_key`, `tags`. Sem necessidade de texto |
| 3.4 | Listagem com filtro por tipo | `curl "http://localhost:8000/api/documents?project_id=teste_e2e&doc_kind=xlsx"` | Apenas planilhas |
| 3.5 | Suggest/autocomplete | `curl "http://localhost:8000/api/search/suggest?q=cont&project_id=teste_e2e"` | Sugestões com "contrato", "Contrato_Servicos_TI" etc. |
| 3.6 | Stats globais | `curl "http://localhost:8000/api/stats"` | Agregações completas: `by_doc_kind`, `by_area_key`, `by_document_type`, `by_extension`, `by_tags`, `by_project_id` |
| 3.7 | Stats por projeto | `curl "http://localhost:8000/api/stats?project_id=teste_e2e"` | Apenas dados do `teste_e2e` |

---

## BLOCO 4 — Normalização de `project_id` (Alto)

> Garante que acentos, case e espaços não quebram buscas e filtros.

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 4.1 | Criar projeto com acentos | Criar pasta `projeto_ação` e inicializar | `project_id` gravado como `projeto_acao` (normalizado), `project_label` preserva "projeto_ação" |
| 4.2 | Busca com acento | `curl "http://localhost:8000/api/documents?project_id=projeto_ação"` | Retorna docs (fuzzy match normaliza o input) |
| 4.3 | Busca com espaço | `curl "http://localhost:8000/api/documents?project_id=teste+e2e"` ou `teste e2e` | Retorna docs do `teste_e2e` (espaço↔underscore tolerant) |
| 4.4 | Busca case-insensitive | `curl "http://localhost:8000/api/documents?project_id=TESTE_E2E"` | Retorna docs (case normalizado) |
| 4.5 | Stats `by_project_id` | Verificar que `by_project_id` retorna IDs normalizados | Sem duplicatas por variação de acentos/case |

---

## BLOCO 5 — Triagem (Médio-Alto)

> Fluxo de revisão humana quando classificação não é automática.

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 5.1 | Verificar itens em triagem | UI: card Ingestão → seção Triagem pendente | Itens com confidence entre `triage_min` e `auto_route_min` aparecem |
| 5.2 | Aprovar item | UI: clicar "Aprovar" em item de triagem | Arquivo movido para área sugerida, indexado, removido de `_TRIAGE_REVIEW` |
| 5.3 | Corrigir área | UI: clicar "Corrigir" → modal → selecionar área diferente → Confirmar | Arquivo movido para nova área, `area_key` atualizado no índice |
| 5.4 | Rejeitar item | UI: clicar "Rejeitar" em item de triagem | Arquivo movido para `_TRIAGE_REVIEW/rejected/`, não indexado |
| 5.5 | Canonical na triagem | Verificar nome do arquivo após aprovação | Mesmo formato canônico: `YYYYMMDD__proj__original_name__v01.ext` |

---

## BLOCO 6 — Assistente LLM / Chat (Médio-Alto)

> Requer API key configurada (OpenAI ou Anthropic).

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 6.1 | Configurar API key | UI: aba Assistente → Settings → inserir key | Key salva no localStorage |
| 6.2 | Criar sessão de chat | UI: "Nova conversa" | Sessão criada |
| 6.3 | Perguntar stats | "Quantos documentos temos no projeto teste_e2e?" | LLM chama `get_stats`, responde com total e distribuição |
| 6.4 | Listar documentos | "Liste os documentos do projeto teste_e2e" | LLM chama `list_documents`, mostra **original_filename** (não canonical), apenas docs de `teste_e2e` (sem misturar projetos) |
| 6.5 | Buscar conteúdo | "Busque documentos sobre due diligence" | LLM chama `search_documents` com query, retorna resultados com highlights |
| 6.6 | Escopo/limites | "Qual a previsão do tempo para amanhã?" | LLM recusa educadamente, explica o que pode fazer |
| 6.7 | Sessões CRUD | Renomear sessão, deletar sessão, listar sessões | Operações refletidas na UI e persistidas |
| 6.8 | MCP `list_documents` | Via MCP client ou chat | Retorna `original_filename`, não `title` canônico |
| 6.9 | MCP search guard | Testar search com query vazia ou 1 char via MCP | Erro orientativo: "query must have at least 2 characters. Use list_documents..." |

---

## BLOCO 7 — Templates (Médio)

> Gerenciamento de templates para diferentes tipos de projeto.

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 7.1 | Listar templates | UI: aba Templates | Template "default" listado como builtin |
| 7.2 | Criar template | UI: botão "Novo template" → preencher slug, nome, desc | Template criado, aparece na lista |
| 7.3 | Editar template | UI: selecionar template → editar áreas, routing rules, thresholds | Alterações salvas e visíveis ao reabrir |
| 7.4 | Deletar template (user) | UI: deletar template criado pelo usuário | Template removido da lista |
| 7.5 | Proteger template builtin | UI: tentar deletar "default" | Operação bloqueada (template builtin não pode ser deletado) |
| 7.6 | Inicializar com template custom | Criar novo projeto → selecionar template custom → inicializar | Profile criado com configurações do template custom |

---

## BLOCO 8 — Profile e Layout (Médio)

> Edição de perfil do projeto e migração de estrutura de pastas.

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 8.1 | Ver profile | UI: seção Profile/Layout com projeto selecionado | Profile completo com áreas, naming, layout |
| 8.2 | Editar profile | UI: alterar campo (ex: adicionar nova área) → Salvar | Profile atualizado, versão incrementada |
| 8.3 | Histórico de profile | UI: ver histórico de alterações | Lista de versões com timestamp e autor |
| 8.4 | Validar profile | UI: inserir dados inválidos → Salvar | Erro de validação exibido (ex: `canonical_pattern` sem `{original_name}`) |
| 8.5 | Layout plan | UI: alterar layout → "Simular" | Preview do plano de migração (rename, move, delete) |
| 8.6 | Layout apply | UI: "Aplicar" plano de migração | Pastas reorganizadas no disco conforme plano |

---

## BLOCO 9 — UI/UX e Responsividade (Médio-Baixo)

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 9.1 | Theme toggle | UI: ícone sol/lua no header | Alterna entre claro/escuro/system, cores consistentes |
| 9.2 | ESC fecha modais | Abrir qualquer modal → pressionar ESC | Modal fecha |
| 9.3 | Controle operacional | UI: aba Operacional com projeto selecionado | Layout compacto com métricas (total docs, tipos), mini-table de projetos, footer de reconciliação |
| 9.4 | Onboarding wizard | Limpar localStorage (`atlasfile-onboarding-done`) → recarregar | Wizard aparece com steps: welcome, projects, llm, done |
| 9.5 | Responsividade 768-1200px | Redimensionar janela para tablet | Cards empilham, header adapta, sem overflow horizontal |
| 9.6 | Responsividade < 768px | Redimensionar para mobile | Layout mobile funcional, touch-friendly |
| 9.7 | Busca modal (Ctrl+K) | Ctrl+K → digitar → ver sugestões → Enter | Modal abre, sugestões em tempo real, resultados completos ao confirmar |

---

## BLOCO 10 — Migração de Formato Canônico (Baixo)

> Testa retrocompatibilidade com arquivos do formato antigo.

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 10.1 | Criar arquivo formato antigo | Criar manualmente: `20260301__teste_e2e__financeiro__nota_fiscal__v01.pdf` em uma pasta de área | Arquivo no formato antigo presente |
| 10.2 | Reconciliar | Rodar reconciliação | Arquivo renomeado para `20260301__teste_e2e__nota_fiscal__v01.pdf` (area removida) |
| 10.3 | Verificar `_INDEX.md` | Ler `_INDEX.md` | `original_filename` = `nota_fiscal.pdf` (extraído corretamente), `canonical_filename` no novo formato |
| 10.4 | Colisão na migração | Criar outro arquivo com mesmo nome de destino | Migration skip: arquivo original mantido, log de warning |

---

## BLOCO 11 — Tags e Metadados (Baixo)

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 11.1 | Adicionar tags | `curl -X POST "http://localhost:8000/api/documents/{doc_id}/tags" -H "Content-Type: application/json" -d '{"add":["importante","urgente"]}'` | Tags adicionadas, visíveis na busca |
| 11.2 | Remover tag | `curl -X POST "http://localhost:8000/api/documents/{doc_id}/tags" -H "Content-Type: application/json" -d '{"remove":["urgente"]}'` | Tag removida |
| 11.3 | Listar tags agregadas | `curl "http://localhost:8000/api/tags?project_id=teste_e2e"` | Lista de tags únicas com contagem |
| 11.4 | Atualizar metadados | `curl -X PATCH "http://localhost:8000/api/documents/{doc_id}" -H "Content-Type: application/json" -d '{"document_type":"parecer"}'` | `document_type` atualizado no índice |

---

## BLOCO 12 — Download e Chunks (Baixo)

| # | Passo | Como testar | Resultado esperado |
|---|-------|-------------|-------------------|
| 12.1 | Download de arquivo | `curl "http://localhost:8000/api/files/download?path=<path>"` | Arquivo baixado corretamente |
| 12.2 | Ver documento | `curl "http://localhost:8000/api/documents/{doc_id}"` | Metadados + conteúdo (pode ser truncado) |
| 12.3 | Chunks por location | `curl "http://localhost:8000/api/documents/{doc_id}/chunks?locations=page:1"` | Chunks específicos retornados |

---

## Checklist de Execução

```
BLOCO 1 — Pipeline Core          [ok] 1.1  [ok] 1.2  [ok] 1.3  [ok] 1.4  [ok] 1.5
                                  [ ] 1.6  [ ] 1.7  [ ] 1.8  [ ] 1.9  [ ] 1.10  [ ] 1.11

BLOCO 2 — Reconciliação          [ ] 2.1  [ ] 2.2  [ ] 2.3  [ ] 2.4  [ ] 2.5
                                  [ ] 2.6  [ ] 2.7  [ ] 2.8  [ ] 2.9  [ ] 2.10

BLOCO 3 — Busca/Listagem/Stats   [ ] 3.1  [ ] 3.2  [ ] 3.3  [ ] 3.4  [ ] 3.5
                                  [ ] 3.6  [ ] 3.7

BLOCO 4 — Normalização project_id [ ] 4.1  [ ] 4.2  [ ] 4.3  [ ] 4.4  [ ] 4.5

BLOCO 5 — Triagem                [ ] 5.1  [ ] 5.2  [ ] 5.3  [ ] 5.4  [ ] 5.5

BLOCO 6 — Assistente LLM         [ ] 6.1  [ ] 6.2  [ ] 6.3  [ ] 6.4  [ ] 6.5
                                  [ ] 6.6  [ ] 6.7  [ ] 6.8  [ ] 6.9

BLOCO 7 — Templates              [ ] 7.1  [ ] 7.2  [ ] 7.3  [ ] 7.4  [ ] 7.5  [ ] 7.6

BLOCO 8 — Profile/Layout         [ ] 8.1  [ ] 8.2  [ ] 8.3  [ ] 8.4  [ ] 8.5  [ ] 8.6

BLOCO 9 — UI/UX                  [ ] 9.1  [ ] 9.2  [ ] 9.3  [ ] 9.4  [ ] 9.5
                                  [ ] 9.6  [ ] 9.7

BLOCO 10 — Migração formato      [ ] 10.1 [ ] 10.2 [ ] 10.3 [ ] 10.4

BLOCO 11 — Tags/Metadados        [ ] 11.1 [ ] 11.2 [ ] 11.3 [ ] 11.4

BLOCO 12 — Download/Chunks       [ ] 12.1 [ ] 12.2 [ ] 12.3
```

---

## Ordem recomendada de execução

1. Subir stack: `make docker-update RESET_INDEX=1`
2. Executar **Blocos 1-4** sequencialmente (dependem um do outro)
3. Executar **Blocos 5-6** (requerem docs indexados do Bloco 1-2)
4. Executar **Blocos 7-12** em qualquer ordem
