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

export interface ProjectDocumentType {
  key: string;
  label: string;
  folder?: string | null;
  aliases?: string[];
  extensions?: string[];
  extension_confidence_by_extension?: Record<string, number>;
  fallback_priority?: number;
  detection_rules?: ProjectDocumentTypeDetectionRule[];
}

export interface ProjectDocumentTypeDetectionRule {
  any_of?: string[];
  all_of?: string[];
  with_any_of?: string[];
  exclude_any_of?: string[];
  extensions?: string[];
  confidence: number;
  reason?: string;
}

export interface SearchEvidence {
  location: string;
  snippet: string;
  match_count?: number;
  match_type?: "lexical" | "semantic";
}

export interface SearchHit {
  doc_id: string;
  project_id: string;
  business_domain?: string | null;
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
  document_type?: string | null;
}

export interface SearchResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  hits: SearchHit[];
  search_mode_effective?: "hybrid" | "lexical" | "semantic";
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
  suggested_business_domain?: string;
  suggested_document_type?: string;
  suggested_path?: string;
  confidence_score: number;
  business_domain_confidence?: number | null;
  document_type_confidence?: number | null;
  reason: string;
  top_candidates: Array<{ business_domain?: string; score: number }>;
  top_document_type_candidates?: Array<{ document_type?: string; score: number }>;
  source_path: string;
  metadata_path: string;
  classifier_mode?: string | null;
  classifier_requested_mode?: string | null;
  classifier_fallback_reason?: string | null;
  llm_explanation?: string;
  llm_proposed_business_domain?: string;
  llm_business_domain?: string;
  llm_document_type?: string;
  llm_confidence?: number;
  rule_business_domain?: string;
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
  /** Model that generated this response (e.g. "openai/gpt-4.1") */
  model?: string;
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

/** Token usage and estimated cost for one chat turn. */
export interface TurnUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  api_call_count?: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
  cache_write_input_tokens?: number;
}

export interface ContextPressure {
  context_tokens_estimate: number;
  context_tokens_limit: number;
  context_pressure_ratio: number;
}

export interface ChatResponse {
  content: string;
  tool_calls_used: { name: string; result_preview?: string }[];
  usage?: TurnUsage;
  context_pressure?: ContextPressure;
}

/** Aggregated token usage and cost for a chat session. */
export interface UsageTotals {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  api_call_count?: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
  cache_write_input_tokens?: number;
}

/** Mensagem armazenada (apenas texto; partes de imagem viram "[imagem]" ao persistir). */
export interface StoredChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: number;
  model?: string;
  channel?: string;
}

/** Sessão de chat persistida no backend. */
export interface ChatSession {
  id: string;
  title: string;
  messages: StoredChatMessage[];
  model: string;
  createdAt: number;
  updatedAt: number;
  project_id?: string | null;
  usage_totals?: UsageTotals | null;
  usage_by_model?: Record<string, UsageTotals> | null;
  channel?: string;
  channel_chat_id?: string | null;
}

/** Usage summary by model (tokens and costs by type). */
export interface UsageByModelEntry {
  model: string;
  input_tokens: number;
  output_tokens: number;
  input_cost_usd: number;
  output_cost_usd: number;
  total_tokens: number;
  estimated_cost_usd: number;
  /** false = modelo sem preço cadastrado; o custo exibido seria 0 fabricado. */
  cost_tracked?: boolean;
}

export interface UsageByDayEntry {
  date: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

export interface UsageSummaryResponse {
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_cache_write_tokens: number;
  estimated_cost_usd: number;
  session_count: number;
  total_api_calls: number;
  by_model: UsageByModelEntry[];
  by_day: UsageByDayEntry[];
}

export interface UsageSessionItem {
  id: string;
  title: string;
  project_id?: string | null;
  model: string;
  updatedAt: number;
  usage_totals?: UsageTotals | null;
  usage_by_model?: Record<string, UsageTotals> | null;
  channel?: string;
}

export interface ClassificationUsageByModel {
  model: string;
  call_count: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface ClassificationUsageSummary {
  total_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
  by_model: ClassificationUsageByModel[];
  by_day: UsageByDayEntry[];
}

export interface TrainingUsageByModel {
  model: string;
  call_count: number;
  api_call_count: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface TrainingUsageByScript {
  script_name: string;
  call_count: number;
  api_call_count: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface TrainingUsageSummary {
  total_calls: number;
  total_api_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
  by_model: TrainingUsageByModel[];
  by_script: TrainingUsageByScript[];
  by_day: UsageByDayEntry[];
}

export interface ProfileBusinessDomainFolder {
  business_domain: string;
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
    business_domain_folders?: ProfileBusinessDomainFolder[];
  };
  classification: {
    business_domains?: Array<{
      key: string;
      label?: string | null;
      aliases: string[];
      primary_scope?: string | null;
      subfunction_topics?: string[];
      folder?: string | null;
    }>;
    document_types?: ProjectDocumentType[];
    entity_catalog?: Array<{ type: string; value: string; aliases: string[] }>;
    routing_rules?: RoutingRule[];
    confidence_thresholds?: {
      auto_route_min: number;
      triage_min: number;
    };
    llm_policy?: LLMPolicy;
    operational?: {
      override_mode?: OperationalClassifierMode | null;
    };
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
  business_domain?: string | null;
  title: string;
  original_filename: string;
  canonical_filename: string;
  path: string;
  decision: "auto" | "triage_pending" | "duplicate" | "error" | "moved" | "approved" | "corrected" | "rejected" | "deleted";
  confidence_score: number;
  business_domain_confidence?: number;
  document_type_confidence?: number;
  sha256: string;
  tags: string[];
  document_type?: string;
  topics?: string[];
  topics_source?: string;
  review_status?: string;
  duplicate_of?: string;
  classifier_mode?: string;
  classifier_requested_mode?: string;
  classifier_fallback_reason?: string;
  rule_business_domain?: string;
  rule_confidence?: number;
  llm_explanation?: string;
  llm_proposed_business_domain?: string;
  llm_business_domain?: string;
  llm_document_type?: string;
  llm_confidence?: number;
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

export interface IngestOperationStatus {
  last_run_started_at: string | null;
  last_run_finished_at: string | null;
  duration_seconds: number | null;
  project_id: string | null;
  running: boolean;
  phase: string;
  progress_current: number;
  progress_total: number;
  progress_file: string | null;
  processed_count: number;
  failed_count: number;
  last_error: string | null;
}

export type OperationalClassifierMode = "bootstrap" | "sparse_logreg" | "llm";

export interface ClassifierBenchmarkSummary {
  mode: string;
  role?: string;
  total_labeled: number;
  business_domain_accuracy: number;
  business_domain_macro_f1?: number;
  document_type_accuracy: number;
  document_type_macro_f1?: number;
  exact_match_accuracy: number;
  skipped?: boolean;
  skip_reason?: string[];
  inherited_from_report_id?: string | null;
  training_pool_records?: number;
  validation_records?: number;
  vectorizer?: string | null;
}

export interface ClassifierStatusResponse {
  project_id?: string | null;
  available_modes: OperationalClassifierMode[];
  champion_mode: OperationalClassifierMode;
  fallback_mode: OperationalClassifierMode;
  effective_mode: OperationalClassifierMode;
  override_mode?: OperationalClassifierMode | null;
  promotion_policy: string;
  project_override_allowed: boolean;
  promotion_gates: {
    primary_metric: string;
    min_business_domain_accuracy: number;
    min_document_type_accuracy: number;
    min_exact_match_accuracy: number;
    prefer_current_champion_on_tie: boolean;
  };
  latest_report_id?: string | null;
  champion_report_id?: string | null;
  champion_summary?: ClassifierBenchmarkSummary | null;
  latest_report_summary?: ClassifierBenchmarkSummary | null;
  latest_cycle_status: string;
  latest_cycle_started_at?: string | null;
  latest_cycle_finished_at?: string | null;
  latest_cycle_error?: string | null;
  benchmark_enabled_modes?: string[];
}

export interface ClassifierReportSummary {
  report_id: string;
  generated_at?: string | null;
  operational_classifier_mode?: string | null;
  champion_mode?: string | null;
  champion_summary?: ClassifierBenchmarkSummary | null;
}

export interface ClassifierBenchmarkResultRow {
  file: string;
  expected_business_domain: string;
  predicted_business_domain: string;
  expected_document_type: string;
  predicted_document_type: string;
  business_domain_ok: boolean;
  document_type_ok: boolean;
  exact_ok: boolean;
}

export interface ClassifierReport {
  report_id: string;
  generated_at?: string | null;
  operational_classifier_mode: string;
  dataset_integrity: Record<string, unknown>;
  gates: Record<string, unknown>;
  training_pool_records: number;
  benchmarks: Record<string, { summary: ClassifierBenchmarkSummary; results: ClassifierBenchmarkResultRow[] }>;
  champion?: {
    mode: string;
    summary: ClassifierBenchmarkSummary;
    promotion_policy: string;
  };
  model_artifacts?: Record<string, { path: string }>;
  training_examples_skipped?: string[];
}

export interface ClassifierCycleStatus {
  last_run_started_at: string | null;
  last_run_finished_at: string | null;
  duration_seconds: number | null;
  running: boolean;
  phase: string;
  progress_current: number;
  progress_total: number;
  report_id: string | null;
  champion_mode: string | null;
  last_error: string | null;
  benchmarks?: Record<string, { summary: ClassifierBenchmarkSummary }>;
}

/* ── Search Filters & Stats ── */

export interface SearchFilters {
  doc_kind?: string;
  document_type?: string;
  business_domain?: string;
}

export interface StatsBucket {
  key: string;
  count: number;
}

export interface StatsResponse {
  project_id: string | null;
  total_documents: number;
  by_doc_kind: StatsBucket[];
  by_business_domain: StatsBucket[];
  by_document_type: StatsBucket[];
  by_extension: StatsBucket[];
  by_tags: StatsBucket[];
  by_project_id: StatsBucket[];
}

/* ── LLM Policy ── */

export interface LLMOverrideGuardrails {
  business_domain_override_only_if_rule_confidence_below: number;
  require_explanation: boolean;
  max_business_domain_changes: number;
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

/* ── Upload / Move ── */

export interface UploadedFile {
  filename: string;
  saved_as: string;
}

export interface UploadResult {
  uploaded: UploadedFile[];
}

export interface MoveResult {
  status: string;
  doc_id: string;
  old_path: string;
  new_path: string;
  old_business_domain: string;
  new_business_domain: string;
  old_document_type: string;
  new_document_type: string;
}

/* ── Channels ── */

export interface ChannelConfigTelegram {
  enabled: boolean;
  bot_token: string;
  mirror_responses: boolean;
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

/** Conflito de rótulo por SHA256 (reconciliação — pendente de arbitragem humana). */
export interface LabelConflictSource {
  source: "training_pool" | "validation_set" | "project_tree";
  ref: string;
  business_domain: string;
  document_type: string;
  authoritative: boolean;
}

export interface LabelConflict {
  sha256: string;
  refs: string[];
  canonical_business_domain: string;
  canonical_document_type: string;
  labeled_by: string;
  llm_proposal: {
    business_domain?: string;
    document_type?: string;
    confidence?: number;
    justificativa?: string;
  };
  sources: LabelConflictSource[];
}

export interface DatasetReadinessBlocker {
  code: string;
  message: string;
  params?: Record<string, number>;
}

export interface DatasetReadiness {
  cycle_ready: boolean;
  splits_available: boolean;
  validation: { labeled: number; unlabeled: number };
  training: {
    records: number;
    business_domain_classes: Record<string, number>;
    document_type_classes: Record<string, number>;
  };
  supervised_gate: { eligible: boolean; reasons: string[]; warnings: string[] };
  holdout: { enabled: boolean; modulus: number; min_train_per_class: number };
  blockers: DatasetReadinessBlocker[];
  suggestions: DatasetReadinessBlocker[];
}
