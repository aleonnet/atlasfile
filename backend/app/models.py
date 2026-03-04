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
