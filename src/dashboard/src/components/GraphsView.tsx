"use client";

import { useMemo } from "react";
import { BarChart3 } from "lucide-react";
import { FoldMark } from "@/components/FoldMark";
import { BarChart, LineChart } from "@/components/RunCharts";
import { formatSeconds, clothConditionLabel } from "@/lib/format";
import {
  compoundChartTitle,
  conditionSlices,
  filterChartRuns,
  formatMetric,
  groupedMetric,
  kpis,
  metricSeries,
  type ChartFilters,
  type ChartGroup,
  type ChartMetric,
  type GraphGroup,
  type Slice,
} from "@/lib/run-charts";
import type { RunLifecycle, RunSummary } from "@/lib/types";

export function conditionFilterLabel(id: string): string {
  if (id === "damaged") return "Holes / torn";
  if (id === "notgood") return "Stains";
  if (id === "good") return "Clean";
  if (id === "skewed") return "Rotated";
  return clothConditionLabel(id);
}

export function GraphsView({
  runs,
  lifecycle,
  query,
  clothType,
  clothCondition,
  metric,
  group,
}: {
  runs: RunSummary[];
  lifecycle: "all" | RunLifecycle;
  query: string;
  clothType: string;
  clothCondition: string;
  metric: ChartMetric;
  group: GraphGroup;
}) {
  const rows = useMemo(
    () => filterChartRuns(runs, { lifecycle, query, clothType, clothCondition, batchId: "all" } satisfies ChartFilters),
    [runs, lifecycle, query, clothType, clothCondition],
  );

  const stats = kpis(rows);
  const mix = conditionSlices(rows).filter((slice) => slice.value > 0);
  const series = group === "run" ? metricSeries(rows, metric) : [];
  const bars = group === "run" ? [] : groupedMetric(rows, group as ChartGroup, metric);
  const hasPlot = group === "run" ? series.length > 0 : bars.length > 0;

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden border border-divider bg-surface">
      {rows.length === 0 ? (
        <div className="flex min-h-0 flex-1 flex-col justify-center px-6 py-8">
          <FoldMark size={32} className="mb-4 opacity-40" />
          <h2 className="text-lg font-semibold">No runs to plot</h2>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">
            {runs.length ? "No rows match this filter." : "Launch experiments to see holes, stains, cycle time, and clothing mix."}
          </p>
        </div>
      ) : (
        <>
          <header className="shrink-0 border-b border-divider px-4 py-3">
            <dl className="grid grid-cols-5 gap-3">
              <Stat label="Succeeded" value={String(stats.succeeded)} />
              <Stat label="Failed" value={String(stats.failed)} />
              <Stat label="Holes" value={String(stats.holes)} />
              <Stat label="Stains" value={String(stats.stains)} />
              <Stat label="Avg finish" value={formatSeconds(stats.avgCycleS)} />
            </dl>
            {mix.length ? <MixStrip slices={mix} /> : null}
          </header>
          <div className="flex min-h-0 flex-1 flex-col px-4 py-3">
            <h2 className="eyebrow mb-2 shrink-0">{compoundChartTitle(metric, group)}</h2>
            <div className="min-h-0 flex-1">
              {!hasPlot ? (
                <EmptyPlot />
              ) : group === "run" ? (
                <LineChart points={series} format={(v) => formatMetric(metric, v)} gradientId="compound-area" />
              ) : (
                <BarChart bars={bars} format={(v) => formatMetric(metric, v)} />
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function MixStrip({ slices }: { slices: Slice[] }) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0) || 1;
  return (
    <div className="mt-3 flex min-w-0 items-center gap-3 overflow-x-auto">
      <div className="flex h-1.5 min-w-0 flex-1 overflow-hidden bg-muted">
        {slices.map((slice) => (
          <div
            key={slice.key}
            className="h-full"
            style={{ width: `${(slice.value / total) * 100}%`, background: slice.color }}
            title={`${slice.label} · ${slice.value}`}
          />
        ))}
      </div>
      <ul className="flex shrink-0 items-center gap-3">
        {slices.map((slice) => (
          <li key={slice.key} className="flex items-center gap-1.5 font-mono text-[11px]">
            <span className="size-1.5 shrink-0 rounded-full" style={{ background: slice.color }} />
            <span className="text-muted-foreground">{slice.label}</span>
            <span className="tabular">{slice.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 border-l border-divider pl-3 first:border-l-0 first:pl-0">
      <dt className="eyebrow truncate">{label}</dt>
      <dd className="mt-0.5 font-mono text-xl tabular leading-none">{value}</dd>
    </div>
  );
}

function EmptyPlot() {
  return (
    <p className="flex h-full items-center gap-2 text-sm text-muted-foreground">
      <BarChart3 className="size-4" aria-hidden />
      Nothing measured for this pairing.
    </p>
  );
}
