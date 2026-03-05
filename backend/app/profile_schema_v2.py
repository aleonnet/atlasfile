from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class LayoutMode(str, Enum):
    para_jd = "para_jd"
    custom = "custom"


class LLMProvider(str, Enum):
    openai = "openai"
    anthropic = "anthropic"


class LLMMode(str, Enum):
    tag_only = "tag_only"
    review = "review"
    full_override = "full_override"


class ProjectPathsTriage(BaseModel):
    pending: str = Field(default="_TRIAGE_REVIEW/pending")
    resolved: str = Field(default="_TRIAGE_REVIEW/resolved")
    rejected: str = Field(default="_TRIAGE_REVIEW/rejected")


class ProjectPaths(BaseModel):
    inbox: str = Field(default="_INBOX_DROP")
    triage: ProjectPathsTriage = Field(default_factory=ProjectPathsTriage)


class LayoutRoots(BaseModel):
    projects: str = Field(default="01_PROJECTS")
    areas: str = Field(default="02_AREAS")
    resources: str = Field(default="03_RESOURCES")
    archive: str = Field(default="04_ARCHIVE")


class AreaFolder(BaseModel):
    area_key: str
    folder: str


class LayoutConfig(BaseModel):
    mode: LayoutMode = Field(default=LayoutMode.para_jd)
    roots: LayoutRoots = Field(default_factory=LayoutRoots)
    areas_root: str = Field(default="02_AREAS")
    area_folders: list[AreaFolder] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_area_folders_unique(self) -> "LayoutConfig":
        keys = [a.area_key for a in self.area_folders]
        if len(keys) != len(set(keys)):
            dup = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError(f"layout.area_folders has duplicate area_key(s): {dup}")
        folders = [a.folder for a in self.area_folders]
        if len(folders) != len(set(folders)):
            dup = sorted({f for f in folders if folders.count(f) > 1})
            raise ValueError(f"layout.area_folders has duplicate folder(s): {dup}")
        return self

    def folder_for_area(self, area_key: str) -> Optional[str]:
        for af in self.area_folders:
            if af.area_key == area_key:
                return af.folder
        return None


class WorkArea(BaseModel):
    key: str
    jd_number: int | None = None
    aliases: list[str] = Field(default_factory=list)


class RoutingRule(BaseModel):
    when_path_contains: list[str] | None = None
    when_filename_contains: list[str] | None = None
    route_to: str
    confidence: float = 0.9

    @model_validator(mode="after")
    def _validate_rule(self) -> "RoutingRule":
        if not self.when_path_contains and not self.when_filename_contains:
            raise ValueError("routing_rule must have when_path_contains and/or when_filename_contains")
        if not self.route_to:
            raise ValueError("routing_rule.route_to is required")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("routing_rule.confidence must be between 0 and 1")
        return self


class ConfidenceThresholds(BaseModel):
    auto_route_min: float = 0.85
    triage_min: float = 0.50

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "ConfidenceThresholds":
        if not (0.0 <= self.triage_min <= self.auto_route_min <= 1.0):
            raise ValueError("thresholds must satisfy 0 <= triage_min <= auto_route_min <= 1")
        return self


class LLMOverrideGuardrails(BaseModel):
    area_override_only_if_rule_confidence_below: float = 0.65
    require_explanation: bool = True
    max_area_changes: int = 1

    @model_validator(mode="after")
    def _validate(self) -> "LLMOverrideGuardrails":
        if not (0.0 <= self.area_override_only_if_rule_confidence_below <= 1.0):
            raise ValueError("area_override_only_if_rule_confidence_below must be between 0 and 1")
        if self.max_area_changes < 0:
            raise ValueError("max_area_changes must be >= 0")
        return self


class LLMPolicy(BaseModel):
    enabled: bool = False
    provider: LLMProvider = LLMProvider.openai
    model: str = "gpt-4.1"
    mode: LLMMode = LLMMode.tag_only
    allow_override_fields: list[str] = Field(
        default_factory=lambda: ["document_type", "tags", "confidence", "topics"]
    )
    override_guardrails: LLMOverrideGuardrails = Field(default_factory=LLMOverrideGuardrails)


class ClassificationConfig(BaseModel):
    work_areas: list[WorkArea] = Field(default_factory=list)
    routing_rules: list[RoutingRule] = Field(default_factory=list)
    confidence_thresholds: ConfidenceThresholds = Field(default_factory=ConfidenceThresholds)
    llm_policy: LLMPolicy = Field(default_factory=LLMPolicy)

    @model_validator(mode="after")
    def _validate_areas(self) -> "ClassificationConfig":
        keys = [a.key for a in self.work_areas]
        if len(keys) != len(set(keys)):
            dup = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError(f"classification.work_areas has duplicate key(s): {dup}")
        return self

    def area_keys(self) -> list[str]:
        return [a.key for a in self.work_areas]


class IndexingConfig(BaseModel):
    topics_path: str = "config/topics_v1.yaml"
    extraction_max_chars: int = 20000
    extraction_mode: Literal["excerpt", "all"] = "excerpt"


class ProjectProfileV2(BaseModel):
    profile_version: Literal[2] = 2
    project_id: str
    project_label: str
    project_root: str
    paths: ProjectPaths = Field(default_factory=ProjectPaths)
    layout: LayoutConfig = Field(default_factory=LayoutConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    updated_at: datetime | None = None
    updated_by: str | None = None
    version: int = 1

    @model_validator(mode="after")
    def _cross_validate(self) -> "ProjectProfileV2":
        area_keys = self.classification.area_keys()
        if area_keys:
            missing = [k for k in area_keys if not self.layout.folder_for_area(k)]
            if missing:
                raise ValueError(
                    "layout.area_folders must define a folder for every classification.work_areas key; "
                    f"missing: {missing}"
                )

        inbox = (self.paths.inbox or "").strip("/")
        triage_roots = [
            (self.paths.triage.pending or "").strip("/"),
            (self.paths.triage.resolved or "").strip("/"),
            (self.paths.triage.rejected or "").strip("/"),
        ]
        areas_root = (self.layout.areas_root or "").strip("/")

        def is_prefix(a: str, b: str) -> bool:
            if not a or not b:
                return False
            a2 = a.rstrip("/") + "/"
            b2 = b.rstrip("/") + "/"
            return b2.startswith(a2) or a2.startswith(b2)

        bad = []
        if is_prefix(inbox, areas_root):
            bad.append(f"layout.areas_root ({areas_root}) overlaps inbox ({inbox})")
        for t in triage_roots:
            if is_prefix(t, areas_root):
                bad.append(f"layout.areas_root ({areas_root}) overlaps triage ({t})")
        if bad:
            raise ValueError("; ".join(bad))
        return self


class ProfileGetResponse(BaseModel):
    profile: ProjectProfileV2
    etag: str
    version: int


class ProfilePutRequest(BaseModel):
    profile: ProjectProfileV2
    if_match_version: int
    updated_by: str | None = None


class ProfilePutResponse(BaseModel):
    profile: ProjectProfileV2
    version: int
    etag: str
