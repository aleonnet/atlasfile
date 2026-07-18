import { ChevronDown, ChevronRight, RefreshCw, Settings, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelClassifierCycle,
  deleteClassifierReport,
  fetchDatasetReadiness,
  fetchClassifierCycleStatus,
  fetchClassifierReportLatest,
  fetchClassifierReports,
  fetchClassifierStatus,
  fetchModels,
  fetchProjectProfile,
  getClassifierCycleStatusStreamUrl,
  startClassifierCycle,
  updateBenchmarkEnabledModes,
  updateClassifierOverride,
  updateProjectProfile
} from "../../api";
import type {
  ClassifierCycleStatus,
  ClassifierReport,
  DatasetReadiness,
  ClassifierReportSummary,
  ClassifierStatusResponse,
  LLMPolicy,
  ModelOption,
  OperationalClassifierMode,
  ProjectProfileV2,
  TriageItem
} from "../../types";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { CollapsibleSection, rowDeleteButtonClass } from "../../components/ui/collapsible-section";
import { DataTable, TableWrap } from "../../components/ui/data-table";
import { EmptyState } from "../../components/ui/empty-state";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { cn } from "../../lib/utils";

/* Bloco de progresso de operação (ingest / ciclo do classificador) */
const opProgressClass = "mb-2.5 flex flex-col gap-1 rounded-md border border-border bg-elevated px-3 py-2.5";
const opPhaseClass = "m-0 text-[0.8rem] font-medium text-foreground";
const opBarWrapClass = "my-0.5 h-1.5 overflow-hidden rounded-full bg-border";
const opBarFillClass = "h-full rounded-full bg-accent transition-[width] duration-300 ease-out";
const opStatsClass = "m-0 text-[0.78rem] text-muted-foreground";
const opFileClass = "m-0 truncate text-xs text-muted-foreground";
const checkboxLabelClass = "flex items-center gap-1.5 text-sm [&_input]:size-3.5 [&_input]:accent-[var(--accent)]";

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

type Props = {
  selectedProject: string;
  selectedProjectLabel: string;
  triageItems: TriageItem[];
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
  triageItems,
  onStatus,
  openaiApiKey,
  anthropicApiKey,
  onOpenSettings,
  selectedModelTriage,
  onChangeModelTriage
}: Props) {
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
  const [datasetReadiness, setDatasetReadiness] = useState<DatasetReadiness | null>(null);
  const classifierCycleMonitorStopRef = useRef<(() => void) | null>(null);

  const isSingleProject = selectedProject !== ALL_PROJECTS;

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
      const [cycle, readiness] = await Promise.all([
        fetchClassifierCycleStatus(),
        fetchDatasetReadiness().catch(() => null)
      ]);
      setClassifierCycleStatus(cycle);
      setDatasetReadiness(readiness);
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

  const stopClassifierCycleMonitor = useCallback(() => {
    classifierCycleMonitorStopRef.current?.();
    classifierCycleMonitorStopRef.current = null;
  }, []);

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
      stopClassifierCycleMonitor();
    };
  }, [stopClassifierCycleMonitor]);

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
      const started = await startClassifierCycle();
      startClassifierCycleMonitor();
      const moved = started.auto_backfill_moved ?? 0;
      onStatus(
        moved > 0
          ? `Ciclo iniciado — ${moved} documento(s) reservado(s) automaticamente para validação`
          : "Ciclo do classificador iniciado"
      );
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

  const currentProviderModel = `${llmPolicy.provider}/${llmPolicy.model}`;
  const modelLabel = models.find((m) => `${m.provider}/${m.model}` === currentProviderModel)?.label;
  const hasKey =
    (llmPolicy.provider === "openai" && !!openaiApiKey) ||
    (llmPolicy.provider === "anthropic" && !!anthropicApiKey);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex min-h-9 items-center gap-2">
          <Sparkles className="size-4 text-accent" aria-hidden />
          Classificador
        </CardTitle>
      </CardHeader>
      <CardContent>

      {!isSingleProject && (
        <EmptyState
          icon={<Sparkles aria-hidden />}
          title="Nenhum projeto selecionado"
          description="Selecione um projeto específico para configurar o classificador, os modos de benchmark e a política LLM."
        />
      )}

      {isSingleProject && selectedProjectLabel && (
        <div className="mb-1 flex items-center gap-1.5 pb-1 text-[0.82rem] text-muted-foreground">
          <span className="font-medium text-foreground">{selectedProjectLabel}</span>
          {triageItems.length > 0 && (
            <span className="text-accent">
              · {triageItems.length} pendente{triageItems.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      )}

      {isSingleProject && (
        <CollapsibleSection
          className="mt-2"
          title="Classificador operacional"
          badge={
            <Badge className="ml-auto">
              {classifierStatus ? formatClassifierModeLabel(classifierStatus.effective_mode) : "carregando"}
            </Badge>
          }
        >
            {classifierStatus && (
              <>
                <div className="mb-2.5 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                  {[
                    { label: "Campeão", value: formatClassifierModeLabel(classifierStatus.champion_mode) },
                    { label: "Efetivo neste projeto", value: formatClassifierModeLabel(classifierStatus.effective_mode) },
                    { label: "Override", value: classifierStatus.override_mode ? formatClassifierModeLabel(classifierStatus.override_mode) : "auto" },
                    { label: "Último ciclo", value: classifierStatus.latest_cycle_status },
                  ].map((stat) => (
                    <div key={stat.label} className="flex flex-col gap-1 rounded-md border border-border bg-background p-2.5">
                      <span className="font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">{stat.label}</span>
                      <strong className="font-display text-sm text-foreground-strong">{stat.value}</strong>
                    </div>
                  ))}
                </div>

                <div className="mb-2 flex flex-wrap items-end gap-2.5">
                  <select
                    id="itc-classifier-override"
                    aria-label="Override do classificador"
                    className={cn(nativeSelectClass, "w-auto min-w-52 flex-initial")}
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
                  <div className="relative">
                    <Button
                      variant={classifierCycleStatus?.running && !cancellingCycle ? "destructive" : "secondary"}
                      disabled={cancellingCycle || (!classifierCycleStatus?.running && datasetReadiness?.cycle_ready === false)}
                      title={
                        !classifierCycleStatus?.running && datasetReadiness?.cycle_ready === false
                          ? datasetReadiness.blockers[0]?.message
                          : undefined
                      }
                      onClick={() => {
                        if (classifierCycleStatus?.running) {
                          setConfirmCancelCycle(true);
                        } else {
                          void handleStartClassifierCycle();
                        }
                      }}
                    >
                      {cancellingCycle ? "Cancelando..." : classifierCycleStatus?.running ? "Cancelar ciclo" : (<><RefreshCw /> Rodar ciclo</>)}
                    </Button>
                    {confirmCancelCycle && classifierCycleStatus?.running && (
                      <div className="absolute right-0 top-[calc(100%+6px)] z-20 flex min-w-52 flex-col gap-2 rounded-md border border-border bg-panel p-3 shadow-[0_4px_12px_rgba(0,0,0,0.25)]">
                        <p className="m-0 text-[0.82rem] text-foreground">Cancelar o ciclo em andamento?</p>
                        <div className="flex gap-1.5">
                          <Button variant="destructive" size="sm" onClick={() => void handleCancelCycle()}>Confirmar</Button>
                          <Button variant="secondary" size="sm" onClick={() => setConfirmCancelCycle(false)}>Não</Button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="mb-2 flex flex-wrap items-center gap-x-3.5 gap-y-1.5">
                  {(["bootstrap", "sparse_logreg", "llm"] as const).map((mode) => {
                    const enabled = classifierStatus.benchmark_enabled_modes?.includes(mode) ?? (mode !== "llm");
                    return (
                      <label key={mode} className={checkboxLabelClass}>
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

                {datasetReadiness && !datasetReadiness.cycle_ready && !classifierCycleStatus?.running && (
                  <div className="mb-2.5 rounded-md border border-accent/30 bg-accent-soft/30 px-3 py-2.5">
                    {datasetReadiness.blockers.map((b) => (
                      <p key={b.code} className="m-0 text-[0.8rem] text-foreground">{b.message}</p>
                    ))}
                    <p className="m-0 mt-1 font-mono text-[0.68rem] text-tertiary">
                      validação rotulada: {datasetReadiness.validation.labeled} · treino: {datasetReadiness.training.records}
                    </p>
                  </div>
                )}
                {datasetReadiness?.cycle_ready &&
                  datasetReadiness.suggestions
                    .filter((s) => s.code === "sparse_gate_not_met" || s.code === "auto_backfill_on_run")
                    .map((s) => (
                      <p key={s.code} className="mb-2 text-[0.75rem] text-muted-foreground">{s.message}</p>
                    ))}

                <p className="mb-2.5 text-[0.78rem] text-muted-foreground">
                  Promoção: {classifierStatus.promotion_policy === "auto_best_with_ui_override" ? "Automático — melhor score" : classifierStatus.promotion_policy} | gate: exact &ge; {formatPct(classifierStatus.promotion_gates.min_exact_match_accuracy)}
                </p>
              </>
            )}

            {classifierCycleStatus && (classifierCycleStatus.running || classifierCycleStatus.phase === "failed" || classifierCycleStatus.phase === "cancelled") && (
              <div className={opProgressClass}>
                <p className={cn(opPhaseClass, classifierCycleStatus.phase === "failed" && "text-destructive", classifierCycleStatus.phase === "cancelled" && "text-accent")}>
                  {cancellingCycle && classifierCycleStatus.running ? "Aguardando cancelamento..." : formatPhaseLabel(classifierCycleStatus.phase)}
                </p>
                {classifierCycleStatus.running && (
                  <>
                    <div className={opBarWrapClass}>
                      <div
                        className={opBarFillClass}
                        style={{
                          width: (classifierCycleStatus.progress_total ?? 0) > 0
                            ? `${Math.min(100, (100 * (classifierCycleStatus.progress_current ?? 0)) / classifierCycleStatus.progress_total!)}%`
                            : "0%"
                        }}
                      />
                    </div>
                    <p className={opStatsClass}>
                      {classifierCycleStatus.progress_current} / {classifierCycleStatus.progress_total}
                    </p>
                  </>
                )}
                {classifierCycleStatus.last_error && (
                  <p className={opFileClass}>{classifierCycleStatus.last_error}</p>
                )}
              </div>
            )}

            {(classifierReport || classifierCycleStatus?.benchmarks) && (() => {
              const liveBenchmarks = classifierCycleStatus?.running ? classifierCycleStatus.benchmarks : undefined;
              const reportBenchmarks = classifierReport?.benchmarks;
              const source = liveBenchmarks || reportBenchmarks;
              if (!source && !liveBenchmarks) return null;
              return (
                <div>
                  <div className="mb-1.5 mt-3.5 flex items-center gap-2.5">
                    <strong className="font-display text-sm font-bold text-foreground-strong">Benchmark oficial</strong>
                  </div>
                  <TableWrap>
                  <DataTable>
                    <thead>
                      <tr>
                        <th className="left">Modo</th>
                        <th>Domínio</th>
                        <th>Tipo</th>
                        <th>Exact match</th>
                        <th className="left">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(["bootstrap", "sparse_logreg", "llm"] as const).map((mode) => {
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
                          <tr key={mode} className={cn(isSkipped && "opacity-45", isLive && "text-foreground")}>
                            <td className="left">
                              {formatClassifierModeLabel(mode)}
                              {isChampion && <Badge variant="success" className="ml-1.5 uppercase">campeão</Badge>}
                              {isSkipped && <span className="ml-1 text-[0.72rem] text-muted-foreground">skip</span>}
                            </td>
                            <td>{formatPct(displaySummary.business_domain_accuracy)}</td>
                            <td>{formatPct(displaySummary.document_type_accuracy)}</td>
                            <td>{formatPct(displaySummary.exact_match_accuracy)}</td>
                            <td className="left">{isSkipped ? "skip" : "ok"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </DataTable>
                  </TableWrap>
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
                <div className="mt-3">
                  <strong className="font-display text-sm font-bold text-foreground-strong">Gate warnings</strong>
                  <ul className="m-0 flex list-none flex-col gap-1 p-0 font-mono text-[0.72rem]">
                    {allWarnings.map((w, i) => <li key={i}><code>{w}</code></li>)}
                  </ul>
                </div>
              );
            })()}

            {classifierReports.length > 0 && (
              <div className="mt-2.5">
                <strong className="font-display text-sm font-bold text-foreground-strong">Evolução recente</strong>
                <TableWrap className="mt-1.5">
                <DataTable>
                  <thead>
                    <tr>
                      <th className="left">Ciclo</th>
                      <th className="left">Campeão</th>
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
                        <tr key={report.report_id} className={isChampion ? "[&_td]:font-semibold" : ""}>
                          <td className="left whitespace-nowrap text-muted-foreground">{ts}</td>
                          <td className="left">{formatClassifierModeLabel(report.champion_mode)}</td>
                          <td>{formatPct(report.champion_summary?.exact_match_accuracy)}</td>
                          <td>{formatPct(report.champion_summary?.business_domain_macro_f1)}</td>
                          <td>
                            <button
                              className={rowDeleteButtonClass}
                              disabled={isChampion || deletingReportId === report.report_id}
                              onClick={() => setConfirmDeleteReportId(report.report_id)}
                              title={isChampion ? "Campeão ativo — não pode ser deletado" : "Deletar relatório"}
                            >×</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </DataTable>
                </TableWrap>
              </div>
            )}
        </CollapsibleSection>
      )}

      {confirmDeleteReportId && (
        <ModalShell label="Confirmar exclusão" title="Excluir relatório" size="sm">
            <p className="m-0 text-sm text-foreground">
              Tem certeza que deseja excluir o relatório <strong>{confirmDeleteReportId}</strong>? Esta ação não pode ser desfeita.
            </p>
            <ModalActions>
              <Button variant="secondary" onClick={() => setConfirmDeleteReportId(null)}>Cancelar</Button>
              <Button variant="destructive" onClick={handleDeleteReport}>Excluir</Button>
            </ModalActions>
        </ModalShell>
      )}

      {/* ── Classificação LLM ── */}
      {isSingleProject && (
        <CollapsibleSection
          className="mt-2"
          title="Classificação LLM"
          badge={
            <Badge variant={llmPolicy.enabled ? "success" : "destructive"} className="ml-auto">
              {llmPolicy.enabled ? "● ativado" : "○ desativado"}
            </Badge>
          }
        >
            <div className="mb-2.5 flex items-center gap-3">
              <label className={checkboxLabelClass}>
                <input
                  type="checkbox"
                  checked={llmPolicy.enabled}
                  onChange={() => handleToggleLlm()}
                  disabled={llmSaving}
                />
                LLM ativado
              </label>
              {llmSaving && <span className="text-[0.78rem] italic text-muted-foreground">salvando...</span>}
            </div>

            {llmPolicy.enabled && (
              <>
                <div className="mt-2 grid gap-2.5 lg:grid-cols-2">
                  <div className="flex flex-col">
                    <label htmlFor="itc-llm-mode" className={fieldLabelClass}>Modo</label>
                    <select
                      id="itc-llm-mode"
                      className={nativeSelectClass}
                      value={llmPolicy.mode}
                      onChange={(e) => handleModeChange(e.target.value as LLMPolicy["mode"])}
                      disabled={llmSaving}
                    >
                      <option value="tag_only">tag_only — enriquece tags/tipo</option>
                      <option value="review">review — revisa e pode ir p/ triagem</option>
                      <option value="full_override">full_override — pode mudar domínio</option>
                    </select>
                  </div>
                  <div className="flex flex-col">
                    <label htmlFor="itc-llm-model" className={fieldLabelClass}>Modelo triagem</label>
                    <div className="flex items-center gap-2">
                      <select
                        id="itc-llm-model"
                        className={nativeSelectClass}
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
                        className="inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-transparent p-0 text-muted-foreground transition-colors hover:border-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={onOpenSettings}
                        title="Configurar modelos e chaves"
                      >
                        <Settings size={16} />
                      </button>
                    </div>
                  </div>
                </div>

                {!hasKey && (
                  <div className="mt-2 flex items-center gap-2 rounded-md border border-[rgba(255,200,50,0.25)] bg-[rgba(255,200,50,0.1)] px-2.5 py-1.5 text-[0.82rem] text-foreground">
                    <span>⚠ API Key não configurada para {llmPolicy.provider}.</span>
                    <Button variant="outline" size="sm" onClick={onOpenSettings}>
                      Configurar
                    </Button>
                  </div>
                )}
              </>
            )}
        </CollapsibleSection>
      )}

      </CardContent>
    </Card>
  );
}
