from __future__ import annotations

from datetime import datetime
from enum import Enum
import string
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


class OperationalClassifierMode(str, Enum):
    bootstrap = "bootstrap"
    sparse_logreg = "sparse_logreg"
    sparse_linear_svc = "sparse_linear_svc"


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


class BusinessDomainFolder(BaseModel):
    business_domain: str
    folder: str


class LayoutConfig(BaseModel):
    mode: LayoutMode = Field(default=LayoutMode.para_jd)
    roots: LayoutRoots = Field(default_factory=LayoutRoots)
    areas_root: str = Field(default="02_AREAS")
    business_domain_folders: list[BusinessDomainFolder] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_business_domain_folders_unique(self) -> "LayoutConfig":
        domain_keys = [row.business_domain for row in self.business_domain_folders]
        if len(domain_keys) != len(set(domain_keys)):
            dup = sorted({k for k in domain_keys if domain_keys.count(k) > 1})
            raise ValueError(f"layout.business_domain_folders has duplicate business_domain(s): {dup}")
        domain_folders = [row.folder for row in self.business_domain_folders]
        if len(domain_folders) != len(set(domain_folders)):
            dup = sorted({f for f in domain_folders if domain_folders.count(f) > 1})
            raise ValueError(f"layout.business_domain_folders has duplicate folder(s): {dup}")
        return self

    def folder_for_business_domain(self, business_domain: str) -> Optional[str]:
        for row in self.business_domain_folders:
            if row.business_domain == business_domain:
                return row.folder
        return None


class BusinessDomain(BaseModel):
    key: str
    label: str | None = None
    aliases: list[str] = Field(default_factory=list)
    primary_scope: str | None = None
    subfunction_topics: list[str] = Field(default_factory=list)


class DocumentTypeDetectionRule(BaseModel):
    any_of: list[str] = Field(default_factory=list)
    all_of: list[str] = Field(default_factory=list)
    with_any_of: list[str] = Field(default_factory=list)
    exclude_any_of: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    confidence: float
    reason: str = "structural_header"

    @model_validator(mode="after")
    def _validate_rule(self) -> "DocumentTypeDetectionRule":
        if not self.any_of and not self.all_of:
            raise ValueError("document_type.detection_rule must define any_of and/or all_of")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("document_type.detection_rule.confidence must be between 0 and 1")
        return self


class DocumentType(BaseModel):
    key: str
    label: str | None = None
    aliases: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    folder: str
    extension_confidence_by_extension: dict[str, float] = Field(default_factory=dict)
    fallback_priority: int = 100
    detection_rules: list[DocumentTypeDetectionRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_document_type(self) -> "DocumentType":
        for ext, confidence in self.extension_confidence_by_extension.items():
            if not str(ext).strip():
                raise ValueError("document_type.extension_confidence_by_extension keys must not be empty")
            if not (0.0 <= float(confidence) <= 1.0):
                raise ValueError("document_type.extension_confidence_by_extension values must be between 0 and 1")
        if self.fallback_priority < 0:
            raise ValueError("document_type.fallback_priority must be >= 0")
        if not self.folder.strip():
            raise ValueError("document_type.folder is required")
        return self


class KnownEntity(BaseModel):
    type: str
    value: str
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
    business_domain_override_only_if_rule_confidence_below: float = 0.65
    require_explanation: bool = True
    max_business_domain_changes: int = 1

    @model_validator(mode="after")
    def _validate(self) -> "LLMOverrideGuardrails":
        if not (0.0 <= self.business_domain_override_only_if_rule_confidence_below <= 1.0):
            raise ValueError("business_domain_override_only_if_rule_confidence_below must be between 0 and 1")
        if self.max_business_domain_changes < 0:
            raise ValueError("max_business_domain_changes must be >= 0")
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


class ClassificationOperationalConfig(BaseModel):
    override_mode: OperationalClassifierMode | None = None


class ClassificationConfig(BaseModel):
    business_domains: list[BusinessDomain] = Field(default_factory=list)
    document_types: list[DocumentType] = Field(default_factory=list)
    entity_catalog: list[KnownEntity] = Field(default_factory=list)
    routing_rules: list[RoutingRule] = Field(default_factory=list)
    confidence_thresholds: ConfidenceThresholds = Field(default_factory=ConfidenceThresholds)
    llm_policy: LLMPolicy = Field(default_factory=LLMPolicy)
    operational: ClassificationOperationalConfig = Field(default_factory=ClassificationOperationalConfig)

    @model_validator(mode="after")
    def _validate_areas(self) -> "ClassificationConfig":
        domain_keys = [d.key for d in self.business_domains]
        if len(domain_keys) != len(set(domain_keys)):
            dup = sorted({k for k in domain_keys if domain_keys.count(k) > 1})
            raise ValueError(f"classification.business_domains has duplicate key(s): {dup}")

        doc_type_keys = [d.key for d in self.document_types]
        if len(doc_type_keys) != len(set(doc_type_keys)):
            dup = sorted({k for k in doc_type_keys if doc_type_keys.count(k) > 1})
            raise ValueError(f"classification.document_types has duplicate key(s): {dup}")
        if not self.business_domains:
            raise ValueError("classification.business_domains must not be empty")
        if not self.document_types:
            raise ValueError("classification.document_types must not be empty")

        doc_type_folder_keys = [d.folder for d in self.document_types]
        if len(doc_type_folder_keys) != len(set(doc_type_folder_keys)):
            dup = sorted({k for k in doc_type_folder_keys if doc_type_folder_keys.count(k) > 1})
            raise ValueError(f"classification.document_types has duplicate folder(s): {dup}")

        return self

    def business_domain_keys(self) -> list[str]:
        return [d.key for d in self.business_domains]


class NamingConfig(BaseModel):
    canonical_pattern: str = Field(
        default="{date}__{project}__{original_name}",
        description="Pattern for canonical filenames. {original_name} is required.",
    )
    date_format: str = Field(default="%Y%m%d", description="strftime format for {date} field")

    @model_validator(mode="after")
    def _validate_pattern(self) -> "NamingConfig":
        if "{original_name}" not in self.canonical_pattern:
            raise ValueError("canonical_pattern must contain {original_name}")
        fields = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(self.canonical_pattern)
            if field_name
        }
        allowed = {"date", "project", "business_domain", "original_name", "document_type"}
        if "area" in fields:
            raise ValueError("canonical_pattern must use {business_domain} instead of {area}")
        unknown = sorted(fields - allowed)
        if unknown:
            raise ValueError(f"canonical_pattern contains unsupported placeholder(s): {unknown}")
        return self


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
    naming: NamingConfig = Field(default_factory=NamingConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    updated_at: datetime | None = None
    updated_by: str | None = None
    version: int = 1

    @model_validator(mode="after")
    def _cross_validate(self) -> "ProjectProfileV2":
        business_domain_keys = self.classification.business_domain_keys()
        if business_domain_keys:
            missing = [k for k in business_domain_keys if not self.layout.folder_for_business_domain(k)]
            if missing:
                raise ValueError(
                    "layout.business_domain_folders must define a folder for every classification.business_domains key; "
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
