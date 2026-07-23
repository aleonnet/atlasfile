import { Database, File, FileSpreadsheet, FileText, FolderOpen, Inbox, LayoutDashboard, Presentation, RefreshCw, Search, X } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import { fetchProjectProfile, getFileDownloadUrl, moveDocument } from "../api";
import { MoveDocumentModal } from "../components/MoveDocumentModal";
import { AnimatedNumber } from "../components/ui/animated-number";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { Input } from "../components/ui/input";
import { StatTile } from "../components/ui/stat-tile";
import { InboxQueueChips } from "../features/ingest/InboxQueueChips";
import { InboxScanCard } from "../features/ingest/InboxScanCard";
import { IngestHistoryCard } from "../features/ingest/IngestHistoryCard";
import { DropHintCard } from "../features/ingest/DropHintCard";
import { LabelConflictsCard } from "../features/triage/LabelConflictsCard";
import { RejectedCard } from "../features/triage/RejectedCard";
import { TriageQueue } from "../features/triage/TriageQueue";
import { buildEvidenceGroups, topLocations } from "../features/search/searchFormatters";
import { cn } from "../lib/utils";
import { formatDate } from "../lib/format";
import { invalidateAfterMove } from "../lib/mutations";
import { useProcessing } from "../contexts/ProcessingContext";
import { usePainelSearch } from "../hooks/usePainelSearch";
import type {
  Project,
  ProjectArea,
  ProjectDocumentType,
  ReconcileStatus,
  SearchFilters,
  SearchHit,
  StatsResponse,
  StatusSeverity,
  TriageItem,
} from "../types";

const ALL_PROJECTS = "__all__";

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
  onStatus: (msg: string, severity?: StatusSeverity) => void;
  onScanComplete: () => void;

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
  if (!highlights.length) return i18n.t("painel:results.noHighlightedSnippet");
  const withEmphasis = highlights.find((h) => h.includes("<em>")) || highlights[0];
  return cleanSnippetHtml(withEmphasis);
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
  return formatDate(parsed, { dateStyle: "short", timeStyle: "medium" });
}

/** Chips de facet — filtros clicáveis com contagem (substituem os <select>). */
function FacetChips({
  label,
  buckets,
  active,
  onSelect,
}: {
  label: string;
  buckets: Array<{ key: string; count: number }>;
  active: string | undefined;
  onSelect: (value: string | undefined) => void;
}) {
  const { t } = useTranslation();
  if (!buckets.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="w-16 shrink-0 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">{label}</span>
      <button
        type="button"
        onClick={() => onSelect(undefined)}
        className={cn(
          "rounded-full border-0 px-2.5 py-0.5 font-mono text-[0.7rem] shadow-none transition-colors",
          !active ? "bg-accent-soft text-accent" : "bg-panel-strong text-muted-foreground hover:text-foreground"
        )}
      >
        {t("painel:results.facetAll")}
      </button>
      {buckets.map((bucket) => (
        <button
          key={bucket.key}
          type="button"
          onClick={() => onSelect(active === bucket.key ? undefined : bucket.key)}
          className={cn(
            "rounded-full border-0 px-2.5 py-0.5 font-mono text-[0.7rem] shadow-none transition-colors",
            active === bucket.key
              ? "bg-accent-soft text-accent shadow-[inset_0_0_0_1px_var(--accent-soft)]"
              : "bg-panel-strong text-muted-foreground hover:text-foreground"
          )}
        >
          {bucket.key} <span className="text-tertiary">{bucket.count}</span>
        </button>
      ))}
    </div>
  );
}

/** Tile de resultado com aura por match_type: semântico = púrpura, lexical = accent. */
function ResultTile({
  hit,
  query,
  breadcrumb,
  onMove,
  index,
}: {
  hit: SearchHit;
  query: string;
  breadcrumb: string;
  onMove: (hit: SearchHit) => void;
  index: number;
}) {
  const { t } = useTranslation();
  const reducedMotion = useReducedMotion();
  const groups = buildEvidenceGroups(hit.evidences ?? []);
  const hasSemantic = groups.some((g) => g.semantic);

  return (
    <motion.li
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1], delay: Math.min(index * 0.03, 0.3) }}
      className={cn(
        "group relative rounded-lg border bg-card p-4 transition-[border-color,box-shadow] duration-200",
        hasSemantic
          ? "border-accent-purple/25 shadow-[0_0_20px_rgba(201,123,255,0.07)] hover:border-accent-purple/50 hover:shadow-[0_0_28px_rgba(201,123,255,0.14)]"
          : "border-border hover:border-accent/40 hover:shadow-[0_0_20px_var(--accent-soft)]"
      )}
    >
      <div className="mb-1 truncate font-mono text-[0.68rem] text-tertiary">{breadcrumb}</div>
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-muted-foreground">{getDocIcon(hit.content_type, hit.original_filename)}</span>
        <a
          className="min-w-0 flex-1 truncate font-display text-sm font-semibold text-foreground-strong no-underline hover:text-accent hover:underline [&_em]:not-italic [&_em]:text-accent"
          href={getFileDownloadUrl(hit.path)}
          target="_blank"
          rel="noreferrer"
        >
          {highlightTerm(hit.original_filename, query)}
        </a>
        <Button
          variant="ghost"
          size="sm"
          className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
          onClick={() => onMove(hit)}
        >
          {t("painel:results.move")}
        </Button>
      </div>
      {groups.length > 0 ? (
        <div className="mt-2 space-y-2">
          {groups.map((group, i) => (
            <div key={`evg-${hit.doc_id}-${group.key}-${i}`}>
              <span className="flex items-center gap-1.5 font-mono text-[0.68rem] text-tertiary">
                {group.label}
                {group.semantic && <Badge variant="purple">{t("painel:results.semanticBadge")}</Badge>}
              </span>
              {group.snippets.map((snippet, j) => (
                <div
                  key={`evg-${hit.doc_id}-${group.key}-${j}`}
                  className="mt-0.5 text-[0.82rem] leading-relaxed text-foreground [&_em]:not-italic [&_em]:font-bold [&_em]:text-accent"
                  dangerouslySetInnerHTML={{ __html: snippet }}
                />
              ))}
            </div>
          ))}
          {Number(hit.omitted_evidences) > 0 && (
            <div className="font-mono text-[0.68rem] text-tertiary">
              {t("painel:results.omittedEvidences", { count: Number(hit.omitted_evidences) })}
            </div>
          )}
        </div>
      ) : (
        <div className="mt-2">
          <div
            className="text-[0.82rem] leading-relaxed text-foreground [&_em]:not-italic [&_em]:font-bold [&_em]:text-accent"
            dangerouslySetInnerHTML={{ __html: bestSnippet(hit.highlights) }}
          />
          {topLocations(hit.match_locations).length > 0 && (
            <div className="mt-1 font-mono text-[0.68rem] text-tertiary">
              {t("painel:results.location", { locations: topLocations(hit.match_locations).join(" | ") })}
            </div>
          )}
        </div>
      )}
    </motion.li>
  );
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
}: Props) {
  const { t } = useTranslation();
  // Busca completa: o Painel é o dono (padrão benchmark) — resultados no cache,
  // handoff da paleta chega via intent de navegação
  const {
    fullQuery,
    fullResults,
    fullPage,
    fullTotalPages,
    fullTotal,
    fullLoading,
    fullSearchInput,
    searchFilters,
    searchStats,
    setFullSearchInput: onFullSearchInputChange,
    runFullSearch: onRunFullSearch,
    setSearchFilters: onSearchFiltersChange,
    clearSearch: onClearSearch,
  } = usePainelSearch({ onStatus });
  const { active: processingOp } = useProcessing();
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
        onStatus(t("painel:moveModal.noTaxonomy"), "error");
        return;
      }
      setMoveBdOptions(bds);
      setMoveDtOptions(dts);
      setMoveHit(hit);
    } catch {
      onStatus(t("painel:moveModal.loadProfileFailed"), "error");
    }
  }

  async function handleMoveConfirm(targetBd: string, targetDt: string) {
    if (!moveHit) return;
    setMoveSubmitting(true);
    setMoveError(null);
    try {
      await moveDocument(moveHit.project_id, moveHit.doc_id, targetBd, targetDt);
      onStatus(t("painel:moveModal.moved", { businessDomain: targetBd, documentType: targetDt }));
      setMoveHit(null);
      setMoveError(null);
      invalidateAfterMove();
      onRunFullSearch(fullPage);
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("painel:moveModal.moveFailed");
      setMoveError(msg);
      onStatus(msg, "error");
    } finally {
      setMoveSubmitting(false);
    }
  }

  const isSingleProject = selectedProject !== ALL_PROJECTS;
  const initializedCount = projects.filter((p) => p.initialized).length;

  function applyFilter(patch: Partial<SearchFilters>) {
    const next = { ...searchFilters, ...patch };
    onSearchFiltersChange(next);
    onRunFullSearch(1, undefined, next);
  }

  return (
    <div className="relative">
      {/* Scrim de processamento: decisão em série é a regra — o resto do Painel
          esmaece e bloqueia cliques; o card focal (z-40) fica acima, vivo */}
      {processingOp && (
        <div
          aria-hidden
          className="absolute inset-0 z-30 cursor-wait rounded-lg bg-background/55 backdrop-blur-[1px]"
          onClick={(e) => e.stopPropagation()}
        />
      )}
      <Card>
        <CardHeader>
          <CardTitle className="flex min-h-9 items-center gap-2">
            <LayoutDashboard className="size-4 text-accent" aria-hidden />
            {t("painel:card.title")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {reconcileStatus?.running ? (
            <div className="space-y-2">
              <div className="h-1.5 overflow-hidden rounded-full bg-panel-strong">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-accent to-accent-light shadow-[0_0_12px_var(--accent-soft)] transition-[width] duration-500"
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
              <p className="font-display text-sm font-semibold text-foreground-strong">
                {t("painel:card.reconcileProgress", {
                  current: reconcileStatus.progress_current ?? 0,
                  total: reconcileStatus.progress_total ?? 0,
                })}
                {(reconcileStatus.progress_skipped ?? 0) > 0 && (
                  <span className="ml-1 font-normal text-muted-foreground">
                    {t("painel:card.reconcileSkipped", { count: reconcileStatus.progress_skipped })}
                  </span>
                )}
              </p>
              <p className="text-xs text-muted-foreground">
                {t("painel:card.projectLabel")} <strong className="text-foreground">{reconcileStatus.progress_project ?? "—"}</strong>
              </p>
              <p className="truncate font-mono text-[0.7rem] text-tertiary">
                {t("painel:card.fileLabel")} <span title={reconcileStatus.progress_file ?? ""}>{reconcileStatus.progress_file ?? "—"}</span>
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-3 lg:grid-cols-[1fr_minmax(260px,0.8fr)]">
                <div className="grid gap-3 sm:grid-cols-3">
                  <StatTile
                    icon={<FolderOpen aria-hidden />}
                    value={initializedCount}
                    label={t("painel:card.statProjects")}
                    hint={projects.length > initializedCount ? t("painel:card.statProjectsHint", { total: projects.length }) : undefined}
                  />
                  <StatTile
                    icon={<Database aria-hidden />}
                    value={dashboardStats?.total_documents ?? 0}
                    label={t("painel:card.statDocuments")}
                  />
                  <StatTile icon={<Inbox aria-hidden />} value={triageItems.length} label={t("painel:card.statTriage")} />
                </div>
                {(dashboardStats?.by_project_id?.length ?? 0) > 0 && (
                  <div className="mini-table overflow-hidden rounded-lg border border-border">
                    <div className="mini-row header grid grid-cols-[1fr_auto] gap-2 border-b border-border bg-panel-strong px-3 py-1.5 font-mono text-[0.68rem] uppercase tracking-wide text-tertiary">
                      <span>{t("painel:card.tableProject")}</span>
                      <span>{t("painel:card.tableDocs")}</span>
                    </div>
                    {dashboardStats!.by_project_id.map((b) => (
                      <div
                        key={b.key}
                        className="mini-row grid grid-cols-[1fr_auto] gap-2 border-b border-border px-3 py-1.5 text-xs last:border-b-0"
                      >
                        <span className="truncate">{projectLabelById.get(b.key) || b.key}</span>
                        <span className="font-mono text-muted-foreground">{b.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {(dashboardStats?.by_extension?.length ?? 0) > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {dashboardStats!.by_extension.map((b) => (
                    <span
                      key={b.key}
                      className="rounded-md border border-border bg-panel-strong px-2 py-0.5 font-mono text-[0.7rem] text-muted-foreground"
                    >
                      {b.key.toUpperCase()} {b.count}
                    </span>
                  ))}
                </div>
              )}

              {isSingleProject && (
                <InboxQueueChips projectId={selectedProject} onStatus={onStatus} />
              )}

              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-4">
                <div className="flex items-center gap-2">
                  <InboxScanCard
                    selectedProject={selectedProject}
                    projects={projects}
                    onStatus={onStatus}
                    onScanComplete={onScanComplete}
                  />
                  <Button disabled={reconcilingNow} onClick={onReconcile}>
                    <RefreshCw className={reconcilingNow ? "animate-spin" : ""} />
                    {reconcilingNow ? t("painel:card.reconciling") : t("painel:card.reconcileButton")}
                  </Button>
                </div>
                <span className="text-xs text-muted-foreground">
                  {t("painel:card.lastReconcile")}{" "}
                  <strong className="text-foreground">{formatTimestamp(reconcileStatus?.last_run_finished_at)}</strong>
                </span>
                {(reconcileStatus?.summary.adjustments_applied ?? 0) > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {t("painel:card.adjustments")} <strong className="text-foreground">{reconcileStatus!.summary.adjustments_applied}</strong>
                  </span>
                )}
                {(reconcileStatus?.summary.indexed_docs ?? 0) > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {t("painel:card.reindexed")} <strong className="text-foreground">{reconcileStatus!.summary.indexed_docs}</strong>
                  </span>
                )}
                {(reconcileStatus?.summary.skipped_docs ?? 0) > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {t("painel:card.skip")} <strong className="text-foreground">{reconcileStatus!.summary.skipped_docs}</strong>
                  </span>
                )}
                {(reconcileStatus?.summary.failed_docs ?? 0) > 0 && (
                  <span className="text-xs text-destructive">
                    {t("painel:card.failures")} <strong>{reconcileStatus!.summary.failed_docs}</strong>
                  </span>
                )}
                {(reconcileStatus?.summary.orphan_docs_deleted ?? 0) > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {t("painel:card.orphans")} <strong className="text-foreground">{reconcileStatus!.summary.orphan_docs_deleted}</strong>
                  </span>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <TriageQueue triageItems={triageItems} projectLabelById={projectLabelById} onDecision={onDecision} />

      <LabelConflictsCard />

      {triageItems.length === 0 && <DropHintCard />}

      {isSingleProject && (
        <RejectedCard projectId={selectedProject} onStatus={onStatus} onChanged={onScanComplete} />
      )}

      {isSingleProject && <IngestHistoryCard selectedProject={selectedProject} onStatus={onStatus} />}

      {fullQuery && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2">
              <Search size={15} className="text-accent" aria-hidden />
              {t("painel:results.title")}
              <span className="font-mono text-xs font-normal text-tertiary">{t("painel:results.count", { count: fullTotal })}</span>
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={onClearSearch}>
              <X />
              {t("painel:results.clearSearch")}
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-tertiary" aria-hidden />
                <Input
                  className="pl-9"
                  value={fullSearchInput}
                  onChange={(e) => onFullSearchInputChange(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onRunFullSearch(1, fullSearchInput);
                  }}
                  placeholder={t("painel:results.refinePlaceholder")}
                />
              </div>
              <Button
                variant="secondary"
                disabled={fullLoading || fullSearchInput.trim().length < 2}
                onClick={() => onRunFullSearch(1, fullSearchInput)}
              >
                {t("painel:results.searchButton")}
              </Button>
            </div>

            {searchStats && (
              <div className="space-y-1.5">
                <FacetChips
                  label={t("painel:results.facetFormat")}
                  buckets={searchStats.by_doc_kind}
                  active={searchFilters.doc_kind}
                  onSelect={(v) => applyFilter({ doc_kind: v })}
                />
                <FacetChips
                  label={t("painel:results.facetType")}
                  buckets={searchStats.by_document_type}
                  active={searchFilters.document_type}
                  onSelect={(v) => applyFilter({ document_type: v })}
                />
                <FacetChips
                  label={t("painel:results.facetDomain")}
                  buckets={searchStats.by_business_domain}
                  active={searchFilters.business_domain}
                  onSelect={(v) => applyFilter({ business_domain: v })}
                />
              </div>
            )}

            {fullResults.length === 0 && !fullLoading ? (
              <EmptyState
                icon={<Search aria-hidden />}
                title={t("painel:results.emptyTitle")}
                description={t("painel:results.emptyDescription", { query: fullQuery })}
              />
            ) : (
              <ul className="m-0 list-none space-y-2.5 p-0">
                {fullResults.map((hit, index) => (
                  <ResultTile
                    key={`full-${hit.doc_id}`}
                    hit={hit}
                    index={index}
                    query={fullQuery}
                    breadcrumb={renderBreadcrumb(hit.project_id, hit.path)}
                    onMove={openMoveModal}
                  />
                ))}
              </ul>
            )}

            <div className="flex items-center justify-between border-t border-border pt-3">
              <span className="font-mono text-xs text-tertiary">
                {t("painel:results.page", { page: fullPage, totalPages: fullTotalPages })}
              </span>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={fullLoading || fullPage <= 1} onClick={() => onRunFullSearch(fullPage - 1)}>
                  {t("painel:results.previous")}
                </Button>
                <Button variant="secondary" size="sm" disabled={fullLoading || fullPage >= fullTotalPages} onClick={() => onRunFullSearch(fullPage + 1)}>
                  {t("painel:results.next")}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
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
          onCancel={() => {
            setMoveHit(null);
            setMoveError(null);
          }}
          onConfirm={handleMoveConfirm}
        />
      )}
    </div>
  );
}
