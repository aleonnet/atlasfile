import type { Project, ProjectArea, ReconcileStatus, SearchResponse, SuggestResponse, TriageItem } from "./types";

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
