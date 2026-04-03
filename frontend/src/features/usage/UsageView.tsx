import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchClassificationUsage, fetchTrainingUsage, fetchUsageSessions, fetchUsageSummary } from "../../api";
import type { ClassificationUsageSummary, TrainingUsageSummary, UsageByDayEntry, UsageByModelEntry, UsageSessionItem, UsageSummaryResponse } from "../../types";
const ALL_CHANNELS = "__all__";
const CHANNEL_LABELS: Record<string, string> = { web: "Web", telegram: "TG" };
const PAGE_SIZE = 10;

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}m`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(n));
}

function formatUsd(n: number): string {
  if (n === 0) return "—";
  const truncated = Math.floor(n * 100) / 100;
  return `$${truncated.toFixed(2)}`;
}

function formatUsd4(n: number): string {
  if (n === 0) return "—";
  const truncated = Math.floor(n * 10000) / 10000;
  return `$${truncated.toFixed(4)}`;
}

function toYyyyMmDd(d: Date): string {
  return d.toISOString().slice(0, 10);
}



function formatDayLabel(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }).replace(".", "");
}

const TOKEN_COLORS = {
  output: "var(--chart-output, #e74c3c)",
  input: "var(--chart-input, #f39c12)",
  cache_write: "var(--chart-cache-write, #2ecc71)",
  cache_read: "var(--chart-cache-read, #00bcd4)",
} as const;

type TokenType = keyof typeof TOKEN_COLORS;

const TOKEN_LABELS: Record<TokenType, string> = {
  output: "Output",
  input: "Input",
  cache_write: "Cache Write",
  cache_read: "Cache Read",
};

function DailyTokenChart({ days }: { days: UsageByDayEntry[] }) {
  const [chartMode, setChartMode] = useState<"total" | "by-type">("by-type");
  const maxTokens = useMemo(() => Math.max(...days.map((d) => d.total_tokens), 1), [days]);
  const showLabels = days.length <= 14;

  if (days.length === 0) {
    return (
      <div className="usage-chart-card">
        <div className="usage-chart-header">
          <span className="usage-section-title" style={{ margin: 0 }}>Uso diário de tokens</span>
        </div>
        <div style={{ padding: "20px", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>Nenhum dado no período.</div>
      </div>
    );
  }

  return (
    <div className="usage-chart-card">
      <div className="usage-chart-header">
        <div className="assistente-tabs-pill" style={{ marginRight: 8 }}>
          <button
            type="button"
            className={`assistente-tab${chartMode === "total" ? " assistente-tab--active" : ""}`}
            onClick={() => setChartMode("total")}
          >Total</button>
          <button
            type="button"
            className={`assistente-tab${chartMode === "by-type" ? " assistente-tab--active" : ""}`}
            onClick={() => setChartMode("by-type")}
          >Por tipo</button>
        </div>
        <span className="usage-section-title" style={{ margin: 0 }}>Uso diário de tokens</span>
      </div>
      <div className="usage-daily-bars">
        {days.map((d) => {
          const heightPct = (d.total_tokens / maxTokens) * 100;
          const segments: { type: TokenType; value: number }[] = [
            { type: "output", value: d.output_tokens },
            { type: "input", value: d.input_tokens },
            { type: "cache_write", value: d.cache_write_tokens },
            { type: "cache_read", value: d.cache_read_tokens },
          ];
          const segTotal = segments.reduce((s, seg) => s + seg.value, 0) || 1;
          return (
            <div key={d.date} className="usage-daily-col" title={`${d.date}\n${formatTokens(d.total_tokens)} tokens`}>
              {showLabels && <div className="usage-daily-total">{formatTokens(d.total_tokens)}</div>}
              <div className="usage-daily-bar" style={{ height: `${heightPct.toFixed(1)}%` }}>
                {chartMode === "by-type"
                  ? segments.map((seg) =>
                      seg.value > 0 ? (
                        <div
                          key={seg.type}
                          className="usage-bar-segment"
                          style={{ height: `${(seg.value / segTotal) * 100}%`, background: TOKEN_COLORS[seg.type] }}
                        />
                      ) : null
                    )
                  : null}
              </div>
              <div className="usage-daily-label">{formatDayLabel(d.date)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TokensByTypeBar({ summary }: { summary: UsageSummaryResponse }) {
  const items: { type: TokenType; value: number }[] = [
    { type: "output", value: summary.total_output_tokens },
    { type: "input", value: summary.total_input_tokens },
    { type: "cache_write", value: summary.total_cache_write_tokens },
    { type: "cache_read", value: summary.total_cache_read_tokens },
  ];
  const total = items.reduce((s, i) => s + i.value, 0) || 1;

  return (
    <div className="usage-chart-card">
      <span className="usage-section-title" style={{ margin: "0 0 10px" }}>Tokens por tipo</span>
      <div className="usage-type-bar">
        {items.map((item) =>
          item.value > 0 ? (
            <div
              key={item.type}
              className="usage-type-segment"
              style={{ width: `${(item.value / total) * 100}%`, background: TOKEN_COLORS[item.type] }}
              title={`${TOKEN_LABELS[item.type]}: ${formatTokens(item.value)}`}
            />
          ) : null
        )}
      </div>
      <div className="usage-type-legend">
        {items.map((item) => (
          <span key={item.type} className="usage-type-legend-item">
            <span className="usage-type-dot" style={{ background: TOKEN_COLORS[item.type] }} />
            {TOKEN_LABELS[item.type]} {formatTokens(item.value)}
          </span>
        ))}
      </div>
      <div className="usage-type-total">Total: {formatTokens(total)}</div>
    </div>
  );
}

export function UsageView({ projectId }: { projectId?: string | null }) {
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 6);
    return toYyyyMmDd(d);
  });
  const [endDate, setEndDate] = useState(() => toYyyyMmDd(new Date()));
  const [channel, setChannel] = useState<string>(ALL_CHANNELS);
  const [summary, setSummary] = useState<UsageSummaryResponse | null>(null);
  const [sessions, setSessions] = useState<UsageSessionItem[]>([]);
  const [classifUsage, setClassifUsage] = useState<ClassificationUsageSummary | null>(null);
  const [trainingUsage, setTrainingUsage] = useState<TrainingUsageSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionsPage, setSessionsPage] = useState(0);

  const load = useCallback(() => {
    setError(null);
    setLoading(true);
    const baseParams = {
      start_date: startDate,
      end_date: endDate,
      project_id: projectId || null,
    };
    const channelParam = channel === ALL_CHANNELS ? null : channel;
    Promise.all([
      fetchUsageSummary({ ...baseParams, channel: channelParam }),
      fetchUsageSessions({ ...baseParams, channel: channelParam, limit: 100 }),
      fetchClassificationUsage(baseParams),
      fetchTrainingUsage(baseParams).catch(() => null),
    ])
      .then(([s, list, classif, training]) => {
        setSummary(s);
        setSessions(list);
        setClassifUsage(classif);
        setTrainingUsage(training);
        setSessionsPage(0);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Erro ao carregar"))
      .finally(() => setLoading(false));
  }, [startDate, endDate, projectId, channel]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="usage-view">
      <div className="chat-panel-toolbar usage-toolbar">
        <label>Período:</label>
        <input type="date" lang="pt-BR" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        <span className="chat-controls__separator">até</span>
        <input type="date" lang="pt-BR" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        <label>Canal:</label>
        <select value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value={ALL_CHANNELS}>Todos</option>
          <option value="web">Web</option>
          <option value="telegram">Telegram</option>
        </select>
        <button type="button" className="btn" onClick={load} disabled={loading}>
          <RefreshCw size={16} style={loading ? { opacity: 0.6 } : undefined} />
          Atualizar
        </button>
      </div>

      {error && <div className="callout danger">{error}</div>}

      {summary && (
        <>
          <div className="usage-summary-cards">
            <div className="usage-stat-card">
              <span className="usage-stat-label">Total tokens</span>
              <span className="usage-stat-value">{formatTokens(
                summary.total_tokens
                + (classifUsage ? classifUsage.total_input_tokens + classifUsage.total_output_tokens : 0)
                + (trainingUsage ? trainingUsage.total_input_tokens + trainingUsage.total_output_tokens : 0)
              )}</span>
            </div>
            <div className="usage-stat-card">
              <span className="usage-stat-label">Custo est.</span>
              <span className="usage-stat-value">{formatUsd(summary.estimated_cost_usd + (classifUsage?.estimated_cost_usd ?? 0) + (trainingUsage?.estimated_cost_usd ?? 0))}</span>
            </div>
            <div className="usage-stat-card">
              <span className="usage-stat-label">Sessões</span>
              <span className="usage-stat-value">{summary.session_count}</span>
            </div>
            {classifUsage && classifUsage.total_calls > 0 && (
              <div className="usage-stat-card">
                <span className="usage-stat-label">Classificações</span>
                <span className="usage-stat-value">{classifUsage.total_calls}</span>
              </div>
            )}
            {trainingUsage && trainingUsage.total_calls > 0 && (
              <div className="usage-stat-card">
                <span className="usage-stat-label">Treinamento</span>
                <span className="usage-stat-value">{trainingUsage.total_calls}</span>
              </div>
            )}
          </div>

          <div className="usage-charts-row">
            <DailyTokenChart days={summary.by_day} />
            <TokensByTypeBar summary={summary} />
          </div>

          <h3 className="usage-section-title">Por modelo (Assistente)</h3>
          <div className="usage-table-wrap">
            <table className="usage-table">
              <thead>
                <tr>
                  <th className="left">Modelo</th>
                  <th>Input (tokens)</th>
                  <th>Output (tokens)</th>
                  <th>Input (custo)</th>
                  <th>Output (custo)</th>
                  <th>Total tokens</th>
                  <th>Custo total</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_model.length === 0 ? (
                  <tr><td colSpan={7} className="empty">Nenhum dado no período.</td></tr>
                ) : (
                  summary.by_model.map((row: UsageByModelEntry) => (
                    <tr key={row.model}>
                      <td className="left">{row.model}</td>
                      <td>{formatTokens(row.input_tokens)}</td>
                      <td>{formatTokens(row.output_tokens)}</td>
                      <td>{formatUsd4(row.input_cost_usd)}</td>
                      <td>{formatUsd4(row.output_cost_usd)}</td>
                      <td>{formatTokens(row.total_tokens)}</td>
                      <td>{formatUsd(row.estimated_cost_usd)}</td>
                    </tr>
                  ))
                )}
              </tbody>
              {summary.by_model.length > 0 && (
                <tfoot>
                  <tr className="usage-table-total">
                    <td className="left">Total</td>
                    <td>{formatTokens(summary.total_input_tokens)}</td>
                    <td>{formatTokens(summary.total_output_tokens)}</td>
                    <td>{formatUsd4(summary.by_model.reduce((s, r) => s + r.input_cost_usd, 0))}</td>
                    <td>{formatUsd4(summary.by_model.reduce((s, r) => s + r.output_cost_usd, 0))}</td>
                    <td>{formatTokens(summary.total_tokens)}</td>
                    <td>{formatUsd(summary.estimated_cost_usd)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          {classifUsage && classifUsage.total_calls > 0 && (
            <>
              <h3 className="usage-section-title">Classificação (uso LLM na ingestão)</h3>
              <div className="usage-table-wrap">
                <table className="usage-table usage-table--5col">
                  <thead>
                    <tr>
                      <th className="left">Modelo</th>
                      <th>Chamadas</th>
                      <th>Input (tokens)</th>
                      <th>Output (tokens)</th>
                      <th>Custo</th>
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
                      <tr className="usage-table-total">
                        <td className="left">Total</td>
                        <td>{classifUsage.total_calls}</td>
                        <td>{formatTokens(classifUsage.total_input_tokens)}</td>
                        <td>{formatTokens(classifUsage.total_output_tokens)}</td>
                        <td>{formatUsd(classifUsage.estimated_cost_usd)}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </>
          )}

          {trainingUsage && trainingUsage.total_calls > 0 && (
            <>
              <h3 className="usage-section-title">Treinamento / Pipeline</h3>
              <div className="usage-table-wrap">
                <table className="usage-table usage-table--5col">
                  <thead>
                    <tr>
                      <th className="left">Script</th>
                      <th>Chamadas</th>
                      <th>Input (tokens)</th>
                      <th>Output (tokens)</th>
                      <th>Custo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trainingUsage.by_script.map((row) => (
                      <tr key={row.script_name}>
                        <td className="left">{row.script_name}</td>
                        <td>{row.call_count}</td>
                        <td>{formatTokens(row.input_tokens)}</td>
                        <td>{formatTokens(row.output_tokens)}</td>
                        <td>{formatUsd(row.estimated_cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                  {trainingUsage.by_script.length > 0 && (
                    <tfoot>
                      <tr className="usage-table-total">
                        <td className="left">Total</td>
                        <td>{trainingUsage.total_calls}</td>
                        <td>{formatTokens(trainingUsage.total_input_tokens)}</td>
                        <td>{formatTokens(trainingUsage.total_output_tokens)}</td>
                        <td>{formatUsd(trainingUsage.estimated_cost_usd)}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </>
          )}

          <h3 className="usage-section-title">Sessões</h3>
          <div className="usage-table-wrap">
            <table className="usage-table">
              <thead>
                <tr>
                  <th className="left">Título</th>
                  <th className="left">Data</th>
                  <th className="left">Projeto</th>
                  <th className="left">Canal</th>
                  <th className="left">Modelo</th>
                  <th>Tokens</th>
                  <th>Custo</th>
                </tr>
              </thead>
              <tbody>
                {sessions.length === 0 ? (
                  <tr><td colSpan={7} className="empty">Nenhuma sessão no período.</td></tr>
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
                    const channelLabel = s.channel ? (CHANNEL_LABELS[s.channel] ?? s.channel) : "—";
                    return (
                      <tr key={s.id}>
                        <td className="left truncate" title={s.title || "Sem título"}>{s.title || "Sem título"}</td>
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
            </table>
            {sessions.length > PAGE_SIZE && (
              <div className="usage-pagination">
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={sessionsPage === 0}
                  onClick={() => setSessionsPage((p) => p - 1)}
                >
                  <ChevronLeft size={14} /> Anterior
                </button>
                <span className="usage-pagination-info">
                  {sessionsPage * PAGE_SIZE + 1}–{Math.min((sessionsPage + 1) * PAGE_SIZE, sessions.length)} de {sessions.length}
                </span>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={(sessionsPage + 1) * PAGE_SIZE >= sessions.length}
                  onClick={() => setSessionsPage((p) => p + 1)}
                >
                  Próxima <ChevronRight size={14} />
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
