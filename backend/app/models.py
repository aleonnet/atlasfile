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
