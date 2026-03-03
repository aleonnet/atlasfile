from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AtlasFile API"
    app_env: str = "dev"

    opensearch_host: str = "http://opensearch:9200"
    opensearch_index: str = "atlasfile_documents"
    opensearch_user: str = "admin"
    opensearch_password: str = "admin123"

    projects_root: str = "/projects"
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
    # Tamanho total máximo do snippet em caracteres (antes + termo + depois). Regra única para autocomplete e busca.
    snippet_total_max: int = 80

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
