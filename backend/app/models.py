from typing import Any, Optional

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    doc_id: str
    project_id: str
    area_key: str
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
    suggested_area: Optional[str] = None
    suggested_path: Optional[str] = None
    confidence_score: float
    reason: str
    top_candidates: list[dict[str, Any]] = Field(default_factory=list)
    source_path: str
    metadata_path: str


class TriageDecisionRequest(BaseModel):
    action: str  # approve | correct | reject
    target_area: Optional[str] = None
    note: Optional[str] = None


class DocumentTagsUpdate(BaseModel):
    add: list[str] = Field(default_factory=list, description="Tags to add")
    remove: Optional[list[str]] = Field(default=None, description="Tags to remove (optional)")


class DocumentMetadataUpdate(BaseModel):
    document_type: Optional[str] = None
    correspondent: Optional[str] = None
    area_key: Optional[str] = None
    review_status: Optional[str] = None


class ChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str | list[dict[str, Any]]  # str ou lista multimodal (text + image_url)


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: str | None = None  # openai | anthropic; default from config
    model: str | None = None  # override model
    enable_thinking: bool = False  # OpenAI: reasoning_effort; Anthropic: thinking.enabled


class ChatResponse(BaseModel):
    content: str
    tool_calls_used: list[dict[str, Any]] = Field(default_factory=list)


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


class StoredChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str  # text only; image parts become "[imagem]" when persisting
    timestamp: Optional[int] = None


class ChatSession(BaseModel):
    id: str
    title: str
    messages: list[StoredChatMessage]
    model: str
    createdAt: int
    updatedAt: int


class ChatSessionCreate(BaseModel):
    title: str
    messages: list[StoredChatMessage]
    model: str


class ChatSessionUpdate(BaseModel):
    title: Optional[str] = None
    messages: Optional[list[StoredChatMessage]] = None  # full replacement when appending


class StatsBucket(BaseModel):
    key: str
    count: int


class StatsResponse(BaseModel):
    project_id: Optional[str] = None
    total_documents: int = 0
    by_doc_kind: list[StatsBucket] = Field(default_factory=list)
    by_area_key: list[StatsBucket] = Field(default_factory=list)
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
    area_key: str | None = None
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
