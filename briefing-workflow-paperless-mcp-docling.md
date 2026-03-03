# Briefing (IA) — Workflow “Agente + Documentos” com Paperless-ngx + MCP (Docker)

> **Objetivo de negócio**  
> Permitir que um **Agente de IA** receba uma pergunta em linguagem natural, **opere ferramentas via MCP** (busca, leitura, tagging, workflow) em um repositório documental (Paperless-ngx) e devolva **respostas com evidência**, incluindo **trechos citados** e, quando possível, **página exata**.

## 1) Requisitos (hard / soft)

### Hard requirements
- Tudo **self-hosted** via **Docker** (sem SaaS pago).
- Base documental com pipeline “pronto”: **ingestão + OCR + indexação + UI**.
- Agente usa **MCP** para operar a base (tool-calling).
- Resposta do agente deve retornar:
  - lista de documentos relevantes (nome + `doc_id`),
  - **trecho citado** (snippet) e **localização** (página quando disponível),
  - campos extraídos (ex.: `multa`, `prazo_cura`),
  - ações executadas quando solicitadas (ex.: aplicar tag; abrir workflow).

### Soft requirements
- “Página exata” **desejável** (ideal), mas aceitar fallback para:
  - trecho + link de abertura do documento,
  - ou “page guess” (estimativa) quando não houver mapeamento robusto.

---

## 2) Solução-base recomendada

### Camada A — DMS (pipeline pronto)
- **Paperless-ngx** como **source of truth**: ingestão, OCR, armazenamento, indexação e busca.
- Motivo: entrega o pipeline documental com menor atrito operacional.

### Camada B — Tool Gateway / MCP
- **paperless-mcp** (MCP Server) conectado à API do Paperless-ngx.
- Motivo: habilita o Agente a operar ações determinísticas (buscar, listar, ler metadata, atualizar tags etc.).

### Camada C — “Página exata” sob demanda
- **Docling MCP** como ferramenta opcional “on-demand”:
  - Quando o usuário exige “página exata” (hard requirement em uma consulta específica), o Agente aciona Docling para extrair **texto por página** (e, se disponível, estrutura/coords) para localizar a ocorrência com precisão.

### Camada D — Agente (orquestrador)
- Um runtime de agente com suporte a MCP (ex.: client MCP do seu stack) que:
  1) chama ferramentas MCP (Paperless) para recuperar candidatos;
  2) lê conteúdo/chunks para evidência;
  3) (opcional) chama Docling para page mapping;
  4) extrai campos e responde com citações;
  5) executa ações (tag/workflow) quando solicitado.

---

## 3) Pergunta: “precisa do Paperless-AI?”
**Resposta:** **Não é obrigatório** para este workflow.  
- O **paperless-mcp** resolve a parte “agente operando ferramenta” (buscar/ler/organizar/ação) via API.
- O **Paperless-AI** é **opcional** se você quiser **automação contínua** dentro do Paperless-ngx (ex.: auto-tagging, classificação, enriquecimento) sem depender do agente em tempo real.

### Quando usar Paperless-AI (opcional)
- Você quer que documentos novos recebam tags/categorias automaticamente no ingest (sempre ligado).
- Você quer “semantic search”/classificação por LLM integrada ao fluxo documental.

### Quando NÃO usar Paperless-AI
- Você quer manter o sistema simples e o Agente já faz a análise “on-demand”.
- Você quer evitar mais um serviço e complexidade de operação.

**Recomendação pragmática:** começar **sem Paperless-AI**, medir fricções e só adicionar depois se fizer falta.

---

## 4) Componentes Docker (alto nível)

### Containers mínimos
1. `paperless-ngx` (+ deps recomendadas do projeto: DB + broker/cache)
2. `paperless-mcp` (MCP server apontando para API do Paperless)
3. `agent-runtime` (seu agente/chat com suporte a MCP)
4. `docling-mcp` (opcional; só se/when page mapping for exigido)

> Observação: este briefing não fixa imagens/tags específicas; a IA configuradora deve usar **docker-compose** e as referências oficiais dos projetos para a versão estável.

---

## 5) Contratos MCP (Tools) — necessários e bem definidos

### Paperless MCP — tools obrigatórias
> Nomes podem variar conforme `paperless-mcp`. A IA deve mapear os nomes reais do servidor MCP instalado para estes **contratos funcionais**.

#### `search_documents(query, filters) -> results[]`
- **Input**
  - `query`: string (texto de busca)
  - `filters` (opcional):
    - `document_type` (ex.: “contract”)
    - `tags` (ex.: “SERREDE”)
    - `date_from`, `date_to`
    - `correspondent`, `owner`, `project`
- **Output (mínimo)**
  - `doc_id`, `title`, `created`, `score`
  - `snippet` (se disponível)
  - `url` (link para abrir no Paperless)

#### `get_document(doc_id) -> doc`
- Retorna metadata + conteúdo (quando exposto pelo MCP) ou ponte para baixar/ler.
- **Se não retornar texto**, expor ferramenta adicional:
  - `download_document(doc_id)` ou `get_document_content(doc_id)`

#### `apply_tags(doc_id, tags_to_add, tags_to_remove?)`
- Idempotente (não duplicar tag).

#### `set_metadata(doc_id, fields)`
- Campos típicos: `document_type`, `correspondent`, `custom_fields`.

#### (Opcional) `create_task(...)` / `start_workflow(...)`
- Se Paperless não tiver “workflow/task” nativo do jeito desejado, crie “task” como:
  - tag especial (ex.: `REVIEW_LEGAL`)
  - ou custom field “status = needs_review”
  - ou integração com um tracker local (ex.: Plane/Linear/Jira self-hosted), se permitido.

### Docling MCP — tools opcionais (para página exata)
#### `parse_document(file_url_or_bytes, options) -> pages[]`
- Output por página:
  - `page_number`
  - `text`
  - (ideal) `spans`/`coords` se existir
- O Agente deve rodar **somente quando necessário** (custo/tempo).

#### `find_phrase(pages, phrase|regex) -> occurrences[]`
- Retorna:
  - `page_number`
  - trecho de contexto
  - posição/offset (se disponível)

---

## 6) Política de resposta (Evidence-first)

O Agente **não deve** responder “de cabeça” quando a pergunta exige evidência documental.  
Formato mínimo de resposta:

- **Resultado** (em bullets / tabela):
  - `Documento`: título + `doc_id` + link
  - `Trecho citado`: “...” (contexto curto)
  - `Local`: página X (se disponível; senão “sem page mapping”)
  - `Campos extraídos`: `multa = ...`, `prazo_cura = ...`
- **Ações executadas** (se usuário pediu):
  - tags adicionadas
  - workflow/task criado (e como localizar isso)

---

## 7) Fluxo conversacional (exemplo alvo)

### Prompt do usuário
> “Ache os contratos da Serede com cláusula de multa por SLA e me diga quais têm prazo de cura até 10 dias.”

### Plano do Agente (obrigatório)
1. **search_documents()**
   - `query`: `"multa" AND "SLA" AND ("prazo de cura" OR "cure period" OR "prazo para saneamento")`
   - `filters`: `document_type=contract`, `tag|correspondent=Serede`, intervalo de datas se houver.
2. Selecionar Top N (ex.: 10–30) por score e diversidade.
3. **get_document()** para coletar conteúdo/chunks relevantes.
4. Extrair campos:
   - `multa`: valor/percentual/condição
   - `prazo_cura`: número de dias (normalizar)
5. Se **página exata** for exigida (ou se a confiança for baixa):
   - baixar PDF (via ferramenta do Paperless, se existir)
   - chamar `docling.parse_document(...)`
   - localizar ocorrência e obter `page_number`
6. Responder com lista estruturada + evidência.
7. Se o usuário pedir: “aplique tag SLA_PENALTY e crie task de revisão jurídica”
   - `apply_tags(doc_id, ["SLA_PENALTY"])`
   - `set_metadata(doc_id, {"review_status":"legal_review"})` **OU** `apply_tags(doc_id, ["REVIEW_LEGAL"])`
   - (se existir) `start_workflow(doc_id, "legal-review")`

---

## 8) Regras de segurança e controle
- O agente deve operar com **princípio do menor privilégio**:
  - token/credencial do Paperless com permissões apenas necessárias (read + tag/metadata; delete desabilitado).
- Todas as ações mutáveis devem ter:
  - logs (quem pediu, quando, quais doc_ids)
  - modo “dry-run” opcional (se desejado)

---

## 9) Testes de aceitação (mínimos)

### T1 — Busca e evidência
- Dado um conjunto de contratos com “SLA”, o agente deve:
  - listar ao menos 3 docs relevantes,
  - citar trechos,
  - fornecer links e doc_id.

### T2 — Extração de campos
- Deve extrair `prazo_cura` em dias e normalizar “10 (dez) dias” para `10`.

### T3 — Página exata (quando acionado)
- Para um PDF onde a frase aparece, o agente deve retornar `page_number` correto (Docling MCP).

### T4 — Ações
- Ao pedir tagging, confirmar que a tag foi aplicada e reaparece ao buscar o doc.

---

## 10) Entregáveis esperados da IA configuradora

1. `docker-compose.yml` com os serviços:
   - paperless-ngx (+ deps)
   - paperless-mcp
   - agent-runtime (stub mínimo)
   - docling-mcp (opcional)
2. Arquivo(s) `.env` com variáveis necessárias (sem segredos hardcoded).
3. Documentação curta “como rodar”:
   - `docker compose up -d`
   - como autenticar MCP
   - como testar com 2–3 prompts
4. Mapeamento final “tools MCP reais vs contratos desejados” (tabela).

---

## 11) Observações finais (trade-offs)
- **Página exata** em PDFs escaneados requer OCR **por página** + pipeline que preserve essa estrutura. Docling tende a melhorar isso quando acionado.
- Comece simples: Paperless + MCP + agente. Só adicione Docling quando a demanda por page mapping for real (evita custo e complexidade).

