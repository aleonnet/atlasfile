from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AtlasFile API"
    app_env: str = "dev"

    opensearch_host: str = "http://opensearch:9200"
    opensearch_index: str = "atlasfile_documents"
    opensearch_chat_sessions_index: str = "atlasfile_chat_sessions"
    opensearch_user: str = "admin"
    opensearch_password: str = "admin123"
    opensearch_nested_objects_limit: int = 50000

    projects_root: str = "/projects"
    classifier_datasets_root: str = ""
    auto_scan_on_startup: bool = False
    auto_reconcile_interval_seconds: int = 0
    auto_reconcile_reindex_search: bool = True

    # --- Busca (search) ---
    # Número de resultados por página na busca completa.
    search_page_size: int = 20
    # Máximo de inner_hits (evidências por documento) retornados pelo OpenSearch na query nested.
    # Deve ser >= search_evidences_max_per_hit para exibir todas as ocorrências (ex.: 7 em um PDF).
    search_inner_hits_size: int = 20
    # Máximo de evidências exibidas por documento no tile (após ordenar por página/ocorrência).
    search_evidences_max_per_hit: int = 10
    # Tamanho mínimo do fragmento de highlight (chars). Usado no cálculo dinâmico com o tamanho da query.
    search_highlight_fragment_size_min: int = 180
    # Tamanho máximo do fragmento de highlight (chars).
    search_highlight_fragment_size_max: int = 1200
    # Número de fragmentos de highlight por campo (modo normal).
    search_highlight_number_of_fragments: int = 4
    # Número de fragmentos de highlight em modo strict (query longa).
    search_highlight_number_of_fragments_strict: int = 6

    # --- Autocomplete (suggest) ---
    # Número de sugestões retornadas no autocomplete.
    suggest_size: int = 8
    # Tamanho do fragmento de highlight no suggest (chars).
    suggest_highlight_fragment_size: int = 100
    # Número de fragmentos de highlight por campo no suggest.
    suggest_highlight_number_of_fragments: int = 1

    # --- Extração de documentos ---
    # "all" = indexar o documento inteiro (default). "limit" = interromper extração após extraction_max_chars * 2 (ex.: PDF).
    extraction_mode: str = "all"
    # Usado apenas quando extraction_mode == "limit": limite de caracteres; o extrator de PDF interrompe após ~ extraction_max_chars * 2.
    extraction_max_chars: int = 50000
    # PDF escaneado: se True, páginas com pouco texto extraído (< pdf_ocr_min_chars) passam por OCR (pdf2image + Tesseract).
    pdf_ocr_enabled: bool = True
    # Limiar em caracteres: página com menos que isso é considerada "vazia" e candidata a OCR.
    pdf_ocr_min_chars: int = 50

    # --- Indexação de busca (reindex) ---
    # Se True, no reconcile só reindexa docs novos ou com sha256 alterado; docs inalterados são skip (delete+index apenas por doc_id).
    search_index_incremental_by_sha256: bool = True

    # --- Snippet (evidências e highlights) ---
    # Tamanho total máximo do snippet em caracteres (plain text, sem tags HTML). Regra única para autocomplete e busca.
    snippet_total_max: int = 120

    # --- GET /api/documents (conteúdo para o agente) ---
    # Limite de caracteres (content + content_chunks) retornados por get_document, para caber no contexto do modelo.
    # ~100k chars ≈ 25k tokens; evita estourar contexto (ex.: 128k tokens no gpt-4o). Quando excedido, a resposta é truncada e campos _truncated/_message sinalizam ao modelo e ao usuário.
    get_document_max_chars: int = 100_000

    # --- MCP e LLM (chat / classificação) ---
    # URL do MCP server (streamable HTTP). Ex.: http://localhost:8001/mcp
    mcp_server_url: str = "http://localhost:8001/mcp"
    # Provedor e modelo padrão (usado para chat e classificação se os específicos não forem definidos).
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o-mini"
    # Opcionais: classificação e chat podem usar provedor/modelo distintos.
    classification_llm_provider: str | None = None
    classification_llm_model: str | None = None
    chat_llm_provider: str | None = None
    chat_llm_model: str | None = None
    # Habilitar classificação por LLM no ingest (usa submit_classification via MCP).
    classification_llm_enabled: bool = False
    # CORS: origens permitidas separadas por vírgula. Ex.: http://localhost:5173,http://192.168.1.5:5173
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Channels (messaging) ---
    channels_enabled: bool = False
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    channel_session_timeout_minutes: int = 30
    telegram_mirror_responses: bool = False

    # --- Classification usage ---
    opensearch_classification_usage_index: str = "atlasfile_classification_usage"

    # --- Usage / cost estimation (assistente) ---
    # Path to JSON config with $/1M tokens per provider/model (input, output, cache_read, cache_write).
    # Relative to process cwd (e.g. backend/) or absolute. Example: config/usage_costs.json
    usage_costs_config_path: str = "/workspace/config/usage_costs.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
