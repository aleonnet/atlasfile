import { ChevronDown, ChevronRight, RefreshCw, Settings } from "lucide-react";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchClassifierCycleStatus,
  fetchClassifierReportLatest,
  fetchClassifierReports,
  fetchClassifierStatus,
  fetchIngestHistory,
  fetchIngestStatus,
  fetchModels,
  fetchProjectProfile,
  getClassifierCycleStatusStreamUrl,
  getIngestStatusStreamUrl,
  startClassifierCycle,
  triggerScan,
  updateClassifierOverride,
  updateProjectProfile
} from "../../api";
import type {
  ClassifierCycleStatus,
  ClassifierReport,
  ClassifierReportSummary,
  ClassifierStatusResponse,
  IngestHistoryEntry,
  IngestOperationStatus,
  LLMPolicy,
  ModelOption,
  OperationalClassifierMode,
  Project,
  ProjectProfileV2,
  ScanResult,
  TriageItem
} from "../../types";
import "./ingestTriageCard.css";

const ALL_PROJECTS = "__all__";
const PAGE_SIZE = 10;
const AUTO_CLASSIFIER_OVERRIDE = "__auto__";

const DEFAULT_LLM_POLICY: LLMPolicy = {
  enabled: false,
  provider: "openai",
  model: "gpt-4o-mini",
  mode: "tag_only",
  allow_override_fields: ["document_type", "tags", "confidence", "topics"],
  override_guardrails: {
    business_domain_override_only_if_rule_confidence_below: 0.65,
    require_explanation: true,
    max_business_domain_changes: 1
  }
};

type FlatRow = {
  key: string;
  timestamp: string;
  filename: string;
  business_domain: string;
  document_type?: string;
  decision: "auto" | "triage_pending" | "duplicate" | "error";
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
  switch (mode) {
    case "bootstrap":
      return "bootstrap";
    case "sparse_logreg":
      return "sparse_logreg";
    case "sparse_linear_svc":
      return "sparse_linear_svc";
    default:
      return mode || "—";
  }
}

function formatPhaseLabel(phase?: string | null): string {
  switch (phase) {
    case "starting":
      return "Iniciando";
    case "loading_datasets":
      return "Carregando datasets";
    case "benchmark_bootstrap":
      return "Benchmark bootstrap";
    case "benchmark_supervised":
      return "Benchmark supervisionado";
    case "persisting_artifacts":
      return "Persistindo artefatos";
    case "promoting_champion":
      return "Promovendo campeão";
    case "training_benchmark":
      return "Treino e benchmark";
    case "processing":
      return "Processando arquivos";
    case "completed":
      return "Concluído";
    case "failed":
      return "Falhou";
    default:
      return phase || "idle";
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function buildPendingIngestStatus(projectId: string | null): IngestOperationStatus {
  return {
    last_run_started_at: null,
    last_run_finished_at: null,
    duration_seconds: null,
    project_id: projectId,
    running: true,
    phase: "starting",
    progress_current: 0,
    progress_total: 0,
    progress_file: null,
    processed_count: 0,
    failed_count: 0,
    last_error: null,
  };
}

function buildPendingClassifierCycleStatus(previous: ClassifierCycleStatus | null): ClassifierCycleStatus {
  return {
    last_run_started_at: previous?.last_run_started_at ?? null,
    last_run_finished_at: null,
    duration_seconds: null,
    running: true,
    phase: "starting",
    progress_current: 0,
    progress_total: previous?.progress_total ?? 0,
    report_id: null,
    champion_mode: previous?.champion_mode ?? null,
    last_error: null,
  };
}

function flattenHistory(entries: IngestHistoryEntry[]): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const entry of entries) {
    const ts = entry.timestamp;
    for (const item of entry.items) {
      rows.push({
        key: `${ts}-${item.doc_id}`,
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
  const [classifierStatus, setClassifierStatus] = useState<ClassifierStatusResponse | null>(null);
  const [classifierReport, setClassifierReport] = useState<ClassifierReport | null>(null);
  const [classifierReports, setClassifierReports] = useState<ClassifierReportSummary[]>([]);
  const [classifierSaving, setClassifierSaving] = useState(false);
  const [classifierCycleStatus, setClassifierCycleStatus] = useState<ClassifierCycleStatus | null>(null);
  const [ingestStatus, setIngestStatus] = useState<IngestOperationStatus | null>(null);
  const ingestMonitorStopRef = useRef<(() => void) | null>(null);
  const classifierCycleMonitorStopRef = useRef<(() => void) | null>(null);

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

  const loadClassifierState = useCallback(async () => {
    try {
      const [cycle, ingest] = await Promise.all([
        fetchClassifierCycleStatus(),
        fetchIngestStatus()
      ]);
      setClassifierCycleStatus(cycle);
      setIngestStatus(ingest);
    } catch {
      /* ignore */
    }

    if (!isSingleProject) {
      setClassifierStatus(null);
      setClassifierReport(null);
      setClassifierReports([]);
      return;
    }

    try {
      const [status, reports, latest] = await Promise.all([
        fetchClassifierStatus(selectedProject),
        fetchClassifierReports(8),
        fetchClassifierReportLatest().catch(() => null)
      ]);
      setClassifierStatus(status);
      setClassifierReports(reports);
      setClassifierReport(latest);
    } catch {
      setClassifierStatus(null);
      setClassifierReports([]);
      setClassifierReport(null);
    }
  }, [isSingleProject, selectedProject]);

  useEffect(() => {
    void loadClassifierState();
  }, [loadClassifierState]);

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

  const stopIngestMonitor = useCallback(() => {
    ingestMonitorStopRef.current?.();
    ingestMonitorStopRef.current = null;
  }, []);

  const stopClassifierCycleMonitor = useCallback(() => {
    classifierCycleMonitorStopRef.current?.();
    classifierCycleMonitorStopRef.current = null;
  }, []);

  const startIngestMonitor = useCallback(
    (requestPromise: Promise<unknown>) => {
      stopIngestMonitor();
      let cancelled = false;
      let requestSettled = false;
      let stream: EventSource | null = null;

      void requestPromise.finally(() => {
        requestSettled = true;
      });

      const closeStream = () => {
        stream?.close();
        stream = null;
      };

      const applyStatus = (data: IngestOperationStatus) => {
        if (!cancelled) {
          setIngestStatus(data);
        }
      };

      const pollUntilFinished = async (): Promise<void> => {
        while (!cancelled) {
          try {
            const latest = await fetchIngestStatus();
            if (cancelled) return;
            applyStatus(latest);
            if (latest.running && typeof window !== "undefined" && typeof window.EventSource !== "undefined") {
              closeStream();
              stream = new window.EventSource(getIngestStatusStreamUrl());
              stream.onmessage = (event) => {
                try {
                  const data = JSON.parse(event.data) as IngestOperationStatus;
                  applyStatus(data);
                  if (!data.running) {
                    closeStream();
                  }
                } catch {
                  /* ignore */
                }
              };
              stream.onerror = () => {
                closeStream();
                if (!cancelled) {
                  void pollUntilFinished();
                }
              };
              return;
            }
            if (!latest.running && requestSettled) {
              return;
            }
          } catch {
            if (requestSettled) {
              return;
            }
          }
          await sleep(250);
        }
      };

      void pollUntilFinished();

      const stop = () => {
        cancelled = true;
        closeStream();
      };
      ingestMonitorStopRef.current = stop;
      return stop;
    },
    [stopIngestMonitor]
  );

  const startClassifierCycleMonitor = useCallback(() => {
    stopClassifierCycleMonitor();
    let cancelled = false;
    let stream: EventSource | null = null;

    const closeStream = () => {
      stream?.close();
      stream = null;
    };

    const applyStatus = (data: ClassifierCycleStatus) => {
      if (!cancelled) {
        setClassifierCycleStatus(data);
      }
    };

    const finish = () => {
      if (!cancelled) {
        void loadClassifierState();
      }
    };

    const pollUntilFinished = async (): Promise<void> => {
      while (!cancelled) {
        try {
          const latest = await fetchClassifierCycleStatus();
          if (cancelled) return;
          applyStatus(latest);
          if (latest.running && typeof window !== "undefined" && typeof window.EventSource !== "undefined") {
            closeStream();
            stream = new window.EventSource(getClassifierCycleStatusStreamUrl());
            stream.onmessage = (event) => {
              try {
                const data = JSON.parse(event.data) as ClassifierCycleStatus;
                applyStatus(data);
                if (!data.running) {
                  closeStream();
                  finish();
                }
              } catch {
                /* ignore */
              }
            };
            stream.onerror = () => {
              closeStream();
              if (!cancelled) {
                void pollUntilFinished();
              }
            };
            return;
          }
          if (!latest.running) {
            finish();
            return;
          }
        } catch {
          /* ignore */
        }
        await sleep(250);
      }
    };

    void pollUntilFinished();

    const stop = () => {
      cancelled = true;
      closeStream();
    };
    classifierCycleMonitorStopRef.current = stop;
    return stop;
  }, [loadClassifierState, stopClassifierCycleMonitor]);

  useEffect(() => {
    return () => {
      stopIngestMonitor();
      stopClassifierCycleMonitor();
    };
  }, [stopClassifierCycleMonitor, stopIngestMonitor]);

  async function handleClassifierOverrideChange(value: string) {
    if (!isSingleProject) return;
    const nextValue = value === AUTO_CLASSIFIER_OVERRIDE ? null : (value as OperationalClassifierMode);
    setClassifierSaving(true);
    try {
      const status = await updateClassifierOverride(selectedProject, nextValue);
      setClassifierStatus(status);
      onStatus(nextValue ? `Override do classificador salvo: ${nextValue}` : "Override do classificador limpo");
    } catch {
      onStatus("Falha ao salvar override do classificador");
    } finally {
      setClassifierSaving(false);
    }
  }

  async function handleStartClassifierCycle() {
    setClassifierCycleStatus((previous) => buildPendingClassifierCycleStatus(previous));
    try {
      await startClassifierCycle();
      startClassifierCycleMonitor();
      onStatus("Ciclo do classificador iniciado");
    } catch {
      stopClassifierCycleMonitor();
      void fetchClassifierCycleStatus().then(setClassifierCycleStatus).catch(() => {});
      onStatus("Falha ao iniciar ciclo do classificador");
    }
  }

  async function handleScan() {
    if (!selectedProject) return;
    setLoading(true);
    setIngestStatus(buildPendingIngestStatus(selectedProject === ALL_PROJECTS ? null : selectedProject));
    onStatus("Processando inbox...");
    try {
      const results: ScanResult[] = [];
      if (selectedProject === ALL_PROJECTS) {
        for (const project of projects) {
          const scanPromise = triggerScan(project.project_id);
          startIngestMonitor(scanPromise);
          results.push(await scanPromise);
        }
      } else {
        const scanPromise = triggerScan(selectedProject);
        startIngestMonitor(scanPromise);
        results.push(await scanPromise);
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
      stopIngestMonitor();
      void fetchIngestStatus().then(setIngestStatus).catch(() => {});
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

      {(loading ||
        ingestStatus?.running ||
        ingestStatus?.phase === "starting" ||
        ingestStatus?.phase === "completed" ||
        ingestStatus?.phase === "failed") && (
        <div className="itc-run-status">
          <strong>Processar INBOX:</strong>
          <span>{formatPhaseLabel(ingestStatus?.phase)}</span>
          <span>
            {ingestStatus?.progress_current ?? 0}/{ingestStatus?.progress_total ?? 0}
          </span>
          {ingestStatus?.progress_file && <code>{ingestStatus.progress_file}</code>}
        </div>
      )}

      {isSingleProject && (
        <details className="itc-collapsible" open>
          <summary className="itc-collapsible-header">
            Classificador operacional
            <span className="itc-badge-count">
              {classifierStatus ? formatClassifierModeLabel(classifierStatus.effective_mode) : "carregando"}
            </span>
          </summary>
          <div className="itc-collapsible-body">
            {classifierStatus && (
              <>
                <div className="itc-classifier-stats">
                  <div className="itc-classifier-stat">
                    <span className="itc-classifier-stat-label">Campeão</span>
                    <strong>{formatClassifierModeLabel(classifierStatus.champion_mode)}</strong>
                  </div>
                  <div className="itc-classifier-stat">
                    <span className="itc-classifier-stat-label">Efetivo neste projeto</span>
                    <strong>{formatClassifierModeLabel(classifierStatus.effective_mode)}</strong>
                  </div>
                  <div className="itc-classifier-stat">
                    <span className="itc-classifier-stat-label">Override</span>
                    <strong>{classifierStatus.override_mode ? formatClassifierModeLabel(classifierStatus.override_mode) : "auto"}</strong>
                  </div>
                  <div className="itc-classifier-stat">
                    <span className="itc-classifier-stat-label">Último ciclo</span>
                    <strong>{classifierStatus.latest_cycle_status}</strong>
                  </div>
                </div>

                <div className="itc-classifier-controls">
                  <div className="itc-llm-field">
                    <label htmlFor="itc-classifier-override">Override manual do projeto</label>
                    <select
                      id="itc-classifier-override"
                      value={classifierStatus.override_mode || AUTO_CLASSIFIER_OVERRIDE}
                      onChange={(e) => void handleClassifierOverrideChange(e.target.value)}
                      disabled={classifierSaving || !!classifierCycleStatus?.running}
                    >
                      <option value={AUTO_CLASSIFIER_OVERRIDE}>auto (usar campeão)</option>
                      {classifierStatus.available_modes.map((mode) => (
                        <option key={mode} value={mode}>
                          {formatClassifierModeLabel(mode)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => void handleStartClassifierCycle()}
                    disabled={!!classifierCycleStatus?.running}
                  >
                    {classifierCycleStatus?.running ? "Ciclo em andamento..." : "Rodar benchmark + retreino"}
                  </button>
                </div>

                <p className="itc-classifier-policy">
                  Promoção: {classifierStatus.promotion_policy} | gates: exact &ge; {formatPct(classifierStatus.promotion_gates.min_exact_match_accuracy)},
                  domínio &ge; {formatPct(classifierStatus.promotion_gates.min_business_domain_accuracy)},
                  tipo &ge; {formatPct(classifierStatus.promotion_gates.min_document_type_accuracy)}
                </p>
              </>
            )}

            {classifierCycleStatus && (
              <div className={`itc-classifier-cycle${classifierCycleStatus.running ? " active" : ""}`}>
                <strong>Ciclo:</strong> {formatPhaseLabel(classifierCycleStatus.phase)}
                <span>
                  {classifierCycleStatus.progress_current}/{classifierCycleStatus.progress_total}
                </span>
                {classifierCycleStatus.last_error && <span className="itc-classifier-cycle-error">{classifierCycleStatus.last_error}</span>}
              </div>
            )}

            {classifierReport && (
              <div className="itc-classifier-benchmark">
                <div className="itc-classifier-benchmark-head">
                  <strong>Benchmark oficial</strong>
                  {classifierReport.report_id && <span className="itc-scan-timestamp">{classifierReport.report_id}</span>}
                </div>
                <table className="itc-scan-table itc-classifier-table">
                  <thead>
                    <tr>
                      <th>Modo</th>
                      <th>Domínio</th>
                      <th>Tipo</th>
                      <th>Exact match</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {["bootstrap", "sparse_logreg", "sparse_linear_svc"].map((mode) => {
                      const benchmark = classifierReport.benchmarks[mode];
                      if (!benchmark) return null;
                      const summary = benchmark.summary;
                      const isChampion = classifierReport.champion?.mode === mode;
                      return (
                        <tr key={mode}>
                          <td>
                            {formatClassifierModeLabel(mode)}
                            {isChampion && <span className="itc-classifier-champion">campeão</span>}
                          </td>
                          <td>{formatPct(summary.business_domain_accuracy)}</td>
                          <td>{formatPct(summary.document_type_accuracy)}</td>
                          <td>{formatPct(summary.exact_match_accuracy)}</td>
                          <td>{summary.skipped ? "skip" : "ok"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {classifierReports.length > 0 && (
              <div className="itc-classifier-history">
                <strong>Evolução recente</strong>
                <ul className="list">
                  {classifierReports.slice(0, 5).map((report) => (
                    <li key={report.report_id} className="list-item">
                      <span className="list-title">{report.report_id}</span>
                      <div className="sub list-meta">
                        campeão: {formatClassifierModeLabel(report.champion_mode)} | exact: {formatPct(report.champion_summary?.exact_match_accuracy)}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </details>
      )}

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
                      <option value="full_override">full_override — pode mudar domínio</option>
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
                const hasLlmContext =
                  item.classifier_mode ||
                  item.llm_explanation ||
                  item.rule_business_domain ||
                  item.llm_proposed_business_domain ||
                  item.business_domain_confidence != null ||
                  item.document_type_confidence != null ||
                  item.classifier_fallback_reason;
                const suggestedBusinessDomain = item.suggested_business_domain;
                return (
                  <li key={item.doc_id} className="list-item">
                    <strong className="list-title">{item.filename}</strong>
                    <div className="sub list-meta">
                      projeto: {projectLabelById.get(item.project_id) || item.project_id} | sugestão:{" "}
                      {suggestedBusinessDomain || "sem sugestão"}
                      {item.suggested_document_type ? ` / ${item.suggested_document_type}` : ""}
                      {" "} | confiança: {item.confidence_score.toFixed(2)}
                    </div>

                    {hasLlmContext && (
                      <div className="itc-triage-llm-context">
                        <p>
                          Classificador: <code>{formatClassifierModeLabel(item.classifier_mode)}</code>
                          {item.classifier_requested_mode && item.classifier_requested_mode !== item.classifier_mode
                            ? ` (solicitado: ${formatClassifierModeLabel(item.classifier_requested_mode)})`
                            : ""}
                        </p>
                        <p>
                          Scores: domínio {formatPct(item.business_domain_confidence)} | tipo {formatPct(item.document_type_confidence)} | final {item.confidence_score.toFixed(2)}
                        </p>
                        {item.classifier_fallback_reason && (
                          <p>Fallback: <code>{item.classifier_fallback_reason}</code></p>
                        )}
                        {item.rule_business_domain && (
                          <p>Regra: <code>{item.rule_business_domain}</code> (conf {(item.rule_confidence ?? 0).toFixed(2)})</p>
                        )}
                        {item.llm_explanation && <p>LLM: <em>{item.llm_explanation}</em></p>}
                        {item.llm_proposed_business_domain && (
                          <p className="itc-proposed-area">Domínio proposto: <code>{item.llm_proposed_business_domain}</code></p>
                        )}
                      </div>
                    )}

                    <div className="row">
                      <button
                        className="btn"
                        disabled={!suggestedBusinessDomain}
                        title={!suggestedBusinessDomain ? "Sem sugestão de domínio" : ""}
                        onClick={() => void onDecision(item, "approve")}
                      >
                        Aprovar
                      </button>
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
