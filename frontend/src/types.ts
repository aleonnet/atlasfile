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
}

export interface ChatResponse {
  content: string;
  tool_calls_used: { name: string; result_preview?: string }[];
}
