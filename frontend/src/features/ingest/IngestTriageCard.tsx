import { ChevronDown, ChevronRight, RefreshCw, Settings, Sparkles } from "lucide-react";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
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
import i18n from "../../i18n";
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
  StatusSeverity,
  TriageItem
} from "../../types";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { ProjectHeaderMeta } from "../../components/ProjectHeaderMeta";
import { CollapsibleSection, rowDeleteButtonClass } from "../../components/ui/collapsible-section";
import { DataTable, TableWrap } from "../../components/ui/data-table";
import { EmptyState } from "../../components/ui/empty-state";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { cn } from "../../lib/utils";
import { apiErrorMessage } from "../../lib/apiError";
import { formatDateTimeShort, formatPercent } from "../../lib/format";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "../../lib/queryKeys";
import { useSseChannel } from "../../hooks/useSseChannel";
import { invalidateAfterProfileChange } from "../../lib/mutations";
import { MiniOrb } from "../../components/ui/processing-aura";

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
  return formatPercent(value);
}

/** Motivo do skip legível — o "skip" mudo já custou uma investigação. */
function formatSkipReason(reasons: string[]): string {
  const first = reasons[0] ?? "";
  if (!first) return "";
  if (first === "llm_api_key_not_configured") return i18n.t("ingest:skipReason.llm_api_key_not_configured");
  if (first.startsWith("training_pool_total_below_min")) return i18n.t("ingest:skipReason.training_pool_total_below_min");
  if (first.startsWith("sklearn_unavailable")) return i18n.t("ingest:skipReason.sklearn_unavailable");
  return first.replace(/_/g, " ").slice(0, 48);
}

/** Status do último ciclo (succeeded/failed/running) traduzido; código
 *  desconhecido passa cru. */
function formatCycleStatus(status?: string | null): string {
  if (!status) return "—";
  return i18n.exists(`ingest:cycleStatus.${status}`) ? i18n.t(`ingest:cycleStatus.${status}`) : status;
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
    return i18n.t("ingest:cyclePhase.baseline", { model });
  }
  if (phase.startsWith("benchmark:")) {
    const model = phase.slice("benchmark:".length);
    return i18n.t("ingest:cyclePhase.benchmark", { model });
  }
  const key = `ingest:cyclePhase.${phase}`;
  return i18n.exists(key) ? i18n.t(key) : phase;
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
  onStatus: (msg: string, severity?: StatusSeverity) => void;
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
  const { t } = useTranslation();
  const [llmPolicy, setLlmPolicy] = useState<LLMPolicy>(DEFAULT_LLM_POLICY);
  const [profileVersion, setProfileVersion] = useState<number>(0);
  const [llmSaving, setLlmSaving] = useState(false);
  const queryClient = useQueryClient();
  const modelsQuery = useQuery({ queryKey: qk.models(), queryFn: fetchModels, staleTime: 5 * 60_000 });
  const models = modelsQuery.data ?? [];
  const [fullProfile, setFullProfile] = useState<ProjectProfileV2 | null>(null);
  const [expandedBenchmarkMode, setExpandedBenchmarkMode] = useState<string | null>(null);
  const [confirmDeleteReportId, setConfirmDeleteReportId] = useState<string | null>(null);
  const [deletingReportId, setDeletingReportId] = useState<string | null>(null);
  const [classifierSaving, setClassifierSaving] = useState(false);
  const [confirmCancelCycle, setConfirmCancelCycle] = useState(false);
  const [cancellingCycle, setCancellingCycle] = useState(false);
  // Ciclo do classificador: ponte SSE→Query — snapshot no cache, retoma sozinho
  // ao remontar com ciclo rodando, e o término invalida report/champion/readiness
  const cycleChannel = useSseChannel<ClassifierCycleStatus>({
    queryKey: qk.classifier.cycleStatus(),
    fetchSnapshot: fetchClassifierCycleStatus,
    streamUrl: getClassifierCycleStatusStreamUrl,
    isActive: (s) => !!s.running,
    onFinished: (s) => {
      if (s.last_run_finished_at) void queryClient.invalidateQueries({ queryKey: qk.classifier.scope() });
    },
    pollMs: 500,
  });
  const classifierCycleStatus = cycleChannel.data ?? null;

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

  // Leituras do classificador via cache — decisões/ciclos invalidam qk.classifier
  const readinessQuery = useQuery({
    queryKey: qk.classifier.datasetReadiness(),
    queryFn: () => fetchDatasetReadiness().catch(() => null),
  });
  const classifierStatusQuery = useQuery({
    queryKey: qk.classifier.status(selectedProject),
    queryFn: () => fetchClassifierStatus(selectedProject),
    enabled: isSingleProject,
  });
  const reportsQuery = useQuery({
    queryKey: qk.classifier.reports(),
    queryFn: () => fetchClassifierReports(8),
    enabled: isSingleProject,
  });
  const latestReportQuery = useQuery({
    queryKey: qk.classifier.reportLatest(),
    queryFn: () => fetchClassifierReportLatest().catch(() => null),
    enabled: isSingleProject,
  });
  const datasetReadiness = readinessQuery.data ?? null;
  const classifierStatus = isSingleProject ? classifierStatusQuery.data ?? null : null;
  const classifierReports = isSingleProject ? reportsQuery.data ?? [] : [];
  const classifierReport = isSingleProject ? latestReportQuery.data ?? null : null;

  const loadClassifierState = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: qk.classifier.scope() });
  }, [queryClient]);



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
      invalidateAfterProfileChange(selectedProject);
    } catch {
      onStatus(t("ingest:llm.savePolicyFailed"), "error");
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
      queryClient.setQueryData(qk.classifier.status(selectedProject), status);
      onStatus(nextValue ? t("ingest:classifier.overrideSaved", { mode: nextValue }) : t("ingest:classifier.overrideCleared"));
    } catch {
      onStatus(t("ingest:classifier.overrideSaveFailed"), "error");
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
      await queryClient.invalidateQueries({ queryKey: qk.classifier.reports() });
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
      queryClient.setQueryData(qk.classifier.status(selectedProject), status);
    } catch {
      onStatus(t("ingest:classifier.benchmarkModesSaveFailed"), "error");
    } finally {
      setClassifierSaving(false);
    }
  }

  async function handleStartClassifierCycle() {
    void queryClient.cancelQueries({ queryKey: qk.classifier.cycleStatus() });
    queryClient.setQueryData(qk.classifier.cycleStatus(), buildPendingClassifierCycleStatus(classifierCycleStatus));
    try {
      // Key do navegador viaja no header — o benchmark llm roda no servidor sem key persistida
      const started = await startClassifierCycle({ openaiApiKey: openaiApiKey || undefined });
      void cycleChannel.refresh();
      const moved = started.auto_backfill_moved ?? 0;
      onStatus(
        moved > 0
          ? t("ingest:classifier.cycleStartedBackfill", { count: moved })
          : t("ingest:classifier.cycleStarted")
      );
    } catch {
      void cycleChannel.refresh();
      onStatus(t("ingest:classifier.cycleStartFailed"), "error");
    }
  }

  async function handleCancelCycle() {
    setConfirmCancelCycle(false);
    setCancellingCycle(true);
    try {
      await cancelClassifierCycle();
      onStatus(t("ingest:classifier.cancelSignalSent"));
    } catch {
      setCancellingCycle(false);
      onStatus(t("ingest:classifier.cancelFailed"), "error");
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
          {t("ingest:classifier.title")}
        </CardTitle>
      </CardHeader>
      <CardContent>

      {!isSingleProject && (
        <EmptyState
          icon={<Sparkles aria-hidden />}
          title={t("ingest:classifier.noProjectTitle")}
          description={t("ingest:classifier.noProjectDescription")}
        />
      )}

      {isSingleProject && selectedProjectLabel && (
        <div className="mb-2 border-b border-border pb-2">
          <ProjectHeaderMeta
            icon={<Sparkles className="size-4 text-accent" aria-hidden />}
            projectLabel={selectedProjectLabel}
            projectId={selectedProject}
            version={profileVersion || null}
            updatedBy={fullProfile?.updated_by ?? null}
            extra={
              triageItems.length > 0 ? (
                <span className="text-[0.8rem] font-normal text-accent">
                  · {t("ingest:classifier.pending", { count: triageItems.length })}
                </span>
              ) : undefined
            }
          />
        </div>
      )}

      {isSingleProject && (
        <CollapsibleSection
          className="mt-2"
          title={t("ingest:classifier.operationalTitle")} persistKey="classificador-operacional"
          badge={
            <Badge className="ml-auto">
              {classifierStatus ? formatClassifierModeLabel(classifierStatus.effective_mode) : t("ingest:classifier.loadingBadge")}
            </Badge>
          }
        >
            {classifierStatus && (
              <>
                <div className="mb-2.5 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                  {[
                    { label: t("ingest:classifier.statChampion"), value: formatClassifierModeLabel(classifierStatus.champion_mode) },
                    { label: t("ingest:classifier.statEffective"), value: formatClassifierModeLabel(classifierStatus.effective_mode) },
                    { label: t("ingest:classifier.statOverride"), value: classifierStatus.override_mode ? formatClassifierModeLabel(classifierStatus.override_mode) : t("ingest:classifier.overrideAuto") },
                    { label: t("ingest:classifier.statLastCycle"), value: formatCycleStatus(classifierStatus.latest_cycle_status) },
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
                    aria-label={t("ingest:classifier.overrideAria")}
                    className={cn(nativeSelectClass, "w-auto min-w-52 flex-initial")}
                    value={classifierStatus.override_mode || AUTO_CLASSIFIER_OVERRIDE}
                    onChange={(e) => void handleClassifierOverrideChange(e.target.value)}
                    disabled={classifierSaving || !!classifierCycleStatus?.running}
                  >
                    <option value={AUTO_CLASSIFIER_OVERRIDE}>{t("ingest:classifier.autoOption")}</option>
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
                          ? (datasetReadiness.blockers[0] && apiErrorMessage(datasetReadiness.blockers[0]))
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
                      {cancellingCycle ? t("ingest:classifier.cancelling") : classifierCycleStatus?.running ? t("ingest:classifier.cancelCycle") : (<><RefreshCw /> {t("ingest:classifier.runCycle")}</>)}
                    </Button>
                    {confirmCancelCycle && classifierCycleStatus?.running && (
                      <div className="absolute right-0 top-[calc(100%+6px)] z-20 flex min-w-52 flex-col gap-2 rounded-md border border-border bg-panel p-3 shadow-[0_4px_12px_rgba(0,0,0,0.25)]">
                        <p className="m-0 text-[0.82rem] text-foreground">{t("ingest:classifier.confirmCancelPrompt")}</p>
                        <div className="flex gap-1.5">
                          <Button variant="destructive" size="sm" onClick={() => void handleCancelCycle()}>{t("common:action.confirm")}</Button>
                          <Button variant="secondary" size="sm" onClick={() => setConfirmCancelCycle(false)}>{t("common:action.no")}</Button>
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
                      <p key={b.code} className="m-0 text-[0.8rem] text-foreground">{apiErrorMessage(b)}</p>
                    ))}
                    <p className="m-0 mt-1 font-mono text-[0.68rem] text-tertiary">
                      {t("ingest:classifier.readinessStats", { labeled: datasetReadiness.validation.labeled, records: datasetReadiness.training.records })}
                    </p>
                  </div>
                )}
                {datasetReadiness?.cycle_ready &&
                  datasetReadiness.suggestions
                    .filter((s) => s.code === "sparse_gate_not_met" || s.code === "auto_backfill_on_run")
                    .map((s) => (
                      <p key={s.code} className="mb-2 text-[0.75rem] text-muted-foreground">{apiErrorMessage(s)}</p>
                    ))}

                <p className="mb-2.5 text-[0.78rem] text-muted-foreground">
                  {t("ingest:classifier.promotionLine", {
                    policy: classifierStatus.promotion_policy === "auto_best_with_ui_override" ? t("ingest:classifier.promotionAuto") : classifierStatus.promotion_policy,
                    gate: formatPct(classifierStatus.promotion_gates.min_exact_match_accuracy)
                  })}
                </p>
              </>
            )}

            {classifierCycleStatus && (classifierCycleStatus.running || classifierCycleStatus.phase === "failed" || classifierCycleStatus.phase === "cancelled") && (
              <div className={opProgressClass}>
                <p className={cn(opPhaseClass, classifierCycleStatus.phase === "failed" && "text-destructive", classifierCycleStatus.phase === "cancelled" && "text-accent")}>
                  {classifierCycleStatus.running && <MiniOrb className="mr-1.5 size-2.5" />}
                  {cancellingCycle && classifierCycleStatus.running ? t("ingest:classifier.awaitingCancellation") : formatPhaseLabel(classifierCycleStatus.phase)}
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
                    <strong className="font-display text-sm font-bold text-foreground-strong">{t("ingest:benchmark.title")}</strong>
                  </div>
                  <TableWrap>
                  <DataTable>
                    <thead>
                      <tr>
                        <th className="left">{t("ingest:benchmark.colMode")}</th>
                        <th>{t("ingest:benchmark.colDomain")}</th>
                        <th>{t("ingest:benchmark.colType")}</th>
                        <th>{t("ingest:benchmark.colExactMatch")}</th>
                        <th className="left">{t("ingest:benchmark.colStatus")}</th>
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
                        const skipReasons = (liveIsSkipped ? liveSummary?.skip_reason : reportSummary?.skip_reason) ?? [];
                        const skipLabel = formatSkipReason(skipReasons);
                        const modeResults = reportBenchmarks?.[mode]?.results ?? [];
                        const isModeExpanded = expandedBenchmarkMode === mode && modeResults.length > 0;
                        return (
                          <Fragment key={mode}>
                            <tr
                              className={cn(isSkipped && "opacity-45", isLive && "text-foreground", modeResults.length > 0 && "cursor-pointer")}
                              onClick={modeResults.length > 0 ? () => setExpandedBenchmarkMode((cur) => (cur === mode ? null : mode)) : undefined}
                            >
                              <td className="left">
                                <span className="inline-flex items-center gap-1">
                                  {modeResults.length > 0 &&
                                    (isModeExpanded ? <ChevronDown size={12} aria-hidden /> : <ChevronRight size={12} aria-hidden />)}
                                  {formatClassifierModeLabel(mode)}
                                </span>
                                {isChampion && <Badge variant="success" className="ml-1.5 uppercase">{t("ingest:benchmark.championBadge")}</Badge>}
                                {isSkipped && <span className="ml-1 text-[0.72rem] text-muted-foreground">{t("ingest:benchmark.statusSkip")}</span>}
                              </td>
                              <td>{formatPct(displaySummary.business_domain_accuracy)}</td>
                              <td>{formatPct(displaySummary.document_type_accuracy)}</td>
                              <td>{formatPct(displaySummary.exact_match_accuracy)}</td>
                              <td className="left" title={skipReasons.join("; ") || undefined}>
                                {isSkipped ? (skipLabel ? t("ingest:benchmark.statusSkipWithReason", { reason: skipLabel }) : t("ingest:benchmark.statusSkip")) : t("ingest:benchmark.statusOk")}
                              </td>
                            </tr>
                            {isModeExpanded && (
                              <tr>
                                <td colSpan={5} className="left">
                                  <div className="space-y-1.5 rounded-md bg-panel-strong p-2.5 font-mono text-[0.72rem] text-muted-foreground [&_code]:text-accent-light">
                                    {modeResults.map((r) => (
                                      <div key={r.file}>
                                        <p className="m-0 truncate text-foreground/90" title={r.file}>{r.file}</p>
                                        <p className="m-0">
                                          {t("ingest:benchmark.expected")} <code>{r.expected_business_domain} / {r.expected_document_type}</code>
                                          {"   "}{t("ingest:benchmark.classified")} <code>{r.predicted_business_domain} / {r.predicted_document_type}</code>
                                          {"   "}
                                          <span className={r.business_domain_ok ? "text-success" : "text-destructive"}>
                                            {r.business_domain_ok ? "✓" : "✗"} {t("ingest:benchmark.domainOk")}
                                          </span>{" "}
                                          <span className={r.document_type_ok ? "text-success" : "text-destructive"}>
                                            {r.document_type_ok ? "✓" : "✗"} {t("ingest:benchmark.typeOk")}
                                          </span>
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
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
                  <strong className="font-display text-sm font-bold text-foreground-strong">{t("ingest:classifier.gateWarnings")}</strong>
                  <ul className="m-0 flex list-none flex-col gap-1 p-0 font-mono text-[0.72rem]">
                    {allWarnings.map((w, i) => <li key={i}><code>{w}</code></li>)}
                  </ul>
                </div>
              );
            })()}

            {classifierReports.length > 0 && (
              <div className="mt-2.5">
                <strong className="font-display text-sm font-bold text-foreground-strong">{t("ingest:classifier.recentEvolution")}</strong>
                <TableWrap className="mt-1.5">
                <DataTable>
                  <thead>
                    <tr>
                      <th className="left">{t("ingest:classifier.colCycle")}</th>
                      <th className="left">{t("ingest:classifier.colChampion")}</th>
                      <th>{t("ingest:classifier.colExact")}</th>
                      <th>{t("ingest:classifier.colBdF1")}</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {classifierReports.slice(0, 8).map((report) => {
                      const isChampion = report.report_id === classifierStatus?.champion_report_id;
                      const ts = report.generated_at
                        ? formatDateTimeShort(report.generated_at)
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
                              title={isChampion ? t("ingest:classifier.championCannotDelete") : t("ingest:classifier.deleteReportTitle")}
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
        <ModalShell label={t("ingest:classifier.confirmDeleteLabel")} title={t("ingest:classifier.deleteModalTitle")} size="sm">
            <p className="m-0 text-sm text-foreground">
              <Trans i18nKey="ingest:classifier.confirmDeleteBody" values={{ id: confirmDeleteReportId }} components={[<strong key="0" />]} />
            </p>
            <ModalActions>
              <Button variant="secondary" onClick={() => setConfirmDeleteReportId(null)}>{t("common:action.cancel")}</Button>
              <Button variant="destructive" onClick={handleDeleteReport}>{t("common:action.delete")}</Button>
            </ModalActions>
        </ModalShell>
      )}

      {/* ── Classificação LLM ── */}
      {isSingleProject && (
        <CollapsibleSection
          className="mt-2"
          title={t("ingest:llm.title")} persistKey="classificacao-llm"
          badge={
            <Badge variant={llmPolicy.enabled ? "success" : "destructive"} className="ml-auto">
              {llmPolicy.enabled ? t("ingest:llm.enabledBadge") : t("ingest:llm.disabledBadge")}
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
                {t("ingest:llm.toggleLabel")}
              </label>
              {llmSaving && <span className="text-[0.78rem] italic text-muted-foreground">{t("ingest:llm.saving")}</span>}
            </div>

            {llmPolicy.enabled && (
              <>
                <div className="mt-2 grid gap-2.5 lg:grid-cols-2">
                  <div className="flex flex-col">
                    <label htmlFor="itc-llm-mode" className={fieldLabelClass}>{t("ingest:llm.modeLabel")}</label>
                    <select
                      id="itc-llm-mode"
                      className={nativeSelectClass}
                      value={llmPolicy.mode}
                      onChange={(e) => handleModeChange(e.target.value as LLMPolicy["mode"])}
                      disabled={llmSaving}
                    >
                      <option value="tag_only">{t("ingest:llm.modeTagOnly")}</option>
                      <option value="review">{t("ingest:llm.modeReview")}</option>
                      <option value="full_override">{t("ingest:llm.modeFullOverride")}</option>
                    </select>
                  </div>
                  <div className="flex flex-col">
                    <label htmlFor="itc-llm-model" className={fieldLabelClass}>{t("ingest:llm.modelLabel")}</label>
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
                        title={t("ingest:llm.configureModelsTitle")}
                      >
                        <Settings size={16} />
                      </button>
                    </div>
                  </div>
                </div>

                {!hasKey && (
                  <div className="mt-2 flex items-center gap-2 rounded-md border border-[rgba(255,200,50,0.25)] bg-[rgba(255,200,50,0.1)] px-2.5 py-1.5 text-[0.82rem] text-foreground">
                    <span>{t("ingest:llm.noKeyWarning", { provider: llmPolicy.provider })}</span>
                    <Button variant="outline" size="sm" onClick={onOpenSettings}>
                      {t("ingest:llm.configure")}
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
