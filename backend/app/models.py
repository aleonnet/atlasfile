from typing import Any, Optional

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    doc_id: str
    project_id: str
    business_domain: str | None = None
    document_type: str | None = None
    original_filename: str
    canonical_filename: str
    path: str
    score: float
    highlights: list[str] = Field(default_factory=list)
    match_locations: list[str] = Field(default_factory=list)
    evidences: list[dict[str, Any]] = Field(default_factory=list)  # [{"location": str, "snippet": str, "match_count": int}]
    total_evidences: int = 0
    omitted_evidences: int = 0
    content_type: str | None = None


class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    hits: list[SearchHit]
    # "hybrid" | "lexical" | "semantic" — modo efetivamente servido (difere do pedido
    # quando o braço semântico está indisponível e a busca degrada para lexical).
    search_mode_effective: str | None = None


class SearchSuggestion(BaseModel):
    doc_id: str
    project_id: str
    original_filename: str
    canonical_filename: str
    path: str
    score: float
    matched_in: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    content_type: str | None = None


class SuggestResponse(BaseModel):
    total: int
    items: list[SearchSuggestion]


class TriageItem(BaseModel):
    doc_id: str
    filename: str
    project_id: str
    suggested_business_domain: Optional[str] = None
    suggested_document_type: Optional[str] = None
    suggested_path: Optional[str] = None
    confidence_score: float
    business_domain_confidence: float | None = None
    document_type_confidence: float | None = None
    reason: str
    top_candidates: list[dict[str, Any]] = Field(default_factory=list)
    top_document_type_candidates: list[dict[str, Any]] = Field(default_factory=list)
    source_path: str
    metadata_path: str
    classifier_mode: str | None = None
    classifier_requested_mode: str | None = None
    classifier_fallback_reason: str | None = None
    llm_explanation: str | None = None
    llm_proposed_business_domain: str | None = None
    rule_business_domain: str | None = None
    rule_confidence: float | None = None


class TriageDecisionRequest(BaseModel):
    action: str  # approve | correct | reject
    target_business_domain: Optional[str] = None
    target_document_type: Optional[str] = None
    note: Optional[str] = None


class DocumentTagsUpdate(BaseModel):
    add: list[str] = Field(default_factory=list, description="Tags to add")
    remove: Optional[list[str]] = Field(default=None, description="Tags to remove (optional)")


class DocumentMetadataUpdate(BaseModel):
    document_type: Optional[str] = None
    correspondent: Optional[str] = None
    business_domain: Optional[str] = None
    review_status: Optional[str] = None


class DocumentMoveRequest(BaseModel):
    target_business_domain: str
    target_document_type: str


class ChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str | list[dict[str, Any]]  # str ou lista multimodal (text + image_url)


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    project_id: str | None = None
    provider: str | None = None  # openai | anthropic; default from config
    model: str | None = None  # override model
    enable_thinking: bool = False  # OpenAI: reasoning_effort; Anthropic: thinking.enabled


class TurnUsage(BaseModel):
    """Token usage and estimated cost for one turn (one chat response)."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    api_call_count: int = 0
    cache_read_input_tokens: Optional[int] = None
    cache_creation_input_tokens: Optional[int] = None
    cache_write_input_tokens: Optional[int] = None


class ContextPressure(BaseModel):
    """Estimated context window pressure for the current session."""
    context_tokens_estimate: int = 0
    context_tokens_limit: int = 0
    context_pressure_ratio: float = 0.0  # 0.0 to 1.0


class ChatResponse(BaseModel):
    content: str
    tool_calls_used: list[dict[str, Any]] = Field(default_factory=list)
    usage: Optional[TurnUsage] = None
    context_pressure: Optional[ContextPressure] = None


class ClassifyRequest(BaseModel):
    doc_id: str
    text_excerpt: str
    filename: str = ""
    provider: str | None = None  # override: openai | anthropic
    model: str | None = None  # override: e.g. gpt-4o-mini


class ClassifyResponse(BaseModel):
    document_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    usage: Optional[TurnUsage] = None


class ClassificationUsageByModel(BaseModel):
    model: str
    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ClassificationUsageSummary(BaseModel):
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    by_model: list[ClassificationUsageByModel] = Field(default_factory=list)
    by_day: list["UsageByDayEntry"] = Field(default_factory=list)


class TrainingUsageByModel(BaseModel):
    model: str
    call_count: int = 0
    api_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class TrainingUsageByScript(BaseModel):
    script_name: str
    call_count: int = 0
    api_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class TrainingUsageSummary(BaseModel):
    total_calls: int = 0
    total_api_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    by_model: list[TrainingUsageByModel] = Field(default_factory=list)
    by_script: list[TrainingUsageByScript] = Field(default_factory=list)
    by_day: list["UsageByDayEntry"] = Field(default_factory=list)


class ModelOption(BaseModel):
    provider: str
    model: str
    label: str  # e.g. "OpenAI gpt-4o-mini (base)"
    context_tokens: int | None = None  # limite de contexto (input) documentado pelo provedor
    max_output_tokens: int | None = None  # limite de tokens de saída por resposta
    supports_reasoning_effort: bool = False  # OpenAI: reasoning_effort; Anthropic: Extended Thinking (doc de cada provedor)
    # Anthropic: "adaptive" (4.6, recomendado) | "enabled" (4.5 e anteriores, budget_tokens). None = não Anthropic ou sem thinking.
    anthropic_thinking_type: str | None = None


# --- Chat sessions (persisted in OpenSearch, separate index) ---


class UsageTotals(BaseModel):
    """Aggregated token usage and cost for a chat session."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    api_call_count: int = 0
    cache_read_input_tokens: Optional[int] = None
    cache_creation_input_tokens: Optional[int] = None
    cache_write_input_tokens: Optional[int] = None


class StoredChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str  # text only; image parts become "[imagem]" when persisting
    timestamp: Optional[int] = None
    model: Optional[str] = None
    channel: Optional[str] = None


class ChatSession(BaseModel):
    id: str
    title: str
    messages: list[StoredChatMessage]
    model: str
    createdAt: int
    updatedAt: int
    project_id: Optional[str] = None
    usage_totals: Optional[UsageTotals] = None
    usage_by_model: Optional[dict[str, UsageTotals]] = None
    channel: Optional[str] = None
    channel_chat_id: Optional[str] = None


class ChatSessionCreate(BaseModel):
    title: str
    messages: list[StoredChatMessage]
    model: str
    project_id: Optional[str] = None
    usage_totals: Optional[UsageTotals] = None
    usage_by_model: Optional[dict[str, UsageTotals]] = None
    channel: str = "web"
    channel_chat_id: Optional[str] = None


class ChatSessionUpdate(BaseModel):
    title: Optional[str] = None
    messages: Optional[list[StoredChatMessage]] = None  # full replace (legado)
    append_messages: Optional[list[StoredChatMessage]] = None  # atomic append
    project_id: Optional[str] = None
    usage_totals: Optional[UsageTotals] = None
    usage_by_model: Optional[dict[str, UsageTotals]] = None
    source_channel: Optional[str] = None  # skip mirror when source matches session channel


# --- Usage aggregation (GET /api/usage/summary, /api/usage/sessions) ---


class UsageByModelEntry(BaseModel):
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class UsageByDayEntry(BaseModel):
    date: str  # YYYY-MM-DD
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class UsageSummaryResponse(BaseModel):
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    estimated_cost_usd: float = 0.0
    session_count: int = 0
    total_api_calls: int = 0
    by_model: list[UsageByModelEntry] = Field(default_factory=list)
    by_day: list[UsageByDayEntry] = Field(default_factory=list)


class UsageSessionItem(BaseModel):
    id: str
    title: str
    project_id: Optional[str] = None
    model: str
    updatedAt: int
    usage_totals: Optional[UsageTotals] = None
    usage_by_model: Optional[dict[str, UsageTotals]] = None
    channel: Optional[str] = None


class StatsBucket(BaseModel):
    key: str
    count: int


class StatsResponse(BaseModel):
    project_id: Optional[str] = None
    total_documents: int = 0
    by_doc_kind: list[StatsBucket] = Field(default_factory=list)
    by_business_domain: list[StatsBucket] = Field(default_factory=list)
    by_document_type: list[StatsBucket] = Field(default_factory=list)
    by_extension: list[StatsBucket] = Field(default_factory=list)
    by_tags: list[StatsBucket] = Field(default_factory=list)
    by_project_id: list[StatsBucket] = Field(default_factory=list)


class ListDocumentItem(BaseModel):
    doc_id: str
    project_id: str
    title: str
    original_filename: str
    path: str
    doc_kind: str | None = None
    document_type: str | None = None
    business_domain: str | None = None
    tags: list[str] = Field(default_factory=list)
    ingested_at: str | None = None


class ListDocumentsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ListDocumentItem]


# --- Channel config / status ---


class ChannelConfigTelegram(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    mirror_responses: bool = False


class ChannelConfigUpdate(BaseModel):
    channels_enabled: bool = False
    telegram: ChannelConfigTelegram = Field(default_factory=ChannelConfigTelegram)


class ChannelStatusItem(BaseModel):
    channel_id: str
    name: str
    running: bool
    connected: bool
    error: str | None = None
    uptime_seconds: float = 0.0


class ChannelStatusResponse(BaseModel):
    channels_enabled: bool
    channels: list[ChannelStatusItem] = Field(default_factory=list)
