import { ArrowRightLeft, ChevronDown, ChevronRight } from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchIngestHistory, fetchProjectProfile, moveDocument } from "../../api";
import { MoveDocumentModal } from "../../components/MoveDocumentModal";
import type { IngestHistoryEntry, ProjectProfileV2 } from "../../types";
import "./ingestTriageCard.css";

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
  decision: "auto" | "triage_pending" | "duplicate" | "error" | "moved";
  confidence: number | null;
  business_domain_confidence?: number;
  document_type_confidence?: number;
  llm: boolean;
  rule_business_domain?: string;
  rule_confidence?: number;
  llm_explanation?: string;
  llm_proposed_business_domain?: string;
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
        llm: item.topics_source === "llm_policy" || !!item.llm_explanation || !!item.rule_business_domain,
        rule_business_domain: item.rule_business_domain,
        rule_confidence: item.rule_confidence,
        llm_explanation: item.llm_explanation,
        llm_proposed_business_domain: item.llm_proposed_business_domain,
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
  onStatus: (msg: string) => void;
};

export function IngestHistoryCard({ selectedProject, onStatus }: Props) {
  const [history, setHistory] = useState<IngestHistoryEntry[]>([]);
  const [page, setPage] = useState(0);
  const [expandedLlm, setExpandedLlm] = useState<Set<string>>(new Set());
  const [moveRow, setMoveRow] = useState<FlatRow | null>(null);
  const [moveSubmitting, setMoveSubmitting] = useState(false);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [fullProfile, setFullProfile] = useState<ProjectProfileV2 | null>(null);

  const isSingleProject = selectedProject !== ALL_PROJECTS;

  const loadHistory = useCallback(async () => {
    if (!isSingleProject) {
      setHistory([]);
      return;
    }
    try {
      const resp = await fetchIngestHistory(selectedProject);
      setHistory(resp.entries);
    } catch {
      setHistory([]);
    }
  }, [selectedProject, isSingleProject]);

  useEffect(() => {
    void loadHistory();
    setPage(0);
  }, [loadHistory]);

  useEffect(() => {
    if (!isSingleProject) return;
    fetchProjectProfile(selectedProject)
      .then((resp) => setFullProfile(resp.profile))
      .catch(() => {});
  }, [selectedProject, isSingleProject]);

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
    row.doc_id && row.decision !== "duplicate" && row.decision !== "error";

  if (allRows.length === 0) return null;

  return (
    <>
      <section className="panel card">
        <details className="itc-collapsible" open>
          <summary className="itc-collapsible-header">
            Processamentos
            <span className="itc-badge itc-badge-accent">{allRows.length} arquivo{allRows.length !== 1 ? "s" : ""}</span>
          </summary>
          <div className="itc-collapsible-body itc-proc-body">
            <div className="itc-proc-table-wrap">
              <table className="itc-scan-table">
                <thead>
                  <tr>
                    <th className="itc-th-status" />
                    <th className="itc-th-datetime">Data / Hora</th>
                    <th className="itc-th-file">Arquivo</th>
                    <th className="itc-th-area">Domínio / Tipo</th>
                    <th className="itc-th-decision">Decisão</th>
                    <th className="itc-th-conf">Conf.</th>
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
                        <tr className={`itc-scan-row${hasLlmDetail ? " itc-row-clickable" : ""}`} onClick={hasLlmDetail ? () => toggleLlmRow(row.key) : undefined}>
                          <td className={`itc-scan-icon ${row.decision}`}>
                            {row.decision === "auto" || row.decision === "moved" ? "✓" : row.decision === "duplicate" ? "✕" : row.decision === "error" ? "✕" : "⏳"}
                          </td>
                          <td className="itc-scan-datetime">
                            {new Date(row.timestamp).toLocaleString("pt-BR", {
                              day: "2-digit", month: "2-digit", year: "2-digit",
                              hour: "2-digit", minute: "2-digit"
                            })}
                          </td>
                          <td className="itc-scan-name" title={row.filename}>
                            {row.filename}
                            {row.llm && (
                              <span className="itc-scan-llm-indicator" title="Classificado com LLM">🤖</span>
                            )}
                          </td>
                          <td className="itc-scan-area" title={row.business_domain}>
                            {row.business_domain}
                            {row.document_type ? ` / ${row.document_type}` : ""}
                            {businessDomainOverridden && (
                              <span className="itc-area-override" title={`Regra: ${row.rule_business_domain}`}>
                                ← {row.rule_business_domain}
                              </span>
                            )}
                          </td>
                          <td>
                            <span className={`itc-scan-badge ${row.decision}`}>
                              {row.decision === "auto" ? "auto" : row.decision === "moved" ? "movido" : row.decision === "duplicate" ? "dup" : row.decision === "error" ? "falha" : "triagem"}
                            </span>
                          </td>
                          <td className="itc-scan-conf">
                            {row.confidence !== null ? row.confidence.toFixed(2) : "-"}
                            {hasLlmDetail && (isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />)}
                            {canMove(row) && (
                              <button
                                type="button"
                                className="itc-move-btn"
                                title="Mover para outro domínio/tipo"
                                onClick={(e) => { e.stopPropagation(); setMoveRow(row); }}
                              >
                                <ArrowRightLeft size={12} />
                              </button>
                            )}
                          </td>
                        </tr>
                        {isExpanded && hasLlmDetail && (
                          <tr className="itc-llm-detail-row">
                            <td colSpan={6}>
                              <div className="itc-llm-detail-card">
                                <strong>Detalhes da classificação LLM</strong>
                                <p>
                                  Classificador: <code>{formatClassifierModeLabel(row.classifier_mode)}</code>
                                  {row.classifier_requested_mode && row.classifier_requested_mode !== row.classifier_mode
                                    ? ` (solicitado: ${formatClassifierModeLabel(row.classifier_requested_mode)})`
                                    : ""}
                                </p>
                                <p>
                                  Scores: domínio {formatPct(row.business_domain_confidence)} | tipo {formatPct(row.document_type_confidence)} | final {row.confidence !== null ? row.confidence.toFixed(2) : "—"}
                                </p>
                                {row.classifier_fallback_reason && (
                                  <p>Fallback: <code>{row.classifier_fallback_reason}</code></p>
                                )}
                                {row.rule_business_domain && (
                                  <p>Regra: <code>{row.rule_business_domain}</code> (conf {(row.rule_confidence ?? 0).toFixed(2)})</p>
                                )}
                                <p>LLM: <code>{row.business_domain}</code> (conf {(row.confidence ?? 0).toFixed(2)})</p>
                                {row.llm_explanation && <p>Motivo: <em>{row.llm_explanation}</em></p>}
                                {row.llm_proposed_business_domain && (
                                  <p className="itc-proposed-area">Domínio proposto: <code>{row.llm_proposed_business_domain}</code></p>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="itc-proc-pagination">
                <button disabled={page <= 0} onClick={() => setPage((p) => p - 1)}>
                  ← Anterior
                </button>
                <span>
                  {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, allRows.length)} de {allRows.length}
                </span>
                <button disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
                  Próxima →
                </button>
              </div>
            )}
          </div>
        </details>
      </section>

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
              onStatus(`Documento movido para ${targetBd}/${targetDt}`);
              setMoveRow(null);
              setMoveError(null);
              void loadHistory();
            } catch (e) {
              const msg = e instanceof Error ? e.message : "Falha ao mover documento";
              setMoveError(msg);
              onStatus(msg);
            } finally {
              setMoveSubmitting(false);
            }
          }}
        />
      )}
    </>
  );
}
