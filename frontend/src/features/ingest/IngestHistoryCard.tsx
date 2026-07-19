import { ArrowRightLeft, CheckCircle2, ChevronDown, ChevronRight, Clock, XCircle } from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { moveDocument } from "../../api";
import i18n from "../../i18n";
import { formatDate } from "../../lib/format";
import { useIngestHistoryQuery, useProjectProfileQuery } from "../../lib/queries";
import { MoveDocumentModal } from "../../components/MoveDocumentModal";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { CollapsibleSection } from "../../components/ui/collapsible-section";
import { DataTable, TableWrap } from "../../components/ui/data-table";
import { invalidateAfterMove } from "../../lib/mutations";
import type { IngestHistoryEntry, ProjectProfileV2, StatusSeverity } from "../../types";

function decisionBadge(decision: FlatRow["decision"]) {
  switch (decision) {
    case "auto":
      return <Badge variant="success">{i18n.t("ingest:decision.auto")}</Badge>;
    case "moved":
      return <Badge variant="success">{i18n.t("ingest:decision.moved")}</Badge>;
    case "duplicate":
      return <Badge variant="outline">{i18n.t("ingest:decision.duplicate")}</Badge>;
    case "error":
      return <Badge variant="destructive">{i18n.t("ingest:decision.error")}</Badge>;
    case "approved":
      return <Badge variant="success">{i18n.t("ingest:decision.approved")}</Badge>;
    case "corrected":
      return <Badge variant="success">{i18n.t("ingest:decision.corrected")}</Badge>;
    case "rejected":
      return <Badge variant="destructive">{i18n.t("ingest:decision.rejected")}</Badge>;
    case "deleted":
      return <Badge variant="outline">{i18n.t("ingest:decision.deleted")}</Badge>;
    default:
      return <Badge>{i18n.t("ingest:decision.triage_pending")}</Badge>;
  }
}

function decisionIcon(decision: FlatRow["decision"]) {
  if (decision === "auto" || decision === "moved" || decision === "approved" || decision === "corrected") return <CheckCircle2 size={13} className="text-success" aria-hidden />;
  if (decision === "duplicate" || decision === "error" || decision === "rejected" || decision === "deleted") return <XCircle size={13} className="text-destructive" aria-hidden />;
  return <Clock size={13} className="text-accent" aria-hidden />;
}

const ALL_PROJECTS = "__all__";
const PAGE_SIZE = 10;

type FlatRow = {
  key: string;
  doc_id?: string;
  project_id?: string;
  timestamp: string;
  filename: string;
  business_domain: string;
  document_type?: string;
  decision: "auto" | "triage_pending" | "duplicate" | "error" | "moved" | "approved" | "corrected" | "rejected" | "deleted";
  confidence: number | null;
  business_domain_confidence?: number;
  document_type_confidence?: number;
  llm: boolean;
  rule_business_domain?: string;
  llm_explanation?: string;
  llm_proposed_business_domain?: string;
  llm_business_domain?: string;
  llm_document_type?: string;
  llm_confidence?: number;
  classification_reason?: string;
  classifier_mode?: string;
  classifier_requested_mode?: string;
  classifier_fallback_reason?: string;
};

function formatPct(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatClassifierModeLabel(mode?: string | null): string {
  return mode || "—";
}

function flattenHistory(entries: IngestHistoryEntry[]): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const entry of entries) {
    const ts = entry.timestamp;
    for (const item of entry.items) {
      rows.push({
        key: `${ts}-${item.doc_id}`,
        doc_id: item.doc_id,
        project_id: item.project_id,
        timestamp: ts,
        filename: item.original_filename,
        business_domain: item.business_domain || "",
        document_type: item.document_type,
        decision: item.decision,
        confidence: item.confidence_score,
        business_domain_confidence: item.business_domain_confidence,
        document_type_confidence: item.document_type_confidence,
        llm: item.topics_source === "llm_policy" || !!item.llm_explanation || !!item.rule_business_domain || !!item.llm_business_domain,
        rule_business_domain: item.rule_business_domain,
        llm_explanation: item.llm_explanation,
        llm_proposed_business_domain: item.llm_proposed_business_domain,
        llm_business_domain: item.llm_business_domain,
        llm_document_type: item.llm_document_type,
        llm_confidence: item.llm_confidence,
        classification_reason: item.classification_reason,
        classifier_mode: item.classifier_mode,
        classifier_requested_mode: item.classifier_requested_mode,
        classifier_fallback_reason: item.classifier_fallback_reason,
      });
    }
    for (let i = 0; i < entry.errors.length; i++) {
      const err = entry.errors[i];
      rows.push({
        key: `${ts}-err-${i}`,
        timestamp: ts,
        filename: err.filename,
        business_domain: err.error.slice(0, 40),
        decision: "error",
        confidence: null,
        llm: false,
      });
    }
  }
  return rows;
}

type Props = {
  selectedProject: string;
  onStatus: (msg: string, severity?: StatusSeverity) => void;
};

export function IngestHistoryCard({ selectedProject, onStatus }: Props) {
  const { t } = useTranslation();
  const [page, setPage] = useState(0);
  const [expandedLlm, setExpandedLlm] = useState<Set<string>>(new Set());
  const [moveRow, setMoveRow] = useState<FlatRow | null>(null);
  const [moveSubmitting, setMoveSubmitting] = useState(false);
  const [moveError, setMoveError] = useState<string | null>(null);

  const isSingleProject = selectedProject !== ALL_PROJECTS;

  // Reativo via cache: scans/decisões invalidam ingest-history
  const { data: historyData } = useIngestHistoryQuery(selectedProject, isSingleProject);
  const history: IngestHistoryEntry[] = historyData?.entries ?? [];
  const { data: profileData } = useProjectProfileQuery(selectedProject, isSingleProject);
  const fullProfile = profileData?.profile ?? null;

  useEffect(() => {
    setPage(0);
  }, [selectedProject]);

  const allRows = useMemo(() => flattenHistory(history), [history]);
  const totalPages = Math.ceil(allRows.length / PAGE_SIZE);
  const pageRows = allRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function toggleLlmRow(key: string) {
    setExpandedLlm((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const canMove = (row: FlatRow) =>
    row.doc_id &&
    row.decision !== "duplicate" &&
    row.decision !== "error" &&
    row.decision !== "rejected" &&
    row.decision !== "deleted";

  if (allRows.length === 0) return null;

  return (
    <>
      <Card>
        <CardContent className="pt-5">
          <CollapsibleSection title={t("ingest:history.title")} persistKey="processamentos" badge={t("common:unit.file", { count: allRows.length })} defaultOpen className="border-0 bg-transparent [&>summary]:px-0 [&>div]:border-0 [&>div]:px-0">
            <TableWrap>
              <DataTable className="[&_td]:text-left [&_th]:text-left">
                <thead>
                  <tr>
                    <th style={{ width: 28 }} />
                    <th>{t("ingest:history.colDateTime")}</th>
                    <th>{t("ingest:history.colFile")}</th>
                    <th>{t("ingest:history.colDomainType")}</th>
                    <th>{t("ingest:history.colDecision")}</th>
                    <th>{t("ingest:history.colConfidence")}</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const hasLlmDetail = !!(
                      row.classifier_mode ||
                      row.llm_explanation ||
                      row.rule_business_domain ||
                      row.llm_proposed_business_domain ||
                      row.business_domain_confidence != null ||
                      row.document_type_confidence != null ||
                      row.classifier_fallback_reason
                    );
                    const isExpanded = expandedLlm.has(row.key);
                    const businessDomainOverridden =
                      row.rule_business_domain && row.rule_business_domain !== row.business_domain;
                    return (
                      <React.Fragment key={row.key}>
                        <tr className={hasLlmDetail ? "cursor-pointer" : undefined} onClick={hasLlmDetail ? () => toggleLlmRow(row.key) : undefined}>
                          <td>{decisionIcon(row.decision)}</td>
                          <td className="whitespace-nowrap">
                            {formatDate(row.timestamp, {
                              day: "2-digit", month: "2-digit", year: "2-digit",
                              hour: "2-digit", minute: "2-digit"
                            })}
                          </td>
                          <td className="max-w-64 truncate font-body" title={row.filename}>
                            {row.filename}
                            {row.llm && (
                              <span className="ml-1" title={t("ingest:history.llmBadgeTitle")}>🤖</span>
                            )}
                          </td>
                          <td className="max-w-44 truncate" title={row.business_domain}>
                            {row.business_domain}
                            {row.document_type ? ` / ${row.document_type}` : ""}
                            {businessDomainOverridden && (
                              <span className="ml-1 text-accent-light" title={t("ingest:history.ruleTitle", { rule: row.rule_business_domain })}>
                                ← {row.rule_business_domain}
                              </span>
                            )}
                          </td>
                          <td>{decisionBadge(row.decision)}</td>
                          <td className="whitespace-nowrap">
                            <span className="inline-flex items-center gap-1">
                              {row.confidence !== null ? row.confidence.toFixed(2) : "-"}
                              {hasLlmDetail && (isExpanded ? <ChevronDown size={12} aria-hidden /> : <ChevronRight size={12} aria-hidden />)}
                              {canMove(row) && (
                                <button
                                  type="button"
                                  className="rounded border-0 bg-transparent p-0.5 text-tertiary shadow-none transition-colors hover:text-accent"
                                  title={t("ingest:history.moveTitle")}
                                  aria-label={t("ingest:history.moveTitle")}
                                  onClick={(e) => { e.stopPropagation(); setMoveRow(row); }}
                                >
                                  <ArrowRightLeft size={12} aria-hidden />
                                </button>
                              )}
                            </span>
                          </td>
                        </tr>
                        {isExpanded && hasLlmDetail && (
                          <tr>
                            <td colSpan={6}>
                              <div className="space-y-0.5 rounded-md bg-panel-strong p-2.5 font-mono text-[0.72rem] text-muted-foreground [&_code]:text-accent-light [&_em]:not-italic [&_em]:text-foreground/80">
                                <strong className="font-display text-foreground-strong">{t("ingest:history.detailsTitle")}</strong>
                                <p>
                                  <code>{formatClassifierModeLabel(row.classifier_mode)}</code>
                                  {row.classifier_requested_mode && row.classifier_requested_mode !== row.classifier_mode
                                    ? ` ${t("ingest:history.requestedMode", { mode: formatClassifierModeLabel(row.classifier_requested_mode) })}`
                                    : ""}
                                  {": "}{t("ingest:history.detailScores", {
                                    domain: formatPct(row.business_domain_confidence),
                                    type: formatPct(row.document_type_confidence),
                                    final: row.confidence !== null ? row.confidence.toFixed(2) : "—"
                                  })}
                                </p>
                                {(row.llm_business_domain || row.llm_document_type) && (
                                  <p>
                                    <code>llm</code>:{row.llm_business_domain && <> {t("ingest:history.domainLabel")} <code>{row.llm_business_domain}</code></>}
                                    {row.llm_business_domain && row.llm_document_type ? " ·" : ""}
                                    {row.llm_document_type && <> {t("ingest:history.typeLabel")} <code>{row.llm_document_type}</code></>}
                                    {row.llm_confidence !== undefined && <> {t("ingest:history.confLabel", { value: row.llm_confidence.toFixed(2) })}</>}
                                  </p>
                                )}
                                {row.classifier_fallback_reason && (
                                  <p>{t("ingest:history.fallbackLabel")} <code>{row.classifier_fallback_reason}</code></p>
                                )}
                                {row.llm_explanation && <p>{t("ingest:history.reasonLabel")} <em>{row.llm_explanation}</em></p>}
                                {row.llm_proposed_business_domain && (
                                  <p>{t("ingest:history.proposedDomainLabel")} <code className="!text-accent-purple">{row.llm_proposed_business_domain}</code></p>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </DataTable>
            </TableWrap>

            {totalPages > 1 && (
              <div className="mt-2 flex items-center justify-between">
                <Button variant="ghost" size="sm" disabled={page <= 0} onClick={() => setPage((p) => p - 1)}>
                  {t("ingest:history.prev")}
                </Button>
                <span className="font-mono text-[0.7rem] text-tertiary">
                  {t("ingest:history.pageInfo", { from: page * PAGE_SIZE + 1, to: Math.min((page + 1) * PAGE_SIZE, allRows.length), total: allRows.length })}
                </span>
                <Button variant="ghost" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
                  {t("ingest:history.next")}
                </Button>
              </div>
            )}
          </CollapsibleSection>
        </CardContent>
      </Card>

      {moveRow && fullProfile && (
        <MoveDocumentModal
          open={!!moveRow}
          filename={moveRow.filename}
          currentBusinessDomain={moveRow.business_domain}
          currentDocumentType={moveRow.document_type || ""}
          businessDomainOptions={(fullProfile.classification?.business_domains || []).map((d) => ({
            key: d.key,
            label: d.label || d.key,
          }))}
          documentTypeOptions={(fullProfile.classification?.document_types || []).map((d) => ({
            key: d.key,
            label: d.label || d.key,
          }))}
          submitting={moveSubmitting}
          errorMessage={moveError}
          onCancel={() => { setMoveRow(null); setMoveError(null); }}
          onConfirm={async (targetBd, targetDt) => {
            if (!moveRow.doc_id || !moveRow.project_id) return;
            setMoveSubmitting(true);
            setMoveError(null);
            try {
              await moveDocument(moveRow.project_id, moveRow.doc_id, targetBd, targetDt);
              onStatus(t("ingest:history.movedTo", { domain: targetBd, type: targetDt }));
              setMoveRow(null);
              setMoveError(null);
              invalidateAfterMove();
            } catch (e) {
              const msg = e instanceof Error ? e.message : t("ingest:history.moveFailed");
              setMoveError(msg);
              onStatus(msg, "error");
            } finally {
              setMoveSubmitting(false);
            }
          }}
        />
      )}
    </>
  );
}
