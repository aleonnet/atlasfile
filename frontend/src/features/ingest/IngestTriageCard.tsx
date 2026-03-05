import { ChevronDown, ChevronRight, RefreshCw, Settings } from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchIngestHistory, fetchModels, fetchProjectProfile, triggerScan, updateProjectProfile } from "../../api";
import type {
  IngestHistoryEntry,
  LLMPolicy,
  ModelOption,
  Project,
  ProjectProfileV2,
  ScanResult,
  TriageItem
} from "../../types";
import "./ingestTriageCard.css";

const ALL_PROJECTS = "__all__";
const PAGE_SIZE = 10;

const DEFAULT_LLM_POLICY: LLMPolicy = {
  enabled: false,
  provider: "openai",
  model: "gpt-4o-mini",
  mode: "tag_only",
  allow_override_fields: ["document_type", "tags", "confidence", "topics"],
  override_guardrails: {
    area_override_only_if_rule_confidence_below: 0.65,
    require_explanation: true,
    max_area_changes: 1
  }
};

type FlatRow = {
  key: string;
  timestamp: string;
  filename: string;
  area_key: string;
  decision: "auto" | "triage_pending" | "duplicate" | "error";
  confidence: number | null;
  llm: boolean;
  rule_area_key?: string;
  rule_confidence?: number;
  llm_explanation?: string;
  llm_proposed_area?: string;
  classification_reason?: string;
};

function flattenHistory(entries: IngestHistoryEntry[]): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const entry of entries) {
    const ts = entry.timestamp;
    for (const item of entry.items) {
      rows.push({
        key: `${ts}-${item.doc_id}`,
        timestamp: ts,
        filename: item.original_filename,
        area_key: item.area_key,
        decision: item.decision,
        confidence: item.confidence_score,
        llm: item.topics_source === "llm_policy" || !!item.llm_explanation || !!item.rule_area_key,
        rule_area_key: item.rule_area_key,
        rule_confidence: item.rule_confidence,
        llm_explanation: item.llm_explanation,
        llm_proposed_area: item.llm_proposed_area,
        classification_reason: item.classification_reason,
      });
    }
    for (let i = 0; i < entry.errors.length; i++) {
      const err = entry.errors[i];
      rows.push({
        key: `${ts}-err-${i}`,
        timestamp: ts,
        filename: err.filename,
        area_key: err.error.slice(0, 40),
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
  selectedProjectLabel: string;
  projects: Project[];
  projectLabelById: Map<string, string>;
  triageItems: TriageItem[];
  initializingProjectId: string | null;
  onDecision: (item: TriageItem, action: "approve" | "correct" | "reject") => Promise<void>;
  onLoadTriage: () => Promise<void>;
  onStatus: (msg: string) => void;
  openaiApiKey: string;
  anthropicApiKey: string;
  onOpenSettings: () => void;
};

export function IngestTriageCard({
  selectedProject,
  selectedProjectLabel,
  projects,
  projectLabelById,
  triageItems,
  initializingProjectId,
  onDecision,
  onLoadTriage,
  onStatus,
  openaiApiKey,
  anthropicApiKey,
  onOpenSettings
}: Props) {
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<IngestHistoryEntry[]>([]);
  const [page, setPage] = useState(0);
  const [llmPolicy, setLlmPolicy] = useState<LLMPolicy>(DEFAULT_LLM_POLICY);
  const [profileVersion, setProfileVersion] = useState<number>(0);
  const [llmSaving, setLlmSaving] = useState(false);
  const [models, setModels] = useState<ModelOption[]>([]);
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

  const loadProfile = useCallback(async () => {
    if (!isSingleProject) return;
    try {
      const resp = await fetchProjectProfile(selectedProject);
      setFullProfile(resp.profile);
      setProfileVersion(resp.version);
      const policy = resp.profile.classification?.llm_policy;
      if (policy) {
        setLlmPolicy({ ...DEFAULT_LLM_POLICY, ...policy });
      } else {
        setLlmPolicy(DEFAULT_LLM_POLICY);
      }
    } catch {
      /* profile not available yet */
    }
  }, [selectedProject, isSingleProject]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    if (models.length === 0) {
      fetchModels()
        .then(setModels)
        .catch(() => {});
    }
  }, [models.length]);

  async function persistLlmPolicy(nextPolicy: LLMPolicy) {
    if (!fullProfile) return;
    setLlmSaving(true);
    try {
      const updated: ProjectProfileV2 = {
        ...fullProfile,
        classification: {
          ...fullProfile.classification,
          llm_policy: nextPolicy
        }
      };
      const resp = await updateProjectProfile(selectedProject, updated, profileVersion);
      setFullProfile(resp.profile);
      setProfileVersion(resp.version);
      setLlmPolicy({ ...DEFAULT_LLM_POLICY, ...resp.profile.classification?.llm_policy });
    } catch {
      onStatus("Falha ao salvar política LLM no profile");
    } finally {
      setLlmSaving(false);
    }
  }

  function handleToggleLlm() {
    const next = !llmPolicy.enabled;
    if (next) {
      const provider = llmPolicy.provider || "openai";
      const needKey =
        (provider === "openai" && !openaiApiKey) ||
        (provider === "anthropic" && !anthropicApiKey);
      if (needKey) {
        onOpenSettings();
        return;
      }
    }
    const nextPolicy = { ...llmPolicy, enabled: next };
    setLlmPolicy(nextPolicy);
    void persistLlmPolicy(nextPolicy);
  }

  function handleModeChange(mode: LLMPolicy["mode"]) {
    const nextPolicy = { ...llmPolicy, mode };
    setLlmPolicy(nextPolicy);
    void persistLlmPolicy(nextPolicy);
  }

  function handleProviderChange(providerModel: string) {
    const [provider, model] = providerModel.split("/");
    const nextPolicy = {
      ...llmPolicy,
      provider: provider as LLMPolicy["provider"],
      model: model || llmPolicy.model
    };
    setLlmPolicy(nextPolicy);
    void persistLlmPolicy(nextPolicy);
  }

  async function handleScan() {
    if (!selectedProject) return;
    setLoading(true);
    onStatus("Processando inbox...");
    try {
      const results: ScanResult[] = [];
      if (selectedProject === ALL_PROJECTS) {
        for (const project of projects) {
          results.push(await triggerScan(project.project_id));
        }
      } else {
        results.push(await triggerScan(selectedProject));
      }

      await loadHistory();
      setPage(0);
      await onLoadTriage();

      const totals = results.reduce(
        (acc, r) => ({
          processed: acc.processed + r.processed_count,
          failed: acc.failed + r.failed_count
        }),
        { processed: 0, failed: 0 }
      );
      onStatus(`Inbox processado: ${totals.processed} arquivo(s), ${totals.failed} falha(s)`);
    } catch {
      onStatus("Falha ao processar inbox");
    } finally {
      setLoading(false);
    }
  }

  const allRows = useMemo(() => flattenHistory(history), [history]);
  const totalPages = Math.ceil(allRows.length / PAGE_SIZE);
  const pageRows = allRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const [expandedLlm, setExpandedLlm] = useState<Set<string>>(new Set());

  function toggleLlmRow(key: string) {
    setExpandedLlm((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const currentProviderModel = `${llmPolicy.provider}/${llmPolicy.model}`;
  const modelLabel = models.find((m) => `${m.provider}/${m.model}` === currentProviderModel)?.label;
  const hasKey =
    (llmPolicy.provider === "openai" && !!openaiApiKey) ||
    (llmPolicy.provider === "anthropic" && !!anthropicApiKey);

  return (
    <section className="panel card">
      <div className="panel-head card-header">
        <h2>Ingestão e triagem</h2>
        <button
          className="btn primary"
          disabled={loading || !selectedProject || initializingProjectId === selectedProject}
          onClick={handleScan}
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          {loading ? "Processando..." : "Processar INBOX"}
        </button>
      </div>

      {/* ── Classificação LLM ── */}
      {isSingleProject && (
        <details className="itc-collapsible">
          <summary className="itc-collapsible-header">
            Classificação LLM
            <span className="itc-badge-count">{llmPolicy.enabled ? "ativado" : "desativado"}</span>
          </summary>
          <div className="itc-collapsible-body">
            <div className="itc-llm-row">
              <label>
                LLM ativado
                <button
                  type="button"
                  className={`itc-toggle ${llmPolicy.enabled ? "active" : ""}`}
                  onClick={handleToggleLlm}
                  aria-pressed={llmPolicy.enabled}
                  aria-label="Ativar classificação LLM"
                  disabled={llmSaving}
                />
              </label>
              {llmSaving && <span className="itc-llm-saving">salvando...</span>}
            </div>

            {llmPolicy.enabled && (
              <>
                <div className="itc-llm-fields">
                  <div className="itc-llm-field">
                    <label htmlFor="itc-llm-mode">Modo</label>
                    <select
                      id="itc-llm-mode"
                      value={llmPolicy.mode}
                      onChange={(e) => handleModeChange(e.target.value as LLMPolicy["mode"])}
                      disabled={llmSaving}
                    >
                      <option value="tag_only">tag_only — enriquece tags/tipo</option>
                      <option value="review">review — revisa e pode ir p/ triagem</option>
                      <option value="full_override">full_override — pode mudar área</option>
                    </select>
                  </div>
                  <div className="itc-llm-field">
                    <label htmlFor="itc-llm-model">Modelo triagem</label>
                    <div className="itc-llm-model-row">
                      <select
                        id="itc-llm-model"
                        value={currentProviderModel}
                        onChange={(e) => handleProviderChange(e.target.value)}
                        disabled={llmSaving}
                      >
                        {models.map((m) => (
                          <option key={`${m.provider}/${m.model}`} value={`${m.provider}/${m.model}`}>
                            {m.label}
                          </option>
                        ))}
                        {models.length === 0 && (
                          <option value={currentProviderModel}>
                            {modelLabel || currentProviderModel}
                          </option>
                        )}
                      </select>
                      <button
                        type="button"
                        className="itc-btn-gear"
                        onClick={onOpenSettings}
                        title="Configurar modelos e chaves"
                      >
                        <Settings size={16} />
                      </button>
                    </div>
                  </div>
                </div>

                {!hasKey && (
                  <div className="itc-llm-warning">
                    <span>⚠ API Key não configurada para {llmPolicy.provider}.</span>
                    <button type="button" onClick={onOpenSettings}>
                      Configurar
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </details>
      )}

      <div className="card-intro">
        <p>Projeto selecionado: {selectedProjectLabel || "-"}</p>
        <p>Itens pendentes: {triageItems.length}</p>
      </div>

      {/* ── Processamentos (tabela plana, paginada) ── */}
      {allRows.length > 0 && (
        <details className="itc-collapsible" open>
          <summary className="itc-collapsible-header">
            Processamentos
            <span className="itc-badge-count">{allRows.length} arquivo(s)</span>
          </summary>
          <div className="itc-collapsible-body itc-proc-body">
            <div className="itc-proc-table-wrap">
              <table className="itc-scan-table">
                <thead>
                  <tr>
                    <th className="itc-th-status" />
                    <th className="itc-th-datetime">Data / Hora</th>
                    <th className="itc-th-file">Arquivo</th>
                    <th className="itc-th-area">Área / Pasta</th>
                    <th className="itc-th-decision">Decisão</th>
                    <th className="itc-th-conf">Conf.</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const hasLlmDetail = row.llm && (row.llm_explanation || row.rule_area_key || row.llm_proposed_area);
                    const isExpanded = expandedLlm.has(row.key);
                    const areaOverridden = row.rule_area_key && row.rule_area_key !== row.area_key;
                    return (
                      <React.Fragment key={row.key}>
                        <tr className={`itc-scan-row${hasLlmDetail ? " itc-row-clickable" : ""}`} onClick={hasLlmDetail ? () => toggleLlmRow(row.key) : undefined}>
                          <td className={`itc-scan-icon ${row.decision}`}>
                            {row.decision === "auto" ? "✓" : row.decision === "duplicate" ? "✕" : row.decision === "error" ? "✕" : "⏳"}
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
                          <td className="itc-scan-area" title={row.area_key}>
                            {row.area_key}
                            {areaOverridden && (
                              <span className="itc-area-override" title={`Regra: ${row.rule_area_key}`}>
                                ← {row.rule_area_key}
                              </span>
                            )}
                          </td>
                          <td>
                            <span className={`itc-scan-badge ${row.decision}`}>
                              {row.decision === "auto" ? "auto" : row.decision === "duplicate" ? "dup" : row.decision === "error" ? "falha" : "triagem"}
                            </span>
                          </td>
                          <td className="itc-scan-conf">
                            {row.confidence !== null ? row.confidence.toFixed(2) : "-"}
                            {hasLlmDetail && (isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />)}
                          </td>
                        </tr>
                        {isExpanded && hasLlmDetail && (
                          <tr className="itc-llm-detail-row">
                            <td colSpan={6}>
                              <div className="itc-llm-detail-card">
                                <strong>Detalhes da classificação LLM</strong>
                                {row.rule_area_key && (
                                  <p>Regra: <code>{row.rule_area_key}</code> (conf {(row.rule_confidence ?? 0).toFixed(2)})</p>
                                )}
                                <p>LLM: <code>{row.area_key}</code> (conf {(row.confidence ?? 0).toFixed(2)})</p>
                                {row.llm_explanation && <p>Motivo: <em>{row.llm_explanation}</em></p>}
                                {row.llm_proposed_area && (
                                  <p className="itc-proposed-area">Área proposta (nova): <code>{row.llm_proposed_area}</code></p>
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
              <div className="itc-pagination">
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
      )}

      {/* ── Itens pendentes de triagem ── */}
      {triageItems.length > 0 && (
        <details className="itc-collapsible" open>
          <summary className="itc-collapsible-header">
            Itens pendentes de triagem
            <span className="itc-badge-count">{triageItems.length}</span>
          </summary>
          <div className="itc-collapsible-body">
            <ul className="list">
              {triageItems.map((item) => {
                const hasLlmContext = item.llm_explanation || item.rule_area_key || item.llm_proposed_area;
                return (
                  <li key={item.doc_id} className="list-item">
                    <strong className="list-title">{item.filename}</strong>
                    <div className="sub list-meta">
                      projeto: {projectLabelById.get(item.project_id) || item.project_id} | sugestão:{" "}
                      {item.suggested_area || "sem sugestão"} | confiança: {item.confidence_score.toFixed(2)}
                    </div>

                    {hasLlmContext && (
                      <div className="itc-triage-llm-context">
                        {item.rule_area_key && (
                          <p>Regra: <code>{item.rule_area_key}</code> (conf {(item.rule_confidence ?? 0).toFixed(2)})</p>
                        )}
                        {item.llm_explanation && <p>LLM: <em>{item.llm_explanation}</em></p>}
                        {item.llm_proposed_area && (
                          <p className="itc-proposed-area">Área proposta (nova): <code>{item.llm_proposed_area}</code></p>
                        )}
                      </div>
                    )}

                    <div className="row">
                      <button
                        className="btn"
                        disabled={!item.suggested_area}
                        title={!item.suggested_area ? "Sem sugestão de área" : ""}
                        onClick={() => void onDecision(item, "approve")}
                      >
                        Aprovar
                      </button>
                      {item.llm_proposed_area && (
                        <button
                          className="btn primary"
                          onClick={() => void onDecision({ ...item, suggested_area: item.llm_proposed_area }, "correct")}
                          title={`Aprovar e criar área: ${item.llm_proposed_area}`}
                        >
                          Aprovar: {item.llm_proposed_area}
                        </button>
                      )}
                      <button className="btn" onClick={() => void onDecision(item, "correct")}>
                        Corrigir
                      </button>
                      <button className="btn danger" onClick={() => void onDecision(item, "reject")}>
                        Rejeitar
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </details>
      )}

      {triageItems.length === 0 && allRows.length === 0 && (
        <p className="itc-scan-empty">Nenhum item pendente ou processado recentemente.</p>
      )}
    </section>
  );
}
