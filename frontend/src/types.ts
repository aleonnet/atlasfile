export interface Project {
  project_id: string;
  project_label: string;
  root: string;
  initialized: boolean;
}

export interface ProjectArea {
  key: string;
  label: string;
}

export interface SearchEvidence {
  location: string;
  snippet: string;
  match_count?: number;
}

export interface SearchHit {
  doc_id: string;
  project_id: string;
  area_key: string;
  original_filename: string;
  canonical_filename: string;
  path: string;
  score: number;
  highlights: string[];
  match_locations: string[];
  evidences?: SearchEvidence[];
  total_evidences?: number;
  omitted_evidences?: number;
  content_type?: string | null;
}

export interface SearchResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  hits: SearchHit[];
}

export interface SearchSuggestion {
  doc_id: string;
  project_id: string;
  original_filename: string;
  canonical_filename: string;
  path: string;
  score: number;
  matched_in: string[];
  highlights: string[];
  content_type?: string | null;
}

export interface SuggestResponse {
  total: number;
  items: SearchSuggestion[];
}

export interface ReconcileSummary {
  project_count: number;
  skipped_count: number;
  rows_written: number;
  added_rows: number;
  removed_rows: number;
  adjustments_applied: number;
  indexed_docs: number;
  skipped_docs?: number;
  failed_docs?: number;
  orphan_projects_found?: number;
  orphan_docs_deleted?: number;
}

export interface ReconcileStatus {
  last_run_started_at: string | null;
  last_run_finished_at: string | null;
  duration_seconds: number | null;
  summary: ReconcileSummary;
  running?: boolean;
  phase?: string;
  progress_current?: number;
  progress_total?: number;
  progress_file?: string | null;
  progress_project?: string | null;
  progress_skipped?: number;
  progress_file_pct?: number;
  last_failure_message?: string | null;
  last_failed_doc_id?: string | null;
}

export interface TriageItem {
  doc_id: string;
  filename: string;
  project_id: string;
  suggested_area?: string;
  suggested_path?: string;
  confidence_score: number;
  reason: string;
  top_candidates: { area_key: string; score: number }[];
  source_path: string;
  metadata_path: string;
  llm_explanation?: string;
  llm_proposed_area?: string;
  rule_area_key?: string;
  rule_confidence?: number;
}

/** Parte de conteúdo multimodal (texto ou imagem) enviada ao LLM. */
export type ChatContentPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string | ChatContentPart[];
  /** Timestamp for display (e.g. Date.now()) */
  timestamp?: number;
}

export interface ModelOption {
  provider: string;
  model: string;
  label: string;
  /** Limite de contexto (input) em tokens — documentado pelo provedor */
  context_tokens?: number;
  /** Limite de tokens de saída por resposta */
  max_output_tokens?: number;
  /** OpenAI: reasoning_effort; Anthropic: Extended Thinking — Brain só ativo quando true */
  supports_reasoning_effort?: boolean;
}

export interface ChatResponse {
  content: string;
  tool_calls_used: { name: string; result_preview?: string }[];
}

/** Mensagem armazenada (apenas texto; partes de imagem viram "[imagem]" ao persistir). */
export interface StoredChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: number;
}

/** Sessão de chat persistida no backend. */
export interface ChatSession {
  id: string;
  title: string;
  messages: StoredChatMessage[];
  model: string;
  createdAt: number;
  updatedAt: number;
}

export interface ProfileAreaFolder {
  area_key: string;
  folder: string;
}

export interface ProjectProfileV2 {
  profile_version: 2;
  project_id: string;
  project_label: string;
  project_root: string;
  paths: {
    inbox: string;
    triage: {
      pending: string;
      resolved: string;
      rejected: string;
    };
  };
  layout: {
    mode: "para_jd" | "custom";
    roots: {
      projects: string;
      areas: string;
      resources: string;
      archive: string;
    };
    areas_root: string;
    area_folders: ProfileAreaFolder[];
  };
  classification: {
    work_areas: Array<{ key: string; jd_number?: number | null; aliases: string[] }>;
    routing_rules: RoutingRule[];
    confidence_thresholds: {
      auto_route_min: number;
      triage_min: number;
    };
    llm_policy: LLMPolicy;
  };
  naming?: {
    canonical_pattern?: string;
    date_format?: string;
  };
  indexing: {
    topics_path: string;
    extraction_max_chars: number;
    extraction_mode: "all" | "excerpt";
  };
  updated_at?: string | null;
  updated_by?: string | null;
  version: number;
}

export interface ProjectProfileResponse {
  profile: ProjectProfileV2;
  etag: string;
  version: number;
}

export interface ProfileHistoryEntry {
  entry: string;
  version: number;
  updated_at: string | null;
  updated_by: string | null;
  etag: string;
}

/* ── Routing Rules ── */

export interface RoutingRule {
  when_path_contains?: string[];
  when_filename_contains?: string[];
  route_to: string;
  confidence: number;
}

/* ── Ingest / Scan ── */

export interface ScanFileResult {
  doc_id: string;
  project_id: string;
  area_key: string;
  title: string;
  original_filename: string;
  canonical_filename: string;
  path: string;
  decision: "auto" | "triage_pending" | "duplicate";
  confidence_score: number;
  sha256: string;
  tags: string[];
  document_type?: string;
  topics?: string[];
  topics_source?: string;
  review_status?: string;
  duplicate_of?: string;
  rule_area_key?: string;
  rule_confidence?: number;
  llm_explanation?: string;
  llm_proposed_area?: string;
  classification_reason?: string;
}

export interface ScanResult {
  project_id: string;
  processed_count: number;
  failed_count: number;
  items: ScanFileResult[];
  errors: Array<{ filename: string; path: string; error: string }>;
}

export interface IngestHistoryEntry {
  timestamp: string;
  project_id: string;
  processed_count: number;
  failed_count: number;
  items: ScanFileResult[];
  errors: Array<{ filename: string; path: string; error: string }>;
}

export interface IngestHistoryResponse {
  project_id: string;
  entries: IngestHistoryEntry[];
}

/* ── Search Filters & Stats ── */

export interface SearchFilters {
  doc_kind?: string;
  document_type?: string;
  area_key?: string;
}

export interface StatsBucket {
  key: string;
  count: number;
}

export interface StatsResponse {
  project_id: string | null;
  total_documents: number;
  by_doc_kind: StatsBucket[];
  by_area_key: StatsBucket[];
  by_document_type: StatsBucket[];
  by_extension: StatsBucket[];
  by_tags: StatsBucket[];
  by_project_id: StatsBucket[];
}

/* ── LLM Policy ── */

export interface LLMOverrideGuardrails {
  area_override_only_if_rule_confidence_below: number;
  require_explanation: boolean;
  max_area_changes: number;
}

export interface LLMPolicy {
  enabled: boolean;
  provider: "openai" | "anthropic";
  model: string;
  mode: "tag_only" | "review" | "full_override";
  allow_override_fields: string[];
  override_guardrails: LLMOverrideGuardrails;
}

/* ── Templates ── */

export interface TemplateMeta {
  slug: string;
  name: string;
  description: string;
  areas_count: number;
  created_at: string;
  updated_at: string;
  source: "builtin" | "user";
}

export interface TemplateData extends TemplateMeta {
  profile: ProjectProfileV2;
}

/* ── Layout ── */

export interface LayoutPlan {
  project_root: string;
  from_areas_root: string;
  to_areas_root: string;
  ops: Array<{
    op: "mkdir" | "move" | "skip" | "conflict" | "rmdir_empty" | "rename_dir";
    src?: string | null;
    dst?: string | null;
    reason?: string;
    detail?: Record<string, unknown> | null;
  }>;
  conflicts: number;
  moves: number;
  mkdirs: number;
  renames: number;
  strategy: string;
  cleanup_empty_dirs: boolean;
}

export interface LayoutPlanResponse {
  plan_id: string;
  summary: {
    moves: number;
    conflicts: number;
    mkdirs: number;
    renames: number;
    ops: number;
  };
  plan: LayoutPlan;
}

/* ── Channels ── */

export interface ChannelConfigTelegram {
  enabled: boolean;
  bot_token: string;
}

export interface ChannelConfig {
  channels_enabled: boolean;
  telegram: ChannelConfigTelegram;
}

export interface ChannelStatusItem {
  channel_id: string;
  name: string;
  running: boolean;
  connected: boolean;
  error: string | null;
  uptime_seconds: number;
}

export interface ChannelStatusResponse {
  channels_enabled: boolean;
  channels: ChannelStatusItem[];
}
