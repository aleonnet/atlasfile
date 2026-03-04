import type {
  ChatMessage,
  ChatResponse,
  ModelOption,
  Project,
  ProjectArea,
  ReconcileStatus,
  SearchResponse,
  SuggestResponse,
  TriageItem
} from "./types";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function getFileDownloadUrl(filePath: string): string {
  return `${API_URL}/api/files/download?path=${encodeURIComponent(filePath)}`;
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_URL}/api/projects`);
  if (!res.ok) throw new Error("Falha ao carregar projetos");
  return res.json();
}

export async function initializeProject(projectRef: string): Promise<{ status: string; already_initialized: boolean }> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/initialize`, { method: "POST" });
  if (!res.ok) throw new Error("Falha ao inicializar projeto");
  return res.json();
}

export async function fetchProjectAreas(projectRef: string): Promise<ProjectArea[]> {
  const res = await fetch(`${API_URL}/api/projects/${encodeURIComponent(projectRef)}/areas`);
  if (!res.ok) throw new Error("Falha ao carregar areas do projeto");
  const data = await res.json();
  return (data.areas || []) as ProjectArea[];
}

export async function triggerScan(projectId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/ingest/scan/${projectId}`, { method: "POST" });
  if (!res.ok) throw new Error("Falha ao escanear inbox");
}

export async function searchDocuments(query: string, projectId?: string, page = 1, size = 20): Promise<SearchResponse> {
  const url = new URL(`${API_URL}/api/search`);
  url.searchParams.set("q", query);
  url.searchParams.set("page", String(page));
  url.searchParams.set("size", String(size));
  if (projectId) url.searchParams.set("project_id", projectId);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Falha na busca");
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
    throw new Error(t || "Falha no chat");
  }
  return res.json();
}
