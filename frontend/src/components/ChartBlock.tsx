import React from "react";
import "./ChartBlock.css";
import { formatNumber } from "../lib/format";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

/** Paleta de gráficos da marca (--chart-N, definida por tema em styles.css) */
const CHART_PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
  "var(--chart-8)",
];

const TOOLTIP_STYLE = {
  backgroundColor: "var(--panel-strong)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  color: "var(--text)",
  fontSize: 12,
};

interface ChartFacet {
  title?: string;
  data: Record<string, unknown>[];
}

interface ChartSpec {
  type: string;
  title?: string;
  data: Record<string, unknown>[];
  series?: string[];
  xKey?: string;
  yKey?: string;
  /** bubble: key da dimensão de cor (grupo) e do valor (tamanho/rótulo) */
  groupKey?: string;
  valueKey?: string;
  /** Small multiples: um mini-gráfico por facet (3ª dimensão categórica) */
  facets?: ChartFacet[];
}

function parseSpec(jsonString: string): ChartSpec | null {
  try {
    const raw = typeof jsonString === "string" ? jsonString : String(jsonString);
    const spec = JSON.parse(raw.trim()) as ChartSpec;
    if (!spec.type) return null;
    const hasData = Array.isArray(spec.data) && spec.data.length > 0;
    const hasFacets =
      Array.isArray(spec.facets) &&
      spec.facets.length > 0 &&
      spec.facets.every((f) => Array.isArray(f?.data) && f.data.length > 0);
    if (!hasData && !hasFacets) return null;
    return spec;
  } catch {
    return null;
  }
}

function getSeriesKeys(spec: ChartSpec): string[] {
  if (spec.series && spec.series.length > 0) return spec.series;
  const yKey = spec.yKey ?? "value";
  return [yKey];
}

function formatValue(v: unknown): string {
  if (typeof v !== "number") return String(v ?? "");
  if (v >= 1_000_000) return `${formatNumber(v / 1_000_000, { maximumFractionDigits: 1, minimumFractionDigits: 1 })}M`;
  if (v >= 1_000) return `${formatNumber(v / 1_000, { maximumFractionDigits: 1, minimumFractionDigits: 1 })}K`;
  return formatNumber(v);
}

function renderBar(spec: ChartSpec) {
  const xKey = spec.xKey ?? "name";
  const keys = getSeriesKeys(spec);
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={spec.data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2630" />
        <XAxis dataKey={xKey} tick={{ fill: "#a8a4b3", fontSize: 11 }} />
        <YAxis tick={{ fill: "#a8a4b3", fontSize: 11 }} tickFormatter={formatValue} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={formatValue} />
        {keys.length > 1 && <Legend />}
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={CHART_PALETTE[i % CHART_PALETTE.length]} radius={[3, 3, 0, 0]} isAnimationActive={true} animationDuration={600} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function renderStackedBar(spec: ChartSpec) {
  const xKey = spec.xKey ?? "name";
  const keys = getSeriesKeys(spec);
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={spec.data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2630" />
        <XAxis dataKey={xKey} tick={{ fill: "#a8a4b3", fontSize: 11 }} />
        <YAxis tick={{ fill: "#a8a4b3", fontSize: 11 }} tickFormatter={formatValue} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={formatValue} />
        <Legend />
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} stackId="a" fill={CHART_PALETTE[i % CHART_PALETTE.length]} isAnimationActive={true} animationDuration={600} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function renderHorizontalBar(spec: ChartSpec) {
  const xKey = spec.xKey ?? "name";
  const keys = getSeriesKeys(spec);
  return (
    <ResponsiveContainer width="100%" height={Math.max(280, spec.data.length * 32)}>
      <BarChart data={spec.data} layout="vertical" margin={{ top: 8, right: 12, bottom: 4, left: 80 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2630" />
        <XAxis type="number" tick={{ fill: "#a8a4b3", fontSize: 11 }} tickFormatter={formatValue} />
        <YAxis type="category" dataKey={xKey} tick={{ fill: "#a8a4b3", fontSize: 11 }} width={75} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={formatValue} />
        {keys.length > 1 && <Legend />}
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={CHART_PALETTE[i % CHART_PALETTE.length]} radius={[0, 3, 3, 0]} isAnimationActive={true} animationDuration={600} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function renderPie(spec: ChartSpec) {
  const yKey = spec.yKey ?? "value";
  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={spec.data}
          dataKey={yKey}
          nameKey={spec.xKey ?? "name"}
          cx="50%"
          cy="50%"
          outerRadius={100}
          isAnimationActive={true} animationDuration={600}
          label={({ name, percent }: { name?: string; percent?: number }) =>
            `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`
          }
          labelLine={{ stroke: "#a8a4b3" }}
        >
          {spec.data.map((_, i) => (
            <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={formatValue} />
      </PieChart>
    </ResponsiveContainer>
  );
}

function renderLine(spec: ChartSpec) {
  const xKey = spec.xKey ?? "name";
  const keys = getSeriesKeys(spec);
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={spec.data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2630" />
        <XAxis dataKey={xKey} tick={{ fill: "#a8a4b3", fontSize: 11 }} />
        <YAxis tick={{ fill: "#a8a4b3", fontSize: 11 }} tickFormatter={formatValue} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={formatValue} />
        {keys.length > 1 && <Legend />}
        {keys.map((k, i) => (
          <Line
            key={k}
            type="monotone"
            dataKey={k}
            stroke={CHART_PALETTE[i % CHART_PALETTE.length]}
            strokeWidth={2}
            dot={{ r: 3 }}
            isAnimationActive={true} animationDuration={600}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function renderArea(spec: ChartSpec) {
  const xKey = spec.xKey ?? "name";
  const keys = getSeriesKeys(spec);
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={spec.data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2630" />
        <XAxis dataKey={xKey} tick={{ fill: "#a8a4b3", fontSize: 11 }} />
        <YAxis tick={{ fill: "#a8a4b3", fontSize: 11 }} tickFormatter={formatValue} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={formatValue} />
        {keys.length > 1 && <Legend />}
        {keys.map((k, i) => (
          <Area
            key={k}
            type="monotone"
            dataKey={k}
            stroke={CHART_PALETTE[i % CHART_PALETTE.length]}
            fill={CHART_PALETTE[i % CHART_PALETTE.length]}
            fillOpacity={0.2}
            isAnimationActive={true} animationDuration={600}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

function renderComposed(spec: ChartSpec) {
  const xKey = spec.xKey ?? "name";
  const keys = getSeriesKeys(spec);
  const lineKeys = keys.length > 1 ? keys.slice(-1) : [];
  const barKeys = keys.length > 1 ? keys.slice(0, -1) : keys;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={spec.data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2630" />
        <XAxis dataKey={xKey} tick={{ fill: "#a8a4b3", fontSize: 11 }} />
        <YAxis tick={{ fill: "#a8a4b3", fontSize: 11 }} tickFormatter={formatValue} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={formatValue} />
        <Legend />
        {barKeys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={CHART_PALETTE[i % CHART_PALETTE.length]} radius={[3, 3, 0, 0]} isAnimationActive={true} animationDuration={600} />
        ))}
        {lineKeys.map((k, i) => (
          <Line
            key={k}
            type="monotone"
            dataKey={k}
            stroke={CHART_PALETTE[(barKeys.length + i) % CHART_PALETTE.length]}
            strokeWidth={2}
            dot={{ r: 3 }}
            isAnimationActive={true} animationDuration={600}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function renderTreemap(spec: ChartSpec) {
  const yKey = spec.yKey ?? "value";
  const coloredData = spec.data.map((d, i) => ({
    ...d,
    fill: CHART_PALETTE[i % CHART_PALETTE.length],
  }));
  return (
    <ResponsiveContainer width="100%" height={280}>
      <Treemap
        data={coloredData}
        dataKey={yKey}
        nameKey={spec.xKey ?? "name"}
        stroke="#1d1a20"
        content={(props: Record<string, unknown>) => {
          const x = Number(props.x ?? 0);
          const y = Number(props.y ?? 0);
          const width = Number(props.width ?? 0);
          const height = Number(props.height ?? 0);
          const name = String(props.name ?? "");
          const fill = String(props.fill ?? CHART_PALETTE[0]);
          return width > 40 && height > 20 ? (
            <g>
              <rect x={x} y={y} width={width} height={height} fill={fill} rx={3} />
              <text
                x={x + width / 2}
                y={y + height / 2}
                textAnchor="middle"
                dominantBaseline="central"
                fill="#f5f4f8"
                fontSize={11}
              >
                {String(name).length > Math.floor(width / 7) ? String(name).slice(0, Math.floor(width / 7)) + "…" : name}
              </text>
            </g>
          ) : (
            <rect x={x} y={y} width={width} height={height} fill={fill} rx={3} />
          );
        }}
      />
    </ResponsiveContainer>
  );
}

/** Matriz de calor: linhas = data[].name, colunas = series; intensidade na paleta da marca. */
function renderHeatmap(spec: ChartSpec) {
  const xKey = spec.xKey ?? "name";
  const cols = getSeriesKeys(spec);
  const values = spec.data.flatMap((row) => cols.map((c) => Number(row[c]) || 0));
  const max = Math.max(...values, 1);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate [border-spacing:3px]">
        <thead>
          <tr>
            <th className="p-1 text-left font-mono text-[0.65rem] font-normal uppercase tracking-wide text-tertiary" />
            {cols.map((c) => (
              <th key={c} className="p-1 text-center font-mono text-[0.65rem] font-normal text-tertiary">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.data.map((row) => (
            <tr key={String(row[xKey])}>
              <td className="whitespace-nowrap p-1 pr-2 text-right font-mono text-[0.7rem] text-muted-foreground">
                {String(row[xKey] ?? "")}
              </td>
              {cols.map((c) => {
                const value = Number(row[c]) || 0;
                const intensity = value === 0 ? 0 : 12 + Math.round(68 * (value / max));
                return (
                  <td
                    key={c}
                    title={`${row[xKey]} × ${c}: ${value}`}
                    className="min-w-11 rounded p-1.5 text-center font-mono text-[0.72rem] transition-colors"
                    style={{
                      background:
                        value === 0
                          ? "color-mix(in oklab, var(--border) 30%, transparent)"
                          : `color-mix(in oklab, var(--chart-1) ${intensity}%, transparent)`,
                      color: value === 0 ? "var(--text-tertiary)" : "var(--text)",
                    }}
                  >
                    {value === 0 ? "·" : formatValue(value)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Bolhas em eixos categóricos: x × y, cor = grupo, tamanho + rótulo = valor.
 *  4 dimensões num gráfico só (ex.: domínio × tipo, cor formato, tamanho quantidade). */
function renderBubble(spec: ChartSpec) {
  const xKey = spec.xKey ?? "x";
  const yKey = spec.yKey ?? "y";
  const groupKey = spec.groupKey ?? "group";
  const valueKey = spec.valueKey ?? "value";
  const groups = [...new Set(spec.data.map((d) => String(d[groupKey] ?? "")))];
  const yCount = new Set(spec.data.map((d) => String(d[yKey] ?? ""))).size;
  const height = Math.max(300, 90 + yCount * 46);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 12, right: 24, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2630" />
        <XAxis type="category" dataKey={xKey} allowDuplicatedCategory={false} tick={{ fill: "#a8a4b3", fontSize: 11 }} />
        <YAxis type="category" dataKey={yKey} allowDuplicatedCategory={false} tick={{ fill: "#a8a4b3", fontSize: 11 }} width={90} />
        <ZAxis dataKey={valueKey} range={[120, 1100]} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ strokeDasharray: "3 3" }}
          formatter={formatValue}
        />
        <Legend />
        {groups.map((group, i) => (
          <Scatter
            key={group}
            name={group}
            data={spec.data.filter((d) => String(d[groupKey] ?? "") === group)}
            fill={CHART_PALETTE[i % CHART_PALETTE.length]}
            fillOpacity={0.75}
            isAnimationActive={true}
            animationDuration={600}
          >
            <LabelList dataKey={valueKey} style={{ fontSize: 10, fill: "var(--text)", pointerEvents: "none" }} />
          </Scatter>
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}

const RENDERERS: Record<string, (spec: ChartSpec) => JSX.Element> = {
  bar: renderBar,
  grouped_bar: renderBar, // multi-series lado a lado (renderBar já agrupa quando há series)
  stacked_bar: renderStackedBar,
  horizontal_bar: renderHorizontalBar,
  pie: renderPie,
  line: renderLine,
  area: renderArea,
  composed: renderComposed,
  treemap: renderTreemap,
  heatmap: renderHeatmap,
  bubble: renderBubble,
};

export const ChartBlock = React.memo(function ChartBlock({ jsonString }: { jsonString: string }) {
  const spec = parseSpec(jsonString);
  if (!spec) {
    return (
      <pre className="chart-block-fallback my-2.5 overflow-x-auto rounded-md bg-black/20 px-3 py-2.5 text-[0.92em] [&_code]:bg-transparent [&_code]:p-0">
        <code>{jsonString}</code>
      </pre>
    );
  }

  const renderer = RENDERERS[spec.type];
  if (!renderer) {
    return (
      <pre className="chart-block-fallback my-2.5 overflow-x-auto rounded-md bg-black/20 px-3 py-2.5 text-[0.92em] [&_code]:bg-transparent [&_code]:p-0">
        <code>{jsonString}</code>
      </pre>
    );
  }

  // Small multiples: um mini-gráfico por facet (3ª dimensão categórica)
  if (spec.facets && spec.facets.length > 0) {
    return (
      <div className="chart-block-container my-2.5 overflow-hidden rounded-md bg-gradient-to-br from-panel-strong to-card p-4">
        {spec.title && <div className="mb-2.5 pl-1 font-display text-sm font-medium text-foreground">{spec.title}</div>}
        <div className={cnFacetGrid(spec.facets.length)}>
          {spec.facets.map((facet, i) => (
            <div key={facet.title ?? i} className="min-w-0">
              {facet.title && (
                <div className="mb-1 pl-1 font-mono text-[0.68rem] uppercase tracking-wide text-tertiary">{facet.title}</div>
              )}
              {renderer({ ...spec, data: facet.data, facets: undefined, title: undefined })}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="chart-block-container my-2.5 min-h-[280px] overflow-hidden rounded-md bg-gradient-to-br from-panel-strong to-card p-4">
      {spec.title && <div className="mb-2.5 pl-1 font-display text-sm font-medium text-foreground">{spec.title}</div>}
      {renderer(spec)}
    </div>
  );
});

function cnFacetGrid(count: number): string {
  return count > 1 ? "grid grid-cols-1 gap-4 sm:grid-cols-2" : "grid grid-cols-1 gap-4";
}
