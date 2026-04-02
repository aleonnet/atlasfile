import { ChevronDown, ChevronRight, RefreshCw, Settings } from "lucide-react";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelClassifierCycle,
  deleteClassifierReport,
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
  updateBenchmarkEnabledModes,
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
    case "setfit":
      return "setfit";
    case "llm":
      return "llm";
    default:
      return mode || "—";
  }
}

function formatPhaseLabel(phase?: string | null): string {
  if (!phase) return "";
  if (phase.startsWith("baseline:")) {
    const model = phase.slice("baseline:".length);
    return `Baseline ${model}`;
  }
  if (phase.startsWith("benchmark:")) {
    const model = phase.slice("benchmark:".length);
    return `Benchmark ${model}`;
  }
  switch (phase) {
    case "starting":
      return "Iniciando";
    case "extracting":
      return "Extraindo conteúdos";
    case "processing":
      return "Processando arquivos";
    case "completed":
      return "Concluído";
    case "cancelled":
      return "Cancelado";
    case "failed":
      return "Falhou";
    default:
      return phase;
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
  selectedModelTriage?: string;
  onChangeModelTriage?: (providerModel: string) => void;
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
  onOpenSettings,
  selectedModelTriage,
  onChangeModelTriage
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
  const [confirmDeleteReportId, setConfirmDeleteReportId] = useState<string | null>(null);
  const [deletingReportId, setDeletingReportId] = useState<string | null>(null);
  const [classifierSaving, setClassifierSaving] = useState(false);
  const [confirmCancelCycle, setConfirmCancelCycle] = useState(false);
  const [cancellingCycle, setCancellingCycle] = useState(false);
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
      const resolved = policy ? { ...DEFAULT_LLM_POLICY, ...policy } : DEFAULT_LLM_POLICY;
      setLlmPolicy(resolved);
      onChangeModelTriage?.(`${resolved.provider}/${resolved.model}`);
    } catch {
      /* profile not available yet */
    }
  }, [selectedProject, isSingleProject, onChangeModelTriage]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  // Sync: modal changed selectedModelTriage → update project profile
  useEffect(() => {
    if (!selectedModelTriage || !fullProfile || !isSingleProject) return;
    const currentProviderModelSync = `${llmPolicy.provider}/${llmPolicy.model}`;
    if (selectedModelTriage === currentProviderModelSync) return;
    const [provider, model] = selectedModelTriage.split("/");
    if (!provider || !model) return;
    const nextPolicy: LLMPolicy = {
      ...llmPolicy,
      provider: provider as LLMPolicy["provider"],
      model
    };
    setLlmPolicy(nextPolicy);
    void persistLlmPolicy(nextPolicy);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModelTriage]);

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
    onChangeModelTriage?.(providerModel);
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

  useEffect(() => {
    if (!classifierCycleStatus?.running) {
      setCancellingCycle(false);
    }
  }, [classifierCycleStatus?.running]);

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

  async function handleDeleteReport() {
    const reportId = confirmDeleteReportId;
    if (!reportId) return;
    setConfirmDeleteReportId(null);
    setDeletingReportId(reportId);
    try {
      await deleteClassifierReport(reportId);
      setClassifierReports(prev => prev.filter(r => r.report_id !== reportId));
    } catch {
      // falha silenciosa — o relatório permanece na lista
    } finally {
      setDeletingReportId(null);
    }
  }

  async function handleToggleBenchmarkMode(mode: string) {
    if (!classifierStatus) return;
    const current = classifierStatus.benchmark_enabled_modes || [];
    const next = current.includes(mode) ? current.filter((m) => m !== mode) : [...current, mode];
    setClassifierSaving(true);
    try {
      const status = await updateBenchmarkEnabledModes(next);
      setClassifierStatus(status);
    } catch {
      onStatus("Falha ao salvar modos de benchmark");
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

  async function handleCancelCycle() {
    setConfirmCancelCycle(false);
    setCancellingCycle(true);
    try {
      await cancelClassifierCycle();
      onStatus("Sinal de cancelamento enviado");
    } catch {
      setCancellingCycle(false);
      onStatus("Falha ao cancelar ciclo");
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
      onStatus(`Inbox processado: ${totals.processed} arquivo${totals.processed !== 1 ? "s" : ""}, ${totals.failed} falha${totals.failed !== 1 ? "s" : ""}`);
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

      {isSingleProject && selectedProjectLabel && (
        <div className="itc-project-header">
          <span className="itc-project-label">{selectedProjectLabel}</span>
          {triageItems.length > 0 && (
            <span className="itc-project-pending">
              · {triageItems.length} pendente{triageItems.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      )}

      {(loading || ingestStatus?.running ||
        ingestStatus?.phase === "starting" ||
        ingestStatus?.phase === "extracting" ||
        ingestStatus?.phase === "processing") && (
        <div className="itc-op-progress">
          <p className="itc-op-phase">{formatPhaseLabel(ingestStatus?.phase) || "Iniciando..."}</p>
          <div className="itc-op-bar-wrap">
            <div
              className="itc-op-bar-fill"
              style={{
                width: (ingestStatus?.progress_total ?? 0) > 0
                  ? `${Math.min(100, (100 * (ingestStatus?.progress_current ?? 0)) / ingestStatus!.progress_total!)}%`
                  : "0%"
              }}
            />
          </div>
          <p className="itc-op-stats">
            {ingestStatus?.progress_current ?? 0} / {ingestStatus?.progress_total ?? 0} arquivo{(ingestStatus?.progress_total ?? 0) !== 1 ? "s" : ""}
          </p>
          {ingestStatus?.progress_file && (
            <p className="itc-op-file">{ingestStatus.progress_file}</p>
          )}
        </div>
      )}

      {ingestStatus?.phase === "failed" && !loading && !ingestStatus?.running && (
        <div className="itc-op-progress itc-op-error">
          <p className="itc-op-phase">Falhou</p>
          {ingestStatus.last_error && <p className="itc-op-file">{ingestStatus.last_error}</p>}
        </div>
      )}

      {isSingleProject && (
        <details className="itc-collapsible">
          <summary className="itc-collapsible-header">
            Classificador operacional
            <span className="itc-badge itc-badge-accent">
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
                    <select
                      id="itc-classifier-override"
                      aria-label="Override do classificador"
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
                  <div className="itc-cycle-btn-wrap">
                    <button
                      type="button"
                      className={`btn${classifierCycleStatus?.running && !cancellingCycle ? " danger" : ""}`}
                      disabled={cancellingCycle}
                      onClick={() => {
                        if (classifierCycleStatus?.running) {
                          setConfirmCancelCycle(true);
                        } else {
                          void handleStartClassifierCycle();
                        }
                      }}
                    >
                      {cancellingCycle ? "Cancelando..." : classifierCycleStatus?.running ? "Cancelar ciclo" : "Rodar ciclo"}
                    </button>
                    {confirmCancelCycle && classifierCycleStatus?.running && (
                      <div className="itc-confirm-popover">
                        <p>Cancelar o ciclo em andamento?</p>
                        <div className="itc-confirm-actions">
                          <button type="button" className="btn danger" onClick={() => void handleCancelCycle()}>Confirmar</button>
                          <button type="button" className="btn" onClick={() => setConfirmCancelCycle(false)}>Não</button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="itc-benchmark-modes">
                  {(["bootstrap", "sparse_logreg", "setfit", "llm"] as const).map((mode) => {
                    const enabled = classifierStatus.benchmark_enabled_modes?.includes(mode) ?? (mode !== "setfit" && mode !== "llm");
                    return (
                      <label key={mode} className="checkbox-inline">
                        <input
                          type="checkbox"
                          checked={enabled}
                          disabled={classifierSaving || !!classifierCycleStatus?.running}
                          onChange={() => void handleToggleBenchmarkMode(mode)}
                        />
                        {formatClassifierModeLabel(mode)}
                      </label>
                    );
                  })}
                </div>

                <p className="itc-classifier-policy">
                  Promoção: {classifierStatus.promotion_policy === "auto_best_with_ui_override" ? "Automático — melhor score" : classifierStatus.promotion_policy} | gate: exact &ge; {formatPct(classifierStatus.promotion_gates.min_exact_match_accuracy)}
                </p>
              </>
            )}

            {classifierCycleStatus && (classifierCycleStatus.running || classifierCycleStatus.phase === "failed" || classifierCycleStatus.phase === "cancelled") && (
              <div className={`itc-op-progress${classifierCycleStatus.phase === "failed" ? " itc-op-error" : classifierCycleStatus.phase === "cancelled" ? " itc-op-cancelled" : ""}`}>
                <p className="itc-op-phase">{cancellingCycle && classifierCycleStatus.running ? "Aguardando cancelamento..." : formatPhaseLabel(classifierCycleStatus.phase)}</p>
                {classifierCycleStatus.running && (
                  <>
                    <div className="itc-op-bar-wrap">
                      <div
                        className="itc-op-bar-fill"
                        style={{
                          width: (classifierCycleStatus.progress_total ?? 0) > 0
                            ? `${Math.min(100, (100 * (classifierCycleStatus.progress_current ?? 0)) / classifierCycleStatus.progress_total!)}%`
                            : "0%"
                        }}
                      />
                    </div>
                    <p className="itc-op-stats">
                      {classifierCycleStatus.progress_current} / {classifierCycleStatus.progress_total}
                    </p>
                  </>
                )}
                {classifierCycleStatus.last_error && (
                  <p className="itc-op-file">{classifierCycleStatus.last_error}</p>
                )}
              </div>
            )}

            {(classifierReport || classifierCycleStatus?.benchmarks) && (() => {
              const liveBenchmarks = classifierCycleStatus?.running ? classifierCycleStatus.benchmarks : undefined;
              const reportBenchmarks = classifierReport?.benchmarks;
              const source = liveBenchmarks || reportBenchmarks;
              if (!source && !liveBenchmarks) return null;
              return (
                <div className="itc-classifier-benchmark">
                  <div className="itc-classifier-benchmark-head">
                    <strong>Benchmark oficial</strong>
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
                      {(["bootstrap", "sparse_logreg", "setfit", "llm"] as const).map((mode) => {
                        const liveSummary = liveBenchmarks?.[mode]?.summary;
                        const reportSummary = reportBenchmarks?.[mode]?.summary;
                        const liveIsSkipped = liveSummary?.skipped === true;
                        // Saved report: mode was skipped but may have inherited metrics from previous cycle
                        const reportIsSkipped = !liveBenchmarks && reportSummary?.skipped === true;
                        const isSkipped = liveIsSkipped || reportIsSkipped;
                        // Live: fall back to reportSummary (previous report) for inherited values
                        const displaySummary = (liveIsSkipped && reportSummary) ? reportSummary : (liveSummary || reportSummary);
                        if (!displaySummary) return null;
                        const isChampion = !liveBenchmarks && classifierReport?.champion?.mode === mode;
                        const isLive = !!liveSummary && !liveIsSkipped;
                        return (
                          <tr key={mode} style={{ opacity: isSkipped ? 0.45 : 1, color: isLive ? "var(--text)" : undefined }}>
                            <td>
                              {formatClassifierModeLabel(mode)}
                              {isChampion && <span className="itc-classifier-champion">campeão</span>}
                              {isSkipped && <span style={{ color: "var(--muted)", fontSize: "0.72rem", marginLeft: 4 }}>skip</span>}
                            </td>
                            <td>{formatPct(displaySummary.business_domain_accuracy)}</td>
                            <td>{formatPct(displaySummary.document_type_accuracy)}</td>
                            <td>{formatPct(displaySummary.exact_match_accuracy)}</td>
                            <td>{isSkipped ? "skip" : "ok"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })()}

            {classifierReport?.gates && (() => {
              const gateEntries = Object.entries(classifierReport.gates) as [string, Record<string, unknown>][];
              const allWarnings = gateEntries.flatMap(([name, gate]) => {
                const warnings = (gate?.warnings ?? []) as string[];
                return warnings.map((w) => `${name}: ${w}`);
              });
              if (!allWarnings.length) return null;
              return (
                <div className="itc-gate-warnings">
                  <strong>Gate warnings</strong>
                  <ul className="list">
                    {allWarnings.map((w, i) => <li key={i}><code>{w}</code></li>)}
                  </ul>
                </div>
              );
            })()}

            {classifierReports.length > 0 && (
              <div className="itc-classifier-history">
                <strong>Evolução recente</strong>
                <table className="itc-history-table">
                  <thead>
                    <tr>
                      <th>Ciclo</th>
                      <th>Campeão</th>
                      <th>exact</th>
                      <th>bd F1</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {classifierReports.slice(0, 8).map((report) => {
                      const isChampion = report.report_id === classifierStatus?.champion_report_id;
                      const ts = report.generated_at
                        ? new Date(report.generated_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
                        : report.report_id;
                      return (
                        <tr key={report.report_id} className={isChampion ? "itc-history-champion" : ""}>
                          <td className="itc-history-ts">{ts}</td>
                          <td>{formatClassifierModeLabel(report.champion_mode)}</td>
                          <td>{formatPct(report.champion_summary?.exact_match_accuracy)}</td>
                          <td>{formatPct(report.champion_summary?.business_domain_macro_f1)}</td>
                          <td>
                            <button
                              className="btn danger"
                              style={{ padding: "2px 6px", fontSize: "0.75rem" }}
                              disabled={isChampion || deletingReportId === report.report_id}
                              onClick={() => setConfirmDeleteReportId(report.report_id)}
                              title={isChampion ? "Campeão ativo — não pode ser deletado" : "Deletar relatório"}
                            >×</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </details>
      )}

      {confirmDeleteReportId && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Confirmar exclusão">
          <div className="modal tmpl-confirm-modal">
            <div className="modal-header">
              <h3>Excluir relatório</h3>
            </div>
            <p style={{ margin: "12px 0 18px", fontSize: "0.88rem", color: "var(--text)" }}>
              Tem certeza que deseja excluir o relatório <strong>{confirmDeleteReportId}</strong>? Esta ação não pode ser desfeita.
            </p>
            <div className="modal-actions">
              <button className="btn" onClick={() => setConfirmDeleteReportId(null)}>Cancelar</button>
              <button className="btn danger" onClick={handleDeleteReport}>Excluir</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Classificação LLM ── */}
      {isSingleProject && (
        <details className="itc-collapsible">
          <summary className="itc-collapsible-header">
            Classificação LLM
            <span className={`itc-badge ${llmPolicy.enabled ? "itc-badge-on" : "itc-badge-off"}`}>
              {llmPolicy.enabled ? "● ativado" : "○ desativado"}
            </span>
          </summary>
          <div className="itc-collapsible-body">
            <div className="itc-llm-row">
              <label className="checkbox-inline">
                <input
                  type="checkbox"
                  checked={llmPolicy.enabled}
                  onChange={() => handleToggleLlm()}
                  disabled={llmSaving}
                />
                LLM ativado
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

      {/* ── Processamentos (tabela plana, paginada) ── */}
      {allRows.length > 0 && (
        <details className="itc-collapsible">
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
        <details className="itc-collapsible">
          <summary className="itc-collapsible-header">
            Itens pendentes de triagem
            <span className="itc-badge itc-badge-pending">{triageItems.length}</span>
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
