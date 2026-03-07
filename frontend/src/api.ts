import type {
  ChannelConfig,
  ChannelStatusResponse,
  ChatMessage,
  ChatResponse,
  ChatSession,
  IngestHistoryResponse,
  ModelOption,
  LayoutPlanResponse,
  Project,
  ProjectArea,
  ProjectProfileResponse,
  ProjectProfileV2,
  ReconcileStatus,
  ScanResult,
  SearchFilters,
  SearchResponse,
  StatsResponse,
  StoredChatMessage,
  SuggestResponse,
  TemplateData,
  TemplateMeta,
  TriageItem
} from "./types";

const API_BASE =
  import.meta.env.VITE_API_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000");
export const API_URL = API_BASE;

export function getFileDownloadUrl(filePath: string): string {
  return `${API_URL}/api/files/download?path=${encodeURIComponent(filePath)}`;
}

/* ── Setup / Onboarding ── */

export interface SetupStatus {
  app_env: string;
  projects_root: string;
  total_project_dirs: number;
  initialized_projects: number;
  onboarding_suggested: boolean;
}

export async function fetchSetupStatus(): Promise<SetupStatus> {
  const res = await fetch(`${API_URL}/api/setup/status`);
  if (!res.ok) throw new Error("Falha ao verificar status de setup");
  return res.json();
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_URL}/api/projects`);
  if (!res.ok) throw new Error("Falha ao carregar projetos");
  return res.json();
}

export async function initializeProject(projectRef: string, templateSlug?: string): Promise<{ status: string; already_initialized: boolean }> {
  const params = templateSlug ? `?template=${encodeURIComponent(templateSlug)}` : "";
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/initialize${params}`, { method: "POST" });
  if (!res.ok) throw new Error("Falha ao inicializar projeto");
  return res.json();
}

/* ── Templates ── */

export async function listTemplates(): Promise<TemplateMeta[]> {
  const res = await fetch(`${API_URL}/api/templates`);
  if (!res.ok) throw new Error("Falha ao listar templates");
  return res.json();
}

export async function getTemplate(slug: string): Promise<TemplateData> {
  const res = await fetch(`${API_URL}/api/templates/${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error("Template não encontrado");
  return res.json();
}

export async function saveTemplate(slug: string, data: Record<string, unknown>): Promise<TemplateMeta> {
  const res = await fetch(`${API_URL}/api/templates/${encodeURIComponent(slug)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Falha ao salvar template");
  return res.json();
}

export async function createTemplate(data: Record<string, unknown>): Promise<TemplateMeta> {
  const res = await fetch(`${API_URL}/api/templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Falha ao criar template");
  return res.json();
}

export async function deleteTemplate(slug: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/templates/${encodeURIComponent(slug)}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Falha ao excluir template");
}

export async function fetchProjectAreas(projectRef: string): Promise<ProjectArea[]> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/areas`);
  if (!res.ok) throw new Error("Falha ao carregar areas do projeto");
  const data = await res.json();
  return (data.areas || []) as ProjectArea[];
}

export async function fetchProjectProfile(projectRef: string): Promise<ProjectProfileResponse> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/profile`);
  if (!res.ok) throw new Error("Falha ao carregar profile do projeto");
  return res.json();
}

export async function validateProjectProfile(projectRef: string, profile: ProjectProfileV2): Promise<{ valid: boolean; profile: ProjectProfileV2 }> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/profile/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile })
  });
  if (!res.ok) throw new Error("Falha ao validar profile");
  return res.json();
}

export async function updateProjectProfile(
  projectRef: string,
  profile: ProjectProfileV2,
  ifMatchVersion: number,
  updatedBy?: string
): Promise<ProjectProfileResponse> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile,
      if_match_version: ifMatchVersion,
      updated_by: updatedBy
    })
  });
  if (!res.ok) throw new Error("Falha ao salvar profile");
  return res.json();
}

export async function fetchProfileHistory(projectRef: string): Promise<{ entries: Array<{ entry: string; version: number; updated_at: string | null; updated_by: string | null; etag: string }> }> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/profile/history`);
  if (!res.ok) throw new Error("Falha ao carregar histórico de profile");
  return res.json();
}

export async function planProjectLayout(
  projectRef: string,
  profile: ProjectProfileV2,
  options?: { strategy?: "rename_with_suffix" | "skip" | "overwrite"; cleanup_empty_dirs?: boolean }
): Promise<LayoutPlanResponse> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/layout/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile,
      strategy: options?.strategy ?? "rename_with_suffix",
      cleanup_empty_dirs: options?.cleanup_empty_dirs ?? false
    })
  });
  if (!res.ok) throw new Error("Falha ao gerar plano de layout");
  return res.json();
}

export async function applyProjectLayout(
  projectRef: string,
  payload: {
    profile: ProjectProfileV2;
    plan_id: string;
    confirm: boolean;
    strategy?: "rename_with_suffix" | "skip" | "overwrite";
    cleanup_empty_dirs?: boolean;
    if_match_version?: number;
  }
): Promise<{ ok: boolean; plan_id: string; profile_version: number; apply: Record<string, unknown> }> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/layout/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("Falha ao aplicar layout");
  return res.json();
}

export async function triggerScan(projectId: string): Promise<ScanResult> {
  const res = await fetch(`${API_URL}/api/ingest/scan/${projectId}`, { method: "POST" });
  if (!res.ok) throw new Error("Falha ao escanear inbox");
  return res.json();
}

export async function fetchIngestHistory(projectId: string): Promise<IngestHistoryResponse> {
  const res = await fetch(`${API_URL}/api/ingest/history/${encodeURIComponent(projectId)}`);
  if (!res.ok) throw new Error("Falha ao carregar histórico de ingestão");
  return res.json();
}

export async function searchDocuments(
  query: string,
  projectId?: string,
  page = 1,
  size = 20,
  filters?: SearchFilters
): Promise<SearchResponse> {
  const url = new URL(`${API_URL}/api/search`);
  url.searchParams.set("q", query);
  url.searchParams.set("page", String(page));
  url.searchParams.set("size", String(size));
  if (projectId) url.searchParams.set("project_id", projectId);
  if (filters?.doc_kind) url.searchParams.set("doc_kind", filters.doc_kind);
  if (filters?.document_type) url.searchParams.set("document_type", filters.document_type);
  if (filters?.area_key) url.searchParams.set("area_key", filters.area_key);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Falha na busca");
  return res.json();
}

export async function fetchStats(projectId?: string): Promise<StatsResponse> {
  const url = new URL(`${API_URL}/api/stats`);
  if (projectId) url.searchParams.set("project_id", projectId);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Falha ao carregar estatísticas");
  return res.json();
}

export async function fetchSuggestions(query: string, projectId?: string): Promise<SuggestResponse> {
  const url = new URL(`${API_URL}/api/search/suggest`);
  url.searchParams.set("q", query);
  if (projectId) url.searchParams.set("project_id", projectId);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Falha no autocomplete");
  return res.json();
}

export async function fetchTriage(projectId: string): Promise<TriageItem[]> {
  const res = await fetch(`${API_URL}/api/triage/${projectId}`);
  if (!res.ok) throw new Error("Falha ao carregar triagem");
  return res.json();
}

export async function triageDecision(
  projectId: string,
  docId: string,
  action: "approve" | "correct" | "reject",
  targetArea?: string
): Promise<void> {
  const res = await fetch(`${API_URL}/api/triage/${projectId}/${docId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, target_area: targetArea })
  });
  if (!res.ok) throw new Error("Falha ao enviar decisao");
}

export async function runReconcile(projectId?: string): Promise<{
  status: string;
  message?: string;
  summary?: ReconcileStatus["summary"];
}> {
  const url = projectId ? `${API_URL}/api/reconcile/${encodeURIComponent(projectId)}` : `${API_URL}/api/reconcile`;
  const res = await fetch(url, { method: "POST" });
  if (res.status === 409) throw new Error("Reconciliacao ja em andamento");
  if (!res.ok) throw new Error("Falha ao reconciliar");
  return res.json();
}

export async function fetchReconcileStatus(): Promise<ReconcileStatus> {
  const res = await fetch(`${API_URL}/api/reconcile/status`);
  if (!res.ok) throw new Error("Falha ao carregar status de reconciliacao");
  return res.json();
}

/** URL do stream SSE de status de reconcile (Server-Sent Events). */
export function getReconcileStatusStreamUrl(): string {
  return `${API_URL}/api/reconcile/status/stream`;
}

/** Health check: backend GET /health returns 200 when OK. */
export async function fetchHealth(): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_URL}/health`);
  return { ok: res.ok };
}

/** List LLM models (provider/model) for chat. */
export async function fetchModels(): Promise<ModelOption[]> {
  const res = await fetch(`${API_URL}/api/models`);
  if (!res.ok) throw new Error("Falha ao carregar modelos");
  return res.json();
}

/** Send chat message; optional API keys in headers. Returns assistant content and tool_calls_used. */
export async function sendChatMessage(
  messages: ChatMessage[],
  options?: {
    provider?: string;
    model?: string;
    openaiApiKey?: string;
    anthropicApiKey?: string;
    enableThinking?: boolean;
    signal?: AbortSignal;
  }
): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options?.openaiApiKey) headers["X-OpenAI-API-Key"] = options.openaiApiKey;
  if (options?.anthropicApiKey) headers["X-Anthropic-API-Key"] = options.anthropicApiKey;
  const body: { messages: ChatMessage[]; provider?: string; model?: string; enable_thinking?: boolean } = { messages };
  if (options?.provider) body.provider = options.provider;
  if (options?.model) body.model = options.model;
  if (options?.enableThinking === true) body.enable_thinking = true;
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: options?.signal
  });
  if (!res.ok) {
    const t = await res.text();
    try {
      const j = JSON.parse(t) as { detail?: string };
      if (typeof j?.detail === "string") throw new Error(j.detail);
    } catch (e) {
      if (e instanceof Error && e.message !== t) throw e;
    }
    throw new Error(t || "Falha no chat");
  }
  return res.json();
}

/** List chat sessions (optional q for title filter). */
export async function fetchChatSessions(q?: string): Promise<ChatSession[]> {
  const url = new URL(`${API_URL}/api/chat/sessions`);
  if (q?.trim()) url.searchParams.set("q", q.trim());
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Falha ao listar sessões");
  return res.json();
}

/** Get one chat session by id. */
export async function getChatSession(id: string): Promise<ChatSession> {
  const res = await fetch(`${API_URL}/api/chat/sessions/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error("Sessão não encontrada");
  return res.json();
}

/** Create a chat session. */
export async function createChatSession(payload: {
  title: string;
  messages: StoredChatMessage[];
  model: string;
}): Promise<ChatSession> {
  const res = await fetch(`${API_URL}/api/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("Falha ao criar sessão");
  return res.json();
}

/** Update session (title and/or messages). */
export async function updateChatSession(
  id: string,
  payload: { title?: string; messages?: StoredChatMessage[] }
): Promise<ChatSession> {
  const res = await fetch(`${API_URL}/api/chat/sessions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("Falha ao atualizar sessão");
  return res.json();
}

/** Delete a chat session. */
export async function deleteChatSession(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/chat/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Falha ao excluir sessão");
}

/* ── Channels ── */

export async function fetchChannelConfig(): Promise<ChannelConfig> {
  const res = await fetch(`${API_URL}/api/channels/config`);
  if (!res.ok) throw new Error("Falha ao carregar config de canais");
  return res.json();
}

export async function updateChannelConfig(config: ChannelConfig): Promise<ChannelConfig> {
  const res = await fetch(`${API_URL}/api/channels/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error("Falha ao salvar config de canais");
  return res.json();
}

export async function fetchChannelStatus(): Promise<ChannelStatusResponse> {
  const res = await fetch(`${API_URL}/api/channels/status`);
  if (!res.ok) throw new Error("Falha ao carregar status dos canais");
  return res.json();
}
