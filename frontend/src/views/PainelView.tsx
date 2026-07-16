import { Database, File, FileSpreadsheet, FileText, FolderOpen, Presentation, RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import { fetchProjectProfile, getFileDownloadUrl, moveDocument } from "../api";
import { MoveDocumentModal } from "../components/MoveDocumentModal";
import { FileUploadZone } from "../features/ingest/FileUploadZone";
import { InboxScanCard } from "../features/ingest/InboxScanCard";
import { IngestHistoryCard } from "../features/ingest/IngestHistoryCard";
import { TriageQueue } from "../features/triage/TriageQueue";
import { buildEvidenceGroups, topLocations } from "../features/search/searchFormatters";
import type {
  Project,
  ProjectArea,
  ProjectDocumentType,
  ReconcileStatus,
  SearchFilters,
  SearchHit,
  StatsResponse,
  TriageItem,
} from "../types";

const ALL_PROJECTS = "__all__";

type InputLikeEvent = { target: { value: string } };
type KeyboardLikeEvent = { key: string };

type Props = {
  projects: Project[];
  selectedProject: string;
  projectLabelById: Map<string, string>;
  triageItems: TriageItem[];
  dashboardStats: StatsResponse | null;
  reconcileStatus: ReconcileStatus | null;
  reconcilingNow: boolean;
  onReconcile: () => void;
  onDecision: (item: TriageItem, action: "approve" | "correct" | "reject") => void;
  onStatus: (msg: string) => void;
  onScanComplete: () => void;
  // Search state & callbacks (owned by App.tsx, shared with SearchModal)
  fullQuery: string;
  fullResults: SearchHit[];
  fullPage: number;
  fullTotalPages: number;
  fullTotal: number;
  fullLoading: boolean;
  fullSearchInput: string;
  searchFilters: SearchFilters;
  searchStats: StatsResponse | null;
  onFullSearchInputChange: (value: string) => void;
  onRunFullSearch: (page?: number, overrideQuery?: string, overrideFilters?: SearchFilters) => void;
  onSearchFiltersChange: (filters: SearchFilters) => void;
  onClearSearch: () => void;
};

function extractFolder(path: string): string {
  const parts = path.split("/").filter(Boolean);
  const workIdx = parts.indexOf("_WORK");
  if (workIdx >= 0 && parts[workIdx + 1]) return parts[workIdx + 1];
  const triageIdx = parts.indexOf("_TRIAGE_REVIEW");
  if (triageIdx >= 0 && parts[triageIdx + 1]) return `_TRIAGE/${parts[triageIdx + 1]}`;
  return parts.length >= 2 ? parts[parts.length - 2] : "-";
}

function cleanSnippetHtml(snippet: string): string {
  return snippet
    .replace(/\[[^\]]+\]\s*/g, "")
    .replace(/\n+/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function bestSnippet(highlights: string[]): string {
  if (!highlights.length) return "Sem trecho destacado para esta busca.";
  const withEmphasis = highlights.find((h) => h.includes("<em>")) || highlights[0];
  return cleanSnippetHtml(withEmphasis);
}

function extractSnippets(highlights: string[]): string[] {
  return [bestSnippet(highlights)];
}

function getDocIcon(contentType?: string | null, filename?: string) {
  const ext = (filename?.split(".").pop() || "").toLowerCase();
  if (contentType === "xlsx" || ["xlsx", "xls", "xlsm", "csv"].includes(ext)) return <FileSpreadsheet size={16} />;
  if (contentType === "pptx" || ["ppt", "pptx"].includes(ext)) return <Presentation size={16} />;
  if (contentType === "docx" || contentType === "pdf" || ["doc", "docx", "pdf", "txt", "md"].includes(ext)) {
    return <FileText size={16} />;
  }
  return <File size={16} />;
}

function highlightTerm(text: string, term: string) {
  const tokens = term
    .trim()
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2);
  if (!tokens.length) return [text];
  const escaped = tokens
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length)
    .join("|");
  const parts = text.split(new RegExp(`(${escaped})`, "ig"));
  return parts.map((part, idx) => {
    const isMatch = tokens.some((token) => token.toLowerCase() === part.toLowerCase());
    return isMatch ? <em key={`${text}-${idx}`}>{part}</em> : part;
  });
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("pt-BR");
}

export function PainelView({
  projects,
  selectedProject,
  projectLabelById,
  triageItems,
  dashboardStats,
  reconcileStatus,
  reconcilingNow,
  onReconcile,
  onDecision,
  onStatus,
  onScanComplete,
  fullQuery,
  fullResults,
  fullPage,
  fullTotalPages,
  fullTotal,
  fullLoading,
  fullSearchInput,
  searchFilters,
  searchStats,
  onFullSearchInputChange,
  onRunFullSearch,
  onSearchFiltersChange,
  onClearSearch,
}: Props) {
  const [moveHit, setMoveHit] = useState<SearchHit | null>(null);
  const [moveSubmitting, setMoveSubmitting] = useState(false);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [moveBdOptions, setMoveBdOptions] = useState<ProjectArea[]>([]);
  const [moveDtOptions, setMoveDtOptions] = useState<ProjectDocumentType[]>([]);

  function renderBreadcrumb(projectId: string, path: string): string {
    const projectLabel = projectLabelById.get(projectId) || projectId;
    return `${projectLabel} > ${extractFolder(path)}`;
  }

  async function openMoveModal(hit: SearchHit) {
    try {
      const resp = await fetchProjectProfile(hit.project_id);
      const classification = resp.profile.classification || {};
      const bds = (classification.business_domains || []).map((d) => ({ key: d.key, label: d.label || d.key }));
      const dts = (classification.document_types || []).map((d) => ({ key: d.key, label: d.label || d.key }));
      if (!bds.length || !dts.length) {
        onStatus("Projeto sem domínios/tipos configurados");
        return;
      }
      setMoveBdOptions(bds);
      setMoveDtOptions(dts);
      setMoveHit(hit);
    } catch {
      onStatus("Falha ao carregar profile para move");
    }
  }

  async function handleMoveConfirm(targetBd: string, targetDt: string) {
    if (!moveHit) return;
    setMoveSubmitting(true);
    setMoveError(null);
    try {
      await moveDocument(moveHit.project_id, moveHit.doc_id, targetBd, targetDt);
      onStatus(`Documento movido para ${targetBd}/${targetDt}`);
      setMoveHit(null);
      setMoveError(null);
      onRunFullSearch(fullPage);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Falha ao mover documento";
      setMoveError(msg);
      onStatus(msg);
    } finally {
      setMoveSubmitting(false);
    }
  }

  const isSingleProject = selectedProject !== ALL_PROJECTS;

  return (
    <>
      <section className="panel panel-control card">
        <div className="panel-head card-header">
          <h2>Painel</h2>
        </div>
        {reconcileStatus?.running ? (
          <div className="reconcile-progress">
            <div className="progress-bar-wrap">
              <div
                className="progress-bar-fill"
                style={{
                  width: `${
                    (reconcileStatus.progress_total ?? 0) > 0
                      ? Math.min(
                          100,
                          (100 *
                            (Math.max(0, (reconcileStatus.progress_current ?? 1) - 1) +
                              (reconcileStatus.progress_file_pct ?? 0) / 100)) /
                            reconcileStatus.progress_total!
                        )
                      : 0
                  }%`,
                }}
              />
            </div>
            <p className="progress-stats">
              {reconcileStatus.progress_current ?? 0} / {reconcileStatus.progress_total ?? 0} docs
              {(reconcileStatus.progress_skipped ?? 0) > 0 && (
                <span className="progress-skip"> (skip: {reconcileStatus.progress_skipped})</span>
              )}
            </p>
            <p className="progress-file">
              Projeto: <strong>{reconcileStatus.progress_project ?? "—"}</strong>
            </p>
            <p className="progress-file sub">
              Arquivo: <span title={reconcileStatus.progress_file ?? ""}>{reconcileStatus.progress_file ? (reconcileStatus.progress_file.length > 60 ? reconcileStatus.progress_file.slice(0, 57) + "..." : reconcileStatus.progress_file) : "—"}</span>
            </p>
          </div>
        ) : (
          <>
          <div className="control-body">
            <div className="control-metrics">
              <div className="stat-big">
                <FolderOpen size={20} />
                <span className="value">{projects.filter(p => p.initialized).length}</span>
                <span className="label">projetos inicializados</span>
                {projects.length > projects.filter(p => p.initialized).length && (
                  <span className="label">/ {projects.length} total</span>
                )}
              </div>
              <div className="stat-big">
                <Database size={20} />
                <span className="value">{dashboardStats?.total_documents ?? 0}</span>
                <span className="label">documentos indexados</span>
              </div>
              <div className="stat-big">
                <span className="value">{triageItems.length}</span>
                <span className="label">pendentes triagem</span>
              </div>
              {(dashboardStats?.by_extension?.length ?? 0) > 0 && (
                <div className="ext-badges">
                  {dashboardStats!.by_extension.map(b => (
                    <span key={b.key} className="ext-badge">{b.key.toUpperCase()} {b.count}</span>
                  ))}
                </div>
              )}
            </div>
            <div className="control-projects">
              {(dashboardStats?.by_project_id?.length ?? 0) > 0 && (
                <div className="mini-table">
                  <div className="mini-row header">
                    <span>Projeto</span>
                    <span>Docs</span>
                  </div>
                  {dashboardStats!.by_project_id.map(b => (
                    <div key={b.key} className="mini-row">
                      <span>{projectLabelById.get(b.key) || b.key}</span>
                      <span>{b.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {isSingleProject && (
            <FileUploadZone
              projectId={selectedProject}
              onUploadComplete={onScanComplete}
              disabled={!isSingleProject}
            />
          )}

          <div className="reconcile-footer">
            <div className="row" style={{ gap: 8, marginBottom: 8 }}>
              <InboxScanCard
                selectedProject={selectedProject}
                projects={projects}
                onStatus={onStatus}
                onScanComplete={onScanComplete}
              />
              <button className="btn primary" disabled={reconcilingNow} onClick={onReconcile}>
                <RefreshCw size={14} className={reconcilingNow ? "spin" : ""} />
                {reconcilingNow ? "Reconciliando..." : "Reconciliar INDEX"}
              </button>
            </div>
            <span>Ultima reconciliacao: <span className="meta-value">{formatTimestamp(reconcileStatus?.last_run_finished_at)}</span></span>
            {(reconcileStatus?.summary.adjustments_applied ?? 0) > 0 && (
              <span>Ajustes: <span className="meta-value">{reconcileStatus!.summary.adjustments_applied}</span></span>
            )}
            {(reconcileStatus?.summary.indexed_docs ?? 0) > 0 && (
              <span>Reindexados: <span className="meta-value">{reconcileStatus!.summary.indexed_docs}</span></span>
            )}
            {(reconcileStatus?.summary.skipped_docs ?? 0) > 0 && (
              <span>Skip: <span className="meta-value">{reconcileStatus!.summary.skipped_docs}</span></span>
            )}
            {(reconcileStatus?.summary.failed_docs ?? 0) > 0 && (
              <span>Falhas: <span className="meta-value">{reconcileStatus!.summary.failed_docs}</span></span>
            )}
            {(reconcileStatus?.summary.orphan_docs_deleted ?? 0) > 0 && (
              <span>Orfaos: <span className="meta-value">{reconcileStatus!.summary.orphan_docs_deleted}</span></span>
            )}
          </div>
          </>
        )}
      </section>

      <TriageQueue
        triageItems={triageItems}
        projectLabelById={projectLabelById}
        onDecision={onDecision}
      />

      {isSingleProject && (
        <IngestHistoryCard
          selectedProject={selectedProject}
          onStatus={onStatus}
        />
      )}

      {fullQuery && (
        <section className="panel card">
          <div className="panel-head panel-head-with-actions">
            <h2>
              <Search size={16} /> Resultados completos
            </h2>
            <div className="panel-head-right">
              <span className="sub">
                {fullTotal} resultado(s)
              </span>
              <button type="button" className="btn search-clear-btn" onClick={onClearSearch} title="Limpar busca">
                Limpar busca
              </button>
            </div>
          </div>

          <div className="full-search-bar">
            <div className="full-search-input-wrap">
              <Search size={16} className="full-search-icon" />
              <input
                className="full-search-input"
                value={fullSearchInput}
                onChange={(e: InputLikeEvent) => onFullSearchInputChange(e.target.value)}
                onKeyDown={(e: KeyboardLikeEvent) => {
                  if (e.key === "Enter") onRunFullSearch(1, fullSearchInput);
                }}
                placeholder="Refinar busca..."
              />
              <button
                className="btn btn-sm"
                disabled={fullLoading || fullSearchInput.trim().length < 2}
                onClick={() => onRunFullSearch(1, fullSearchInput)}
              >
                Buscar
              </button>
            </div>

            {searchStats && (
              <details className="pl-collapsible full-search-filters">
                <summary className="pl-collapsible-header">Filtros</summary>
                <div className="full-search-filters-row">
                  <label className="full-search-filter-label">
                    <span className="sub">Formato</span>
                    <select
                      value={searchFilters.doc_kind || ""}
                      onChange={(e) => {
                        const v = e.target.value || undefined;
                        const next = { ...searchFilters, doc_kind: v };
                        onSearchFiltersChange(next);
                        onRunFullSearch(1, undefined, next);
                      }}
                    >
                      <option value="">Todos</option>
                      {searchStats.by_doc_kind.map((b) => (
                        <option key={b.key} value={b.key}>{b.key} ({b.count})</option>
                      ))}
                    </select>
                  </label>
                  <label className="full-search-filter-label">
                    <span className="sub">Tipo</span>
                    <select
                      value={searchFilters.document_type || ""}
                      onChange={(e) => {
                        const v = e.target.value || undefined;
                        const next = { ...searchFilters, document_type: v };
                        onSearchFiltersChange(next);
                        onRunFullSearch(1, undefined, next);
                      }}
                    >
                      <option value="">Todos</option>
                      {searchStats.by_document_type.map((b) => (
                        <option key={b.key} value={b.key}>{b.key} ({b.count})</option>
                      ))}
                    </select>
                  </label>
                  <label className="full-search-filter-label">
                    <span className="sub">Domínio</span>
                    <select
                      value={searchFilters.business_domain || ""}
                      onChange={(e) => {
                        const v = e.target.value || undefined;
                        const next = { ...searchFilters, business_domain: v };
                        onSearchFiltersChange(next);
                        onRunFullSearch(1, undefined, next);
                      }}
                    >
                      <option value="">Todas</option>
                      {searchStats.by_business_domain.map((b) => (
                        <option key={b.key} value={b.key}>{b.key} ({b.count})</option>
                      ))}
                    </select>
                  </label>
                </div>
              </details>
            )}
          </div>

          <ul className="list search-list">
            {fullResults.map((hit) => (
              <li key={`full-${hit.doc_id}`} className="list-item search-item">
                <div className="search-item-content">
                  <div className="sub breadcrumb-line">{renderBreadcrumb(hit.project_id, hit.path)}</div>
                  <div className="title-row">
                    <span className="doc-icon-inline">{getDocIcon(hit.content_type, hit.original_filename)}</span>
                    <a className="result-link result-title" href={getFileDownloadUrl(hit.path)} target="_blank" rel="noreferrer">
                      {highlightTerm(hit.original_filename, fullQuery)}
                    </a>
                    <button
                      type="button"
                      className="btn btn-sm"
                      style={{ marginLeft: "auto", fontSize: "0.72rem" }}
                      onClick={() => openMoveModal(hit)}
                    >
                      Mover
                    </button>
                  </div>
                  {hit.evidences && hit.evidences.length > 0 ? (
                    <>
                      {buildEvidenceGroups(hit.evidences ?? []).map((group, i: number) => (
                        <div key={`evg-${hit.doc_id}-${group.key}-${i}`} className="evidence">
                          <span className="evidence-location sub">
                            {group.label}
                            {group.semantic && <span className="evidence-badge-semantic">semântico</span>}
                          </span>
                          {group.snippets.map((snippet, j) => (
                            <div
                              key={`evg-${hit.doc_id}-${group.key}-${j}`}
                              className="snippet"
                              dangerouslySetInnerHTML={{ __html: snippet }}
                            />
                          ))}
                        </div>
                      ))}
                      {Number(hit.omitted_evidences) > 0 && (
                        <div className="sub">+ {hit.omitted_evidences} outro(s) trecho(s)</div>
                      )}
                    </>
                  ) : (
                    <>
                      {extractSnippets(hit.highlights).map((snippet, idx) => (
                        <div key={`full-${hit.doc_id}-snippet-${idx}`} className="snippet" dangerouslySetInnerHTML={{ __html: snippet }} />
                      ))}
                      {topLocations(hit.match_locations).length > 0 && (
                        <div className="sub">Local: {topLocations(hit.match_locations).join(" | ")}</div>
                      )}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <div className="search-modal-footer">
            <span className="sub">
              pagina {fullPage}/{fullTotalPages}
            </span>
            <div className="row">
              <button className="btn" disabled={fullLoading || fullPage <= 1} onClick={() => onRunFullSearch(fullPage - 1)}>
                Anterior
              </button>
              <button className="btn" disabled={fullLoading || fullPage >= fullTotalPages} onClick={() => onRunFullSearch(fullPage + 1)}>
                Proxima
              </button>
            </div>
          </div>
        </section>
      )}

      {moveHit && (
        <MoveDocumentModal
          open={!!moveHit}
          filename={moveHit.original_filename}
          currentBusinessDomain={moveHit.business_domain || ""}
          currentDocumentType={moveHit.document_type || ""}
          businessDomainOptions={moveBdOptions}
          documentTypeOptions={moveDtOptions}
          submitting={moveSubmitting}
          errorMessage={moveError}
          onCancel={() => { setMoveHit(null); setMoveError(null); }}
          onConfirm={handleMoveConfirm}
        />
      )}
    </>
  );
}
