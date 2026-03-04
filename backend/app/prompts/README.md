# Prompts do AtlasFile

Arquivos `.md` carregados em tempo de execução pelo orchestrator. Permite editar os prompts sem alterar código.

- **system_prompt_chat.md** – System prompt do chat (assistente + ferramentas MCP).
- **system_prompt_classify.md** – System prompt da classificação de documentos (submit_classification).

Se um arquivo não existir ou não puder ser lido, o backend usa o fallback definido em `app/prompts.py`.
