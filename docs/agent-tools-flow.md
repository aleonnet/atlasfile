# Como o agente recebe as informações das ferramentas

Este documento descreve **exatamente** como o LLM (agente) tem acesso aos nomes, descrições e schemas das ferramentas no AtlasFile: de onde vêm os dados e qual o formato de cada chamada/resposta.

---

## 1. Visão geral do fluxo

```
┌─────────────────┐     tools/list      ┌─────────────────┐
│  Backend        │ ──────────────────► │  MCP Server     │
│  (orchestrator  │                      │  (FastMCP)      │
│   + mcp_client) │ ◄────────────────── │  server.py      │
└────────┬────────┘   tools[]           └─────────────────┘
         │
         │  Converte para formato do provedor (OpenAI ou Anthropic)
         │
         ▼
┌─────────────────┐
│  LLM            │  Recebe: messages + tools (name, description, parameters)
│  (OpenAI /      │  Responde (quando quer usar ferramenta): tool_calls
│   Anthropic)    │
└────────┬────────┘
         │
         │  Backend chama tools/call no MCP para cada tool_call
         │  e cola o resultado na conversa; reenvia ao LLM.
         ▼
    (loop até o modelo não devolver mais tool_calls)
```

O agente **não** recebe um documento externo. Ele recebe apenas o que é enviado no corpo da requisição da API do provedor (OpenAI Chat Completions ou Anthropic Messages): um array `tools` com nome, descrição e schema de parâmetros. Esse array é montado a partir da resposta do servidor MCP `tools/list`.

---

## 2. Onde as ferramentas são definidas

**Arquivo:** `backend/app/mcp/server.py`

Cada ferramenta é uma função Python decorada com `@mcp.tool()`. O servidor MCP (FastMCP) expõe essas funções via protocolo MCP. O **nome** da ferramenta é o nome da função; a **descrição** vem do docstring; o **inputSchema** é gerado pelo FastMCP a partir dos type hints dos parâmetros (JSON Schema).

Ferramentas expostas hoje (e só essas):

| Ferramenta              | Descrição (resumo do docstring) |
|-------------------------|----------------------------------|
| `search_documents`      | Busca full-text com filtros (project_id, area_key, document_type, tags, datas, page, size) |
| `get_document`          | Obtém documento por doc_id (metadata, excerpt, content_chunks) |
| `apply_tags`            | Adiciona/remove tags de um documento |
| `set_metadata`          | Atualiza document_type, correspondent, area_key, review_status |
| `list_tags`             | Lista tags únicas (opcionalmente por project_id) |
| `create_review_marker`  | Marca documento para revisão (legal_review, finance_review, needs_review) |
| `submit_classification` | Usado pelo fluxo de classificação: document_type, tags, confidence |

Não existe no nosso código nenhuma ferramenta `multi_tool_use.parallel` nem “functions.search_documents” como namespace; o nome enviado ao LLM é exatamente o nome da função (ex.: `search_documents`).

---

## 3. Como o backend obtém a lista de ferramentas (MCP)

**Arquivo:** `backend/app/mcp_client/client.py`

- O backend chama `list_tools()` no início de cada `run_chat_loop`.
- `list_tools()` abre uma sessão MCP via **streamable HTTP** para `settings.mcp_server_url` (ex.: `http://localhost:8001`).
- Envia a requisição **MCP** equivalente a `tools/list` (via `session.list_tools()` do SDK).
- A resposta MCP contém um objeto com uma lista de ferramentas; cada item no SDK Python tem atributos como `name`, `description`, `inputSchema`.

**Mapeamento no nosso client** (trecho relevante):

```python
# app/mcp_client/client.py
tools_response = await session.list_tools()
for t in tools_response.tools:
    result.append({
        "name": t.name,
        "description": t.description or "",
        "inputSchema": getattr(t, "inputSchema", {}),
    })
```

Ou seja: o agente recebe apenas o que o MCP devolve em `tools` (nome, descrição, inputSchema), depois de convertido para o formato do provedor abaixo.

---

## 4. Formato enviado ao LLM (OpenAI)

**Arquivo:** `backend/app/orchestrator.py` — `mcp_tools_to_openai()`

Cada ferramenta MCP vira um item no array `tools` da API OpenAI:

```python
{
    "type": "function",
    "function": {
        "name": t["name"],
        "description": t.get("description") or "",
        "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
    },
}
```

O `inputSchema` vem direto do MCP; se estiver vazio, usamos `{"type": "object", "properties": {}}`.

**Exemplo de payload (OpenAI) — trecho relevante da primeira chamada ao modelo:**

```json
{
  "model": "gpt-4o",
  "messages": [
    { "role": "system", "content": "Você é um assistente que opera sobre um repositório de documentos (AtlasFile)..." },
    { "role": "user", "content": "Liste os contratos do projeto X" }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_documents",
        "description": "Search documents by full-text query with optional filters: project_id, area_key, document_type, tags, date_from, date_to (ISO dates). Returns JSON with total, page, and hits (doc_id, title, path, score, highlights).",
        "parameters": {
          "type": "object",
          "properties": {
            "query": { "type": "string" },
            "project_id": { "type": "string" },
            "area_key": { "type": "string" },
            "document_type": { "type": "string" },
            "tags": { "type": "array", "items": { "type": "string" } },
            "date_from": { "type": "string" },
            "date_to": { "type": "string" },
            "page": { "type": "integer" },
            "size": { "type": "integer" }
          },
          "required": ["query"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "get_document",
        "description": "Get a document by doc_id. Returns metadata, content excerpt, and content_chunks (location + text) for evidence.",
        "parameters": {
          "type": "object",
          "properties": {
            "doc_id": { "type": "string" }
          },
          "required": ["doc_id"]
        }
      }
    }
    // ... demais ferramentas (apply_tags, set_metadata, list_tags, create_review_marker, submit_classification)
  ]
}
```

O `parameters` real é o que o MCP devolve em `inputSchema`; o exemplo acima é o tipo de schema que as assinaturas em `server.py` tendem a gerar. O modelo só enxerga esse JSON.

---

## 5. Formato enviado ao LLM (Anthropic)

**Arquivo:** `backend/app/orchestrator.py` — `mcp_tools_to_anthropic()`

Cada ferramenta vira um item no array `tools` da API Anthropic:

```python
{
    "name": t["name"],
    "description": t.get("description") or "",
    "input_schema": schema,  # inputSchema do MCP, com type: "object" garantido
}
```

**Exemplo equivalente para Anthropic (mesma ferramenta):**

```json
{
  "name": "search_documents",
  "description": "Search documents by full-text query with optional filters: project_id, area_key, document_type, tags, date_from, date_to (ISO dates). Returns JSON with total, page, and hits (doc_id, title, path, score, highlights).",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string" },
      "project_id": { "type": "string" },
      "area_key": { "type": "string" },
      "document_type": { "type": "string" },
      "tags": { "type": "array", "items": { "type": "string" } },
      "date_from": { "type": "string" },
      "date_to": { "type": "string" },
      "page": { "type": "integer" },
      "size": { "type": "integer" }
    },
    "required": ["query"]
  }
}
```

Ou seja: o agente na Anthropic também recebe só nome, descrição e schema; a única diferença é a chave `input_schema` em vez de `parameters` e o envelope da API (Messages em vez de Chat Completions).

---

## 6. Quando o modelo chama uma ferramenta (resposta do LLM)

O modelo devolve uma mensagem com `tool_calls`. Exemplo (OpenAI):

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_abc123",
          "type": "function",
          "function": {
            "name": "search_documents",
            "arguments": "{\"query\": \"contrato\", \"project_id\": \"project123\", \"size\": 20}"
          }
        }
      ]
    }
  }]
}
```

O backend extrai `name` e `arguments` (JSON string), chama o MCP e depois cola o resultado na conversa.

---

## 7. Chamada ao MCP (tools/call)

**Arquivo:** `backend/app/mcp_client/client.py` — `call_tool()`

```python
call_result = await session.call_tool(name, arguments=args)
```

- **Entrada:** `name` (string, ex.: `"search_documents"`), `arguments` (dict, ex.: `{"query": "contrato", "project_id": "project123", "size": 20}`).
- O SDK MCP envia ao servidor o equivalente a **tools/call** com esse nome e argumentos.

No servidor MCP (`server.py`), a função correspondente é executada (ex.: `search_documents(query="contrato", project_id="project123", size=20)`). Ela chama a API HTTP do AtlasFile (ex.: `GET /api/search`) e retorna o resultado.

---

## 8. Resposta do MCP (o que volta para o modelo)

**Arquivo:** `backend/app/mcp_client/client.py`

O resultado de `session.call_tool()` tem:
- `content`: lista de blocos (ex.: `TextContent` com texto).
- Opcionalmente `structuredContent`.

Nosso client concatena o texto:

```python
for block in call_result.content:
    if isinstance(block, TextContent):
        parts.append(block.text)
if call_result.structuredContent and not parts:
    parts.append(json.dumps(call_result.structuredContent, ensure_ascii=False))
return "\n".join(parts) if parts else ""
```

Ou seja: o agente recebe **uma única string** (texto concatenado ou JSON do structured). Não há um “schema de resposta” separado enviado ao modelo; ele aprende o formato pelo conteúdo que já viu em respostas anteriores de ferramentas.

**Exemplo de string retornada para `search_documents`** (o que a função em `server.py` faz é `return json.dumps(data, ensure_ascii=False)` com o JSON da API de busca):

```json
{"total": 4, "page": 1, "page_size": 20, "hits": [{"doc_id": "abc123", "project_id": "p1", "area_key": "contratos", "original_filename": "Contrato.pdf", "canonical_filename": "Contrato.pdf", "path": "/contratos/Contrato.pdf", "score": 0.94, "highlights": ["...trecho..."]}]}
```

**Exemplo para `get_document`:**

```json
{"metadata": {"doc_id": "abc123", "original_filename": "Contrato.pdf", ...}, "excerpt": "Primeiros caracteres do conteúdo...", "content_chunks": [{"location": "p.1", "text": "O CONTRATANTE..."}, ...]}
```

Essas strings são então anexadas à conversa como mensagem de **tool** (OpenAI) ou **user** com bloco **tool_result** (Anthropic), e o loop reenvia todo o histórico (incluindo system, usuário, assistente com tool_calls e resultados) de volta ao modelo.

---

## 9. Resumo

| O quê | Onde | Formato |
|-------|------|--------|
| Definição das ferramentas | `backend/app/mcp/server.py` | Funções `@mcp.tool()` com docstring e type hints |
| Listagem (o que o backend “sabe”) | MCP `tools/list` → `mcp_client.client.list_tools()` | Lista de `{ name, description, inputSchema }` |
| O que o **agente** recebe (OpenAI) | Corpo da 1ª requisição à API OpenAI | `messages` + `tools`: array de `{ type: "function", function: { name, description, parameters } }` |
| O que o **agente** recebe (Anthropic) | Corpo da 1ª requisição à API Anthropic | `messages` + `tools`: array de `{ name, description, input_schema }` |
| Quando o agente “chama” uma ferramenta | Resposta do LLM | `tool_calls`: `{ id, function: { name, arguments } }` |
| Execução real | `mcp_client.client.call_tool(name, arguments)` | MCP **tools/call** → execução da função em `server.py` |
| O que volta para o agente | Resposta do MCP (texto/JSON) | String única colada na conversa como mensagem de tool / tool_result |

Não existe documento externo nem “contrato de API” separado injetado no prompt: **toda a informação que o agente tem sobre as ferramentas vem do array `tools` enviado na primeira (e em cada rodada da) chamada à API do provedor**, montado a partir do MCP `tools/list` e das conversões em `mcp_tools_to_openai` / `mcp_tools_to_anthropic`.
