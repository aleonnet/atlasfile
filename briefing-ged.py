updated = r"""# Briefing (IA) — Workflow “Agente + Documentos” com Paperless-ngx + MCP + Paperless-AI (Docker)

> **Objetivo de negócio**  
> Permitir que um **Agente de IA** receba uma pergunta em linguagem natural, **opere ferramentas via MCP** (busca, leitura, tagging, workflow) em um repositório documental (Paperless-ngx) e devolva **respostas com evidência**, incluindo **trechos citados** e, quando possível, **página exata**.  
> Além disso, **todo documento novo** deve entrar com **classificação e tags automáticas** (sempre ligado), sem depender do agente “on-demand”.

---

## 1) Requisitos (hard / soft)

### Hard requirements
- Tudo **self-hosted** via **Docker** (sem SaaS pago/caro).
- Base documental com pipeline “pronto”: **ingestão + OCR + indexação + UI**.
- **Auto-classificação e auto-tagging no ingest (requisito):**
  - todo documento novo deve receber **tags/categorias** automaticamente;
  - deve existir fallback seguro para **baixa confiança** (triagem/revisão).
- Agente usa **MCP** para operar a base (tool-calling).
- Resposta do agente deve retornar:
  - lista de documentos relevantes (nome + `doc_id`),
  - **trecho citado** (snippet) e **localização** (página quando disponível),
  - campos extraídos (ex.: `multa`, `prazo_cura`),
  - ações executadas quando solicitadas (ex.: aplicar tag; abrir workflow/task).

### Soft requirements
- “Página exata” **desejável** (ideal), mas aceitar fallback para:
  - trecho + link de abertura do documento,
  - ou “page guess” (estimativa) quando não houver mapeamento robusto.

---

## 2) Solução-base recomendada

### Camada A — DMS (pipeline pronto)
- **Paperless-ngx** como **source of truth**: ingestão, OCR, armazenamento, indexação e busca.
- Motivo: entrega o pipeline documental com menor atrito operacional.

### Camada B — Auto-classificação/auto-tagging (requisito)
- **Paperless-AI** (ou equivalente *self-hosted* e integrado ao Paperless) como serviço sempre ligado.
- Responsabilidades:
  - atribuir **document_type / correspondent / tags** automaticamente no ingest;
  - registrar **confiança** (confidence) e decidir:
    - **auto-apply** acima de um threshold,
    - **enfileirar para revisão** abaixo do threshold.
- Motivo: você explicitou que isso é **requisito**, não “dor”.

> **Nota:** Paperless-AI não substitui o Agente; ele automatiza o “ingest enrichment”.  
> O Agente segue sendo o operador (via MCP) para perguntas e ações explícitas.

### Camada C — Tool Gateway / MCP
- **paperless-mcp** (MCP Server) conectado à API do Paperless-ngx.
- Motivo: habilita o Agente a operar ações determinísticas (buscar, listar, ler metadata, atualizar tags etc.).

### Camada D — “Página exata” sob demanda
- **Docling MCP** como ferramenta opcional “on-demand”:
  - quando a consulta exigir precisão de **página exata**, o Agente aciona Docling para extrair **texto por página** (e, se disponível, estrutura/coords) para localizar ocorrência com precisão.

### Camada E — Agente (orquestrador)
- Um runtime de agente com suporte a MCP (cliente MCP do seu stack) que:
  1) chama ferramentas MCP (Paperless) para recuperar candidatos;
  2) lê conteúdo/chunks para evidência;
  3) (opcional) chama Docling para page mapping;
  4) extrai campos e responde com citações;
  5) executa ações (tag/workflow/task) quando solicitado.

---

## 3) Paperless-AI: como deve funcionar (contrato funcional)

### 3.1 Saídas mínimas por documento novo
Ao receber um documento novo (via consume folder / upload / e-mail), o Paperless-AI deve produzir (ou atualizar) no Paperless:
- `document_type` (ex.: Contract, Invoice, NDA)
- `correspondent` (ex.: Serede, Oi, TIM) — quando aplicável
- `tags[]` (ex.: `SERREDE`, `SLA`, `CONTRATO`)
- `ai_confidence` (ex.: 0.00–1.00) **ou** categorias por campo

### 3.2 Política de confiança e triagem (obrigatória)
- Definir `AUTO_APPLY_THRESHOLD` (ex.: 0.85) e `REVIEW_THRESHOLD` (ex.: 0.60).
- Regras:
  - `confidence >= AUTO_APPLY_THRESHOLD` → aplicar automaticamente.
  - `REVIEW_THRESHOLD <= confidence < AUTO_APPLY_THRESHOLD` → aplicar parcialmente + marcar para revisão.
  - `confidence < REVIEW_THRESHOLD` → não aplicar campos sensíveis + marcar para revisão.

### 3.3 Como marcar “para revisão”
Como Paperless-ngx não é um BPM completo, usar uma destas abordagens (preferência na ordem):
1) **Tag de revisão**: `REVIEW_REQUIRED` (e opcionalmente `REVIEW_LEGAL`, `REVIEW_FINANCE`)
2) **Custom field**: `review_status = needs_review`
3) **Folder/Inbox lógico** via tags/correspondent/type (evitar mover arquivos fisicamente)

### 3.4 Reversibilidade / auditoria
- Toda decisão automática deve ser rastreável via:
  - log do serviço Paperless-AI,
  - e/ou custom field `ai_last_run`, `ai_model`, `ai_confidence`.

---

## 4) Componentes Docker (alto nível)

### Containers mínimos
1. `paperless-ngx` (+ deps recomendadas do projeto: DB + broker/cache)
2. `paperless-ai` (serviço de auto-classificação/auto-tagging, sempre ligado)
3. `paperless-mcp` (MCP server apontando para API do Paperless)
4. `agent-runtime` (seu agente/chat com suporte a MCP)
5. `docling-mcp` (opcional; só se/when page mapping for exigido)

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

#### `list_tags()` / `ensure_tag_exists(tag_name)`
- Necessário para o agente (e/ou Paperless-AI) garantir tags padronizadas.

#### `start_workflow(doc_id, workflow_id)` (se existir) **OU** `create_review_marker(doc_id, kind)`
- Se Paperless não tiver “workflow/task” nativo do jeito desejado, padronizar como:
  - tag `REVIEW_LEGAL` / `REVIEW_FINANCE`
  - ou custom field `review_status`

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
  - marker de revisão / workflow/task criado (e como localizar isso)

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

## 8) Automação no ingest (Paperless-AI) — testes e regras

### 8.1 Teste de ingest com classificação automática
- Ao adicionar um novo contrato com “SLA”, o Paperless-AI deve:
  - atribuir `document_type=contract` (ou equivalente),
  - aplicar tags como `SERREDE` e `SLA` (se reconhecíveis),
  - registrar `ai_confidence`.

### 8.2 Baixa confiança → revisão
- Se `ai_confidence` abaixo do threshold, o documento deve ficar marcado com:
  - `REVIEW_REQUIRED` (tag) e/ou `review_status = needs_review`.

### 8.3 Correção humana retroalimenta padrão (quando possível)
- Se existir mecanismo de “aprendizado”/regras no Paperless-AI, habilitar:
  - reprocessamento sob demanda (`reclassify(doc_id)`) ou job periódico.

---

## 9) Regras de segurança e controle
- O agente deve operar com **princípio do menor privilégio**:
  - token/credencial do Paperless com permissões apenas necessárias (read + tag/metadata; delete desabilitado).
- Paperless-AI deve usar credencial com permissões:
  - read + update tags/types/correspondent (sem delete).
- Todas as ações mutáveis devem ter:
  - logs (quem pediu, quando, quais doc_ids)
  - modo “dry-run” opcional (se desejado)

---

## 10) Testes de aceitação (mínimos)

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

### T5 — Auto-tag no ingest (requisito)
- Inserir 5 documentos novos variados (misto PDF texto + scan):
  - 4/5 devem receber `document_type` e ao menos 1 tag correta automaticamente,
  - os casos de baixa confiança devem ficar com `REVIEW_REQUIRED`.

---

## 11) Entregáveis esperados da IA configuradora

1. `docker-compose.yml` com os serviços:
   - paperless-ngx (+ deps)
   - paperless-ai
   - paperless-mcp
   - agent-runtime (stub mínimo)
   - docling-mcp (opcional)
2. Arquivo(s) `.env` com variáveis necessárias (sem segredos hardcoded).
3. Documentação curta “como rodar”:
   - `docker compose up -d`
   - como autenticar MCP
   - como testar ingest + auto-tag
   - como testar 2–3 prompts do agente
4. Mapeamento final “tools MCP reais vs contratos desejados” (tabela).
5. Política de thresholds e revisão (valores iniciais + como ajustar).

---

## 12) Observações finais (trade-offs)
- **Página exata** em PDFs escaneados requer OCR **por página** + pipeline que preserve essa estrutura. Docling tende a melhorar isso quando acionado.
- Paperless-AI cumpre o requisito de **auto-classificação** no ingest, mas aumenta:
  - número de serviços,
  - necessidade de logging/observabilidade,
  - e gestão de modelos (local vs remoto).
- Comece com thresholds conservadores e revisão humana para evitar tags erradas em escala.
"""
out_path = "briefing-workflow-paperless-mcp-docling_v2.md"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(updated)
out_path