/** Factory única de query keys — nunca strings soltas em componentes.
 *
 *  Convenção: [recurso, projectId?, params?]. Chaves de recursos escopados por
 *  projeto SEMPRE carregam o projectId — trocar de projeto segrega o cache
 *  naturalmente, sem invalidation manual. Invalidations usam prefixos:
 *  `invalidateQueries({ queryKey: qk.triage.scope() })` derruba todas as filas.
 */
export const qk = {
  // ── Globais (sem projeto) ──
  health: () => ["health"] as const,
  setupStatus: () => ["setup-status"] as const,
  projects: () => ["projects"] as const,
  models: () => ["models"] as const,
  modelCatalog: () => ["model-catalog"] as const,
  catalogConfig: () => ["catalog-config"] as const,
  templates: {
    scope: () => ["templates"] as const,
    list: () => ["templates", "list"] as const,
    detail: (slug: string) => ["templates", "detail", slug] as const,
  },
  taxonomy: () => ["taxonomy"] as const,
  labelConflicts: () => ["label-conflicts"] as const,
  reconcileStatus: () => ["reconcile-status"] as const,
  ingestStatus: () => ["ingest-status"] as const,
  decisionStatus: () => ["decision-status"] as const,
  channelStatus: () => ["channel-status"] as const,
  channelConfig: () => ["channel-config"] as const,
  classifier: {
    scope: () => ["classifier"] as const,
    status: (projectId: string | undefined) => ["classifier", "status", projectId ?? null] as const,
    reports: () => ["classifier", "reports"] as const,
    reportLatest: () => ["classifier", "report-latest"] as const,
    cycleStatus: () => ["classifier", "cycle-status"] as const,
    datasetReadiness: () => ["classifier", "dataset-readiness"] as const,
  },

  // ── Escopados por projeto ──
  stats: (projectId?: string) => ["stats", projectId ?? null] as const,
  triage: {
    scope: () => ["triage"] as const,
    list: (projectId: string) => ["triage", projectId] as const,
    rejected: (projectId: string) => ["triage", projectId, "rejected"] as const,
  },
  inboxFiles: (projectId: string) => ["inbox-files", projectId] as const,
  ingestHistory: (projectId: string) => ["ingest-history", projectId] as const,
  profile: (projectRef: string) => ["profile", projectRef] as const,
  profileHistory: (projectRef: string) => ["profile-history", projectRef] as const,
  search: (projectId: string | undefined, params: Record<string, unknown>) =>
    ["search", projectId ?? null, params] as const,
  chatSessions: (projectId: string | undefined) => ["chat-sessions", projectId ?? null] as const,
  usage: {
    scope: () => ["usage"] as const,
    summary: (projectId: string | undefined, params: Record<string, unknown>) =>
      ["usage", "summary", projectId ?? null, params] as const,
    sessions: (projectId: string | undefined, params: Record<string, unknown>) =>
      ["usage", "sessions", projectId ?? null, params] as const,
    classification: (projectId: string | undefined, params: Record<string, unknown>) =>
      ["usage", "classification", projectId ?? null, params] as const,
    training: (params: Record<string, unknown>) => ["usage", "training", params] as const,
  },
} as const;
