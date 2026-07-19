import { differenceInCalendarDays, format, parseISO, startOfISOWeek, startOfMonth } from "date-fns";
import { ptBR } from "date-fns/locale";
import { BarChart3, ChevronLeft, ChevronRight, CircleDollarSign, Coins, GraduationCap, MessagesSquare, RefreshCw, Tags, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import i18n from "../../i18n";
import { fetchClassificationUsage, fetchTrainingUsage, fetchUsageSessions, fetchUsageSummary } from "../../api";
import { qk } from "../../lib/queryKeys";
import { Button } from "../../components/ui/button";
import { DataTable, TableWrap } from "../../components/ui/data-table";
import { DateRangePicker } from "../../components/ui/date-range-picker";
import { EmptyState, ErrorState } from "../../components/ui/empty-state";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { StatTile } from "../../components/ui/stat-tile";
import { Tabs, TabsList, TabsTrigger } from "../../components/ui/tabs";
import type { ClassificationUsageSummary, TrainingUsageSummary, UsageByDayEntry, UsageByModelEntry, UsageSessionItem, UsageSummaryResponse } from "../../types";

const chartCardClass = "flex flex-col rounded-lg border border-border bg-card p-4";
const sectionTitleClass = "mt-5 mb-2 font-display text-sm font-bold text-foreground-strong";
const legendDotClass = "inline-block size-2 rounded-full";
const ALL_CHANNELS = "__all__";
const PAGE_SIZE = 10;

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}m`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(n));
}

export function formatUsd(n: number): string {
  if (n === 0) return "—";
  const rounded = Math.round(n * 100) / 100;
  return `$${rounded.toFixed(2)}`;
}

export function formatUsd4(n: number): string {
  if (n === 0) return "—";
  const rounded = Math.round(n * 10000) / 10000;
  return `$${rounded.toFixed(4)}`;
}

function toYyyyMmDd(d: Date): string {
  return d.toISOString().slice(0, 10);
}

type Granularity = "day" | "week" | "month";

const GRANULARITIES: Granularity[] = ["day", "week", "month"];

/** Granularidade default calculada pelo tamanho do range: até 31 dias → dia;
 * até 26 semanas → semana; acima → mês (mantém ≤ ~31 barras legíveis). */
export function autoGranularity(start: string, end: string): Granularity {
  const span = differenceInCalendarDays(parseISO(end), parseISO(start)) + 1;
  if (span <= 31) return "day";
  if (span <= 182) return "week";
  return "month";
}

function bucketKey(date: string, g: Granularity): string {
  if (g === "day") return date;
  const d = parseISO(date);
  return format(g === "week" ? startOfISOWeek(d) : startOfMonth(d), "yyyy-MM-dd");
}

function bucketLabel(key: string, g: Granularity): string {
  const d = parseISO(key);
  if (g === "month") return format(d, "MMM/yy", { locale: ptBR }).replace(".", "");
  if (g === "week") return format(d, "dd/MM");
  return format(d, "dd MMM", { locale: ptBR }).replace(".", "");
}

function bucketTooltip(key: string, g: Granularity): string {
  const d = parseISO(key);
  if (g === "month") return format(d, "MMMM 'de' yyyy", { locale: ptBR });
  if (g === "week") return i18n.t("usage:chart.weekOf", { date: format(d, "dd/MM/yyyy") });
  return format(d, "dd/MM/yyyy");
}

// Paleta de gráficos da marca (--chart-N em styles.css, dark + light)
const TOKEN_COLORS = {
  output: "var(--chart-1)",
  input: "var(--chart-3)",
  cache_write: "var(--chart-4)",
  cache_read: "var(--chart-5)",
} as const;

type TokenType = keyof typeof TOKEN_COLORS;

const PROCESS_COLORS = {
  assistant: "var(--chart-3)",
  classification: "var(--chart-2)",
  training: "var(--chart-5)",
} as const;

type ProcessType = keyof typeof PROCESS_COLORS;

interface MergedDay {
  date: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_tokens: number;
  assistant_tokens: number;
  classification_tokens: number;
  training_tokens: number;
}

function mergeDays(
  assistantDays: UsageByDayEntry[],
  classificationDays: UsageByDayEntry[],
  trainingDays: UsageByDayEntry[],
): MergedDay[] {
  const map = new Map<string, MergedDay>();
  const ensure = (date: string) => {
    if (!map.has(date)) {
      map.set(date, { date, input_tokens: 0, output_tokens: 0, cache_read_tokens: 0, cache_write_tokens: 0, total_tokens: 0, assistant_tokens: 0, classification_tokens: 0, training_tokens: 0 });
    }
    return map.get(date)!;
  };
  for (const d of assistantDays) {
    const m = ensure(d.date);
    m.input_tokens += d.input_tokens;
    m.output_tokens += d.output_tokens;
    m.cache_read_tokens += d.cache_read_tokens;
    m.cache_write_tokens += d.cache_write_tokens;
    m.total_tokens += d.total_tokens;
    m.assistant_tokens += d.total_tokens;
  }
  for (const d of classificationDays) {
    const m = ensure(d.date);
    m.input_tokens += d.input_tokens;
    m.output_tokens += d.output_tokens;
    m.cache_read_tokens += d.cache_read_tokens;
    m.cache_write_tokens += d.cache_write_tokens;
    m.total_tokens += d.total_tokens;
    m.classification_tokens += d.total_tokens;
  }
  for (const d of trainingDays) {
    const m = ensure(d.date);
    m.input_tokens += d.input_tokens;
    m.output_tokens += d.output_tokens;
    m.cache_read_tokens += d.cache_read_tokens;
    m.cache_write_tokens += d.cache_write_tokens;
    m.total_tokens += d.total_tokens;
    m.training_tokens += d.total_tokens;
  }
  return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function aggregateByBucket(days: MergedDay[], g: Granularity): MergedDay[] {
  if (g === "day") return days;
  const map = new Map<string, MergedDay>();
  for (const d of days) {
    const key = bucketKey(d.date, g);
    let m = map.get(key);
    if (!m) {
      m = { date: key, input_tokens: 0, output_tokens: 0, cache_read_tokens: 0, cache_write_tokens: 0, total_tokens: 0, assistant_tokens: 0, classification_tokens: 0, training_tokens: 0 };
      map.set(key, m);
    }
    m.input_tokens += d.input_tokens;
    m.output_tokens += d.output_tokens;
    m.cache_read_tokens += d.cache_read_tokens;
    m.cache_write_tokens += d.cache_write_tokens;
    m.total_tokens += d.total_tokens;
    m.assistant_tokens += d.assistant_tokens;
    m.classification_tokens += d.classification_tokens;
    m.training_tokens += d.training_tokens;
  }
  return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
}

type ChartMode = "by-type" | "by-process";

function DailyTokenChart({
  assistantDays,
  classificationDays,
  trainingDays,
  chartMode,
  onChartModeChange,
  granularity,
  onGranularityChange,
}: {
  assistantDays: UsageByDayEntry[];
  classificationDays: UsageByDayEntry[];
  trainingDays: UsageByDayEntry[];
  chartMode: ChartMode;
  onChartModeChange: (mode: ChartMode) => void;
  granularity: Granularity;
  onGranularityChange: (g: Granularity) => void;
}) {
  const { t } = useTranslation();
  const days = useMemo(() => mergeDays(assistantDays, classificationDays, trainingDays), [assistantDays, classificationDays, trainingDays]);
  const buckets = useMemo(() => aggregateByBucket(days, granularity), [days, granularity]);
  const maxTokens = useMemo(() => Math.max(...buckets.map((d) => d.total_tokens), 1), [buckets]);
  const showValueLabels = buckets.length <= 14;
  const labelEvery = Math.max(1, Math.ceil(buckets.length / 16));

  const granularityTabs = (
    <Tabs value={granularity} onValueChange={(v) => onGranularityChange(v as Granularity)}>
      <TabsList aria-label={t("usage:chart.granularityAria")}>
        {GRANULARITIES.map((g) => (
          <TabsTrigger key={g} value={g} className="px-2.5 py-1 text-xs">{t(`usage:granularity.${g}`)}</TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );

  if (buckets.length === 0) {
    return (
      <div className={chartCardClass}>
        <span className="font-display text-sm font-bold text-foreground-strong">{t("usage:chart.title")}</span>
        <EmptyState className="mt-3 border-0 py-8" icon={<BarChart3 aria-hidden />} title={t("usage:chart.emptyTitle")} description={t("usage:chart.emptyDescription")} />
      </div>
    );
  }

  return (
    <div className={chartCardClass}>
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="font-display text-sm font-bold text-foreground-strong">{t("usage:chart.title")}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Tabs value={chartMode} onValueChange={(v) => onChartModeChange(v as ChartMode)}>
            <TabsList aria-label={t("usage:chart.modeAria")}>
              <TabsTrigger value="by-type" className="px-2.5 py-1 text-xs">{t("usage:chart.byType")}</TabsTrigger>
              <TabsTrigger value="by-process" className="px-2.5 py-1 text-xs">{t("usage:chart.byProcess")}</TabsTrigger>
            </TabsList>
          </Tabs>
          {granularityTabs}
        </div>
      </div>
      <div className="flex h-44 items-end gap-1.5">
        {buckets.map((d, idx) => {
          const heightPct = (d.total_tokens / maxTokens) * 100;
          const segments: { key: string; value: number; color: string }[] =
            chartMode === "by-type"
              ? (["output", "input", "cache_write", "cache_read"] as TokenType[]).map((t) => ({
                  key: t,
                  value: { output: d.output_tokens, input: d.input_tokens, cache_write: d.cache_write_tokens, cache_read: d.cache_read_tokens }[t],
                  color: TOKEN_COLORS[t],
                }))
              : (["assistant", "classification", "training"] as ProcessType[]).map((t) => ({
                  key: t,
                  value: { assistant: d.assistant_tokens, classification: d.classification_tokens, training: d.training_tokens }[t],
                  color: PROCESS_COLORS[t],
                }));
          const segTotal = segments.reduce((s, seg) => s + seg.value, 0) || 1;
          return (
            <div
              key={d.date}
              className="group flex min-w-0 flex-1 flex-col items-center justify-end gap-1 self-stretch"
              title={t("usage:chart.barTitle", { date: bucketTooltip(d.date, granularity), tokens: formatTokens(d.total_tokens) })}
            >
              {showValueLabels && <div className="font-mono text-[0.6rem] text-tertiary">{formatTokens(d.total_tokens)}</div>}
              <div className="flex w-full max-w-8 origin-bottom animate-[atlas-grow-up_500ms_var(--ease-out)] flex-col justify-end overflow-hidden rounded-t-sm transition-[filter] group-hover:brightness-125 motion-reduce:animate-none" style={{ height: `${heightPct.toFixed(1)}%` }}>
                {segments.map((seg) =>
                  seg.value > 0 ? (
                    <div key={seg.key} className="w-full" style={{ height: `${(seg.value / segTotal) * 100}%`, background: seg.color }} />
                  ) : null
                )}
              </div>
              <div className="h-3.5 font-mono text-[0.6rem] text-tertiary">
                {idx % labelEvery === 0 ? bucketLabel(d.date, granularity) : ""}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TokensByTypeBar({
  chartMode,
  totalInput, totalOutput, totalCacheRead, totalCacheWrite,
  totalAssistant, totalClassification, totalTraining,
}: {
  chartMode: ChartMode;
  totalInput: number; totalOutput: number; totalCacheRead: number; totalCacheWrite: number;
  totalAssistant: number; totalClassification: number; totalTraining: number;
}) {
  const { t } = useTranslation();
  if (chartMode === "by-process") {
    const items: { type: ProcessType; value: number }[] = [
      { type: "assistant", value: totalAssistant },
      { type: "classification", value: totalClassification },
      { type: "training", value: totalTraining },
    ];
    const total = items.reduce((s, i) => s + i.value, 0) || 1;
    return (
      <div className={chartCardClass}>
        <span className="mb-2.5 font-display text-sm font-bold text-foreground-strong">{t("usage:tokensBar.byProcessTitle")}</span>
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-panel-strong">
          {items.map((item) =>
            item.value > 0 ? (
              <div
                key={item.type}
                className="h-full"
                style={{ width: `${(item.value / total) * 100}%`, background: PROCESS_COLORS[item.type] }}
                title={t("usage:tokensBar.segmentTitle", { label: t(`usage:process.${item.type}`), value: formatTokens(item.value) })}
              />
            ) : null
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {items.map((item) => (
            <span key={item.type} className="flex items-center gap-1.5 font-mono text-[0.7rem] text-muted-foreground">
              <span className={legendDotClass} style={{ background: PROCESS_COLORS[item.type] }} />
              {t(`usage:process.${item.type}`)} {formatTokens(item.value)}
            </span>
          ))}
        </div>
        <div className="mt-2 font-mono text-[0.7rem] text-tertiary">{t("usage:tokensBar.total", { value: formatTokens(total) })}</div>
      </div>
    );
  }

  const items: { type: TokenType; value: number }[] = [
    { type: "output", value: totalOutput },
    { type: "input", value: totalInput },
    { type: "cache_write", value: totalCacheWrite },
    { type: "cache_read", value: totalCacheRead },
  ];
  const total = items.reduce((s, i) => s + i.value, 0) || 1;

  return (
    <div className={chartCardClass}>
      <span className="mb-2.5 font-display text-sm font-bold text-foreground-strong">{t("usage:tokensBar.byTypeTitle")}</span>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-panel-strong">
        {items.map((item) =>
          item.value > 0 ? (
            <div
              key={item.type}
              className="h-full"
              style={{ width: `${(item.value / total) * 100}%`, background: TOKEN_COLORS[item.type] }}
              title={t("usage:tokensBar.segmentTitle", { label: t(`usage:tokenType.${item.type}`), value: formatTokens(item.value) })}
            />
          ) : null
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {items.map((item) => (
          <span key={item.type} className="flex items-center gap-1.5 font-mono text-[0.7rem] text-muted-foreground">
            <span className={legendDotClass} style={{ background: TOKEN_COLORS[item.type] }} />
            {t(`usage:tokenType.${item.type}`)} {formatTokens(item.value)}
          </span>
        ))}
      </div>
      <div className="mt-2 font-mono text-[0.7rem] text-tertiary">{t("usage:tokensBar.total", { value: formatTokens(total) })}</div>
    </div>
  );
}

export function UsageView({ projectId }: { projectId?: string | null }) {
  const { t } = useTranslation();
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 6);
    return toYyyyMmDd(d);
  });
  const [endDate, setEndDate] = useState(() => toYyyyMmDd(new Date()));
  const [channel, setChannel] = useState<string>(ALL_CHANNELS);
  const [chartMode, setChartMode] = useState<ChartMode>("by-type");
  const [granularityOverride, setGranularityOverride] = useState<Granularity | null>(null);
  const granularity = granularityOverride ?? autoGranularity(startDate, endDate);
  const [sessionsPage, setSessionsPage] = useState(0);

  // Uma query para o bundle da tela (mesmo Promise.all de antes) — o cache por
  // chave [período, projeto, canal] torna a troca de filtros instantânea na volta
  const usageQuery = useQuery({
    queryKey: qk.usage.summary(projectId || undefined, { startDate, endDate, channel }),
    queryFn: async () => {
      const baseParams = {
        start_date: startDate,
        end_date: endDate,
        project_id: projectId || null,
      };
      const channelParam = channel === ALL_CHANNELS ? null : channel;
      const [s, list, classif, training] = await Promise.all([
        fetchUsageSummary({ ...baseParams, channel: channelParam }),
        fetchUsageSessions({ ...baseParams, channel: channelParam, limit: 100 }),
        fetchClassificationUsage(baseParams),
        fetchTrainingUsage(baseParams).catch(() => null),
      ]);
      return { summary: s, sessions: list, classifUsage: classif, trainingUsage: training };
    },
  });
  const loading = usageQuery.isPending;
  const error = usageQuery.error ? (usageQuery.error instanceof Error ? usageQuery.error.message : t("usage:loadError")) : null;
  const summary = usageQuery.data?.summary ?? null;
  const sessions = usageQuery.data?.sessions ?? [];
  const classifUsage = usageQuery.data?.classifUsage ?? null;
  const trainingUsage = usageQuery.data?.trainingUsage ?? null;

  useEffect(() => {
    setSessionsPage(0);
  }, [startDate, endDate, projectId, channel]);

  return (
    <section className="flex flex-col">
      <div className="flex flex-wrap items-center gap-2">
        <label className="font-mono text-[0.7rem] uppercase tracking-wide text-tertiary">{t("usage:filters.period")}</label>
        <DateRangePicker
          start={startDate}
          end={endDate}
          onChange={(s, e) => {
            setStartDate(s);
            setEndDate(e);
            setGranularityOverride(null);
          }}
        />
        <label className="ml-2 font-mono text-[0.7rem] uppercase tracking-wide text-tertiary">{t("usage:filters.channel")}</label>
        <Select value={channel} onValueChange={setChannel}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_CHANNELS}>{t("usage:filters.allChannels")}</SelectItem>
            <SelectItem value="web">{t("usage:filters.channelWeb")}</SelectItem>
            <SelectItem value="telegram">{t("usage:filters.channelTelegram")}</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="secondary" onClick={() => void usageQuery.refetch()} disabled={loading}>
          <RefreshCw className={loading ? "animate-spin" : ""} />
          {t("common:action.update")}
        </Button>
      </div>

      {error && <ErrorState className="mt-4" description={error} onRetry={() => void usageQuery.refetch()} />}

      {summary && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <StatTile
              dense
              icon={<Coins aria-hidden />}
              value={
                summary.total_tokens
                + (classifUsage ? classifUsage.total_input_tokens + classifUsage.total_output_tokens : 0)
                + (trainingUsage ? trainingUsage.total_input_tokens + trainingUsage.total_output_tokens : 0)
              }
              format={formatTokens}
              label={t("usage:stats.totalTokens")}
            />
            <StatTile
              dense
              icon={<CircleDollarSign aria-hidden />}
              value={summary.estimated_cost_usd + (classifUsage?.estimated_cost_usd ?? 0) + (trainingUsage?.estimated_cost_usd ?? 0)}
              format={(n) => (n === 0 ? "—" : `$${n.toFixed(2)}`)}
              label={t("usage:stats.estimatedCost")}
            />
            <StatTile
              dense
              icon={<Zap aria-hidden />}
              value={(summary.total_api_calls ?? 0) + (classifUsage?.total_calls ?? 0) + (trainingUsage?.total_api_calls ?? 0)}
              label={t("usage:stats.apiCalls")}
            />
            <StatTile dense icon={<MessagesSquare aria-hidden />} value={summary.session_count} label={t("usage:stats.sessions")} />
            {classifUsage && classifUsage.total_calls > 0 && (
              <StatTile dense icon={<Tags aria-hidden />} value={classifUsage.total_calls} label={t("usage:stats.classifications")} />
            )}
            {trainingUsage && trainingUsage.total_calls > 0 && (
              <StatTile dense icon={<GraduationCap aria-hidden />} value={trainingUsage.total_calls} label={t("usage:stats.training")} />
            )}
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-[1.6fr_1fr]">
            <DailyTokenChart
              assistantDays={summary.by_day}
              classificationDays={classifUsage?.by_day ?? []}
              trainingDays={trainingUsage?.by_day ?? []}
              chartMode={chartMode}
              onChartModeChange={setChartMode}
              granularity={granularity}
              onGranularityChange={setGranularityOverride}
            />
            <TokensByTypeBar
              chartMode={chartMode}
              totalInput={summary.total_input_tokens + (classifUsage?.total_input_tokens ?? 0) + (trainingUsage?.total_input_tokens ?? 0)}
              totalOutput={summary.total_output_tokens + (classifUsage?.total_output_tokens ?? 0) + (trainingUsage?.total_output_tokens ?? 0)}
              totalCacheRead={summary.total_cache_read_tokens}
              totalCacheWrite={summary.total_cache_write_tokens}
              totalAssistant={summary.total_tokens}
              totalClassification={(classifUsage?.total_input_tokens ?? 0) + (classifUsage?.total_output_tokens ?? 0)}
              totalTraining={(trainingUsage?.total_input_tokens ?? 0) + (trainingUsage?.total_output_tokens ?? 0)}
            />
          </div>

          <h3 className={sectionTitleClass}>{t("usage:modelTable.title")}</h3>
          <TableWrap>
            <DataTable>
              <thead>
                <tr>
                  <th className="left">{t("usage:modelTable.model")}</th>
                  <th>{t("usage:modelTable.inputTokens")}</th>
                  <th>{t("usage:modelTable.outputTokens")}</th>
                  <th>{t("usage:modelTable.inputCost")}</th>
                  <th>{t("usage:modelTable.outputCost")}</th>
                  <th>{t("usage:modelTable.totalTokens")}</th>
                  <th>{t("usage:modelTable.totalCost")}</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_model.length === 0 ? (
                  <tr><td colSpan={7} className="empty">{t("usage:modelTable.empty")}</td></tr>
                ) : (
                  summary.by_model.map((row: UsageByModelEntry) => (
                    <tr key={row.model}>
                      <td className="left">
                        {row.model}
                        {row.cost_tracked === false && (
                          <span
                            className="ml-1.5 rounded-full border border-border bg-panel-strong px-1.5 py-0.5 font-mono text-[0.62rem] text-tertiary"
                            title={t("usage:modelTable.costNotTrackedTitle")}
                          >
                            {t("usage:modelTable.costNotTracked")}
                          </span>
                        )}
                      </td>
                      <td>{formatTokens(row.input_tokens)}</td>
                      <td>{formatTokens(row.output_tokens)}</td>
                      <td>{formatUsd4(row.input_cost_usd)}</td>
                      <td>{formatUsd4(row.output_cost_usd)}</td>
                      <td>{formatTokens(row.total_tokens)}</td>
                      <td>{row.cost_tracked === false ? "—" : formatUsd(row.estimated_cost_usd)}</td>
                    </tr>
                  ))
                )}
              </tbody>
              {summary.by_model.length > 0 && (
                <tfoot>
                  <tr className="">
                    <td className="left">{t("usage:modelTable.total")}</td>
                    <td>{formatTokens(summary.total_input_tokens)}</td>
                    <td>{formatTokens(summary.total_output_tokens)}</td>
                    <td>{formatUsd4(summary.by_model.reduce((s, r) => s + r.input_cost_usd, 0))}</td>
                    <td>{formatUsd4(summary.by_model.reduce((s, r) => s + r.output_cost_usd, 0))}</td>
                    <td>{formatTokens(summary.total_tokens)}</td>
                    <td>{formatUsd(summary.estimated_cost_usd)}</td>
                  </tr>
                </tfoot>
              )}
            </DataTable>
          </TableWrap>

          {classifUsage && classifUsage.total_calls > 0 && (
            <>
              <h3 className={sectionTitleClass}>{t("usage:classifTable.title")}</h3>
              <TableWrap>
                <DataTable>
                  <thead>
                    <tr>
                      <th className="left">{t("usage:modelTable.model")}</th>
                      <th>{t("usage:classifTable.apiCalls")}</th>
                      <th>{t("usage:modelTable.inputTokens")}</th>
                      <th>{t("usage:modelTable.outputTokens")}</th>
                      <th>{t("usage:classifTable.cost")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classifUsage.by_model.map((row) => (
                      <tr key={row.model}>
                        <td className="left">{row.model}</td>
                        <td>{row.call_count}</td>
                        <td>{formatTokens(row.input_tokens)}</td>
                        <td>{formatTokens(row.output_tokens)}</td>
                        <td>{formatUsd(row.estimated_cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                  {classifUsage.by_model.length > 0 && (
                    <tfoot>
                      <tr className="">
                        <td className="left">{t("usage:modelTable.total")}</td>
                        <td>{classifUsage.total_calls}</td>
                        <td>{formatTokens(classifUsage.total_input_tokens)}</td>
                        <td>{formatTokens(classifUsage.total_output_tokens)}</td>
                        <td>{formatUsd(classifUsage.estimated_cost_usd)}</td>
                      </tr>
                    </tfoot>
                  )}
                </DataTable>
              </TableWrap>
            </>
          )}

          {trainingUsage && trainingUsage.total_calls > 0 && (
            <>
              <h3 className={sectionTitleClass}>{t("usage:trainingTable.title")}</h3>
              <TableWrap>
                <DataTable>
                  <thead>
                    <tr>
                      <th className="left">{t("usage:trainingTable.script")}</th>
                      <th>{t("usage:classifTable.apiCalls")}</th>
                      <th>{t("usage:modelTable.inputTokens")}</th>
                      <th>{t("usage:modelTable.outputTokens")}</th>
                      <th>{t("usage:classifTable.cost")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trainingUsage.by_script.map((row) => (
                      <tr key={row.script_name}>
                        <td className="left">{row.script_name}</td>
                        <td>{row.api_call_count}</td>
                        <td>{formatTokens(row.input_tokens)}</td>
                        <td>{formatTokens(row.output_tokens)}</td>
                        <td>{formatUsd(row.estimated_cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                  {trainingUsage.by_script.length > 0 && (
                    <tfoot>
                      <tr className="">
                        <td className="left">{t("usage:modelTable.total")}</td>
                        <td>{trainingUsage.total_api_calls}</td>
                        <td>{formatTokens(trainingUsage.total_input_tokens)}</td>
                        <td>{formatTokens(trainingUsage.total_output_tokens)}</td>
                        <td>{formatUsd(trainingUsage.estimated_cost_usd)}</td>
                      </tr>
                    </tfoot>
                  )}
                </DataTable>
              </TableWrap>
            </>
          )}

          <h3 className={sectionTitleClass}>{t("usage:sessionsTable.title")}</h3>
          <TableWrap>
            <DataTable>
              <thead>
                <tr>
                  <th className="left">{t("usage:sessionsTable.titleCol")}</th>
                  <th className="left">{t("usage:sessionsTable.date")}</th>
                  <th className="left">{t("usage:sessionsTable.project")}</th>
                  <th className="left">{t("usage:sessionsTable.channel")}</th>
                  <th className="left">{t("usage:sessionsTable.model")}</th>
                  <th>{t("usage:sessionsTable.tokens")}</th>
                  <th>{t("usage:sessionsTable.cost")}</th>
                </tr>
              </thead>
              <tbody>
                {sessions.length === 0 ? (
                  <tr><td colSpan={7} className="empty">{t("usage:sessionsTable.empty")}</td></tr>
                ) : (
                  sessions.slice(sessionsPage * PAGE_SIZE, (sessionsPage + 1) * PAGE_SIZE).map((s: UsageSessionItem) => {
                    const tot = s.usage_totals;
                    const tokens = tot ? tot.total_tokens : 0;
                    const cost = tot ? tot.estimated_cost_usd : 0;
                    const dateStr = s.updatedAt
                      ? new Date(s.updatedAt).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
                      : "—";
                    const modelKeys = s.usage_by_model ? Object.keys(s.usage_by_model) : [];
                    const stripProvider = (m: string) => m.replace(/^[^/]+\//, "");
                    const modelLabel = modelKeys.length > 1
                      ? modelKeys.map(stripProvider).join(", ")
                      : stripProvider(s.model);
                    const channelLabel = s.channel ? t(`usage:channel.${s.channel}`, { defaultValue: s.channel }) : "—";
                    return (
                      <tr key={s.id}>
                        <td className="left max-w-64 truncate" title={s.title || t("usage:sessionsTable.untitled")}>{s.title || t("usage:sessionsTable.untitled")}</td>
                        <td className="left">{dateStr}</td>
                        <td className="left">{s.project_id ?? "—"}</td>
                        <td className="left">{channelLabel}</td>
                        <td className="left">{modelLabel}</td>
                        <td>{formatTokens(tokens)}</td>
                        <td>{formatUsd(cost)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </DataTable>
            {sessions.length > PAGE_SIZE && (
              <div className="flex items-center justify-between border-t border-border px-3 py-2">
                <Button variant="ghost" size="sm" disabled={sessionsPage === 0} onClick={() => setSessionsPage((p) => p - 1)}>
                  <ChevronLeft /> {t("usage:sessionsTable.previous")}
                </Button>
                <span className="font-mono text-[0.7rem] text-tertiary">
                  {t("usage:sessionsTable.pageInfo", { from: sessionsPage * PAGE_SIZE + 1, to: Math.min((sessionsPage + 1) * PAGE_SIZE, sessions.length), total: sessions.length })}
                </span>
                <Button variant="ghost" size="sm" disabled={(sessionsPage + 1) * PAGE_SIZE >= sessions.length} onClick={() => setSessionsPage((p) => p + 1)}>
                  {t("usage:sessionsTable.next")} <ChevronRight />
                </Button>
              </div>
            )}
          </TableWrap>
        </>
      )}
    </section>
  );
}
