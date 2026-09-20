import { clothTypeLabel, lifecycleLabel } from "@/lib/format";
import type { RunLifecycle, RunSummary } from "@/lib/types";

export type ChartMetric =
  | "count"
  | "cycle"
  | "wall"
  | "succeeded"
  | "failed"
  | "holes"
  | "stains"
  | "success"
  | "bag"
  | "flatness"
  | "fold";

export type ChartGroup = "outcome" | "clothType" | "clothCondition" | "batch" | "day" | "cycle";
export type GraphGroup = ChartGroup | "run";

export type ChartFilters = {
  lifecycle: "all" | RunLifecycle;
  query: string;
  clothType: string;
  clothCondition: string;
  batchId: string;
};

export const CHART_METRICS: { id: ChartMetric; label: string }[] = [
  { id: "cycle", label: "Time to finish (sim)" },
  { id: "wall", label: "Time to finish (wall)" },
  { id: "count", label: "Run count" },
  { id: "succeeded", label: "Succeeded" },
  { id: "failed", label: "Failed" },
  { id: "holes", label: "Holes / torn" },
  { id: "stains", label: "Stains" },
  { id: "success", label: "Success rate" },
  { id: "bag", label: "Packed in bag" },
  { id: "flatness", label: "Flatness after press" },
  { id: "fold", label: "Fold quality" },
];

export const GRAPH_MEASURES: { id: ChartMetric; label: string }[] = [
  { id: "cycle", label: "Time to finish" },
  { id: "failed", label: "Failures" },
  { id: "succeeded", label: "Succeeded" },
  { id: "count", label: "Runs" },
  { id: "holes", label: "Holes" },
  { id: "stains", label: "Stains" },
  { id: "success", label: "Success rate" },
  { id: "fold", label: "Fold quality" },
];

export const GRAPH_GROUPS: { id: GraphGroup; label: string }[] = [
  { id: "clothType", label: "Clothing type" },
  { id: "clothCondition", label: "Condition" },
  { id: "outcome", label: "Outcome" },
  { id: "cycle", label: "Finish time" },
  { id: "run", label: "Run order" },
];

export const CHART_GROUPS: { id: ChartGroup; label: string }[] = [
  { id: "clothType", label: "Clothing type" },
  { id: "clothCondition", label: "Condition" },
  { id: "outcome", label: "Outcome" },
  { id: "cycle", label: "Finish time" },
  { id: "batch", label: "Batch" },
  { id: "day", label: "Day" },
];

const CYCLE_BIN_ORDER = ["lt20", "20-40", "40-60", "60plus", "unmeasured"];
const CYCLE_BIN_LABEL: Record<string, string> = {
  lt20: "< 20 s",
  "20-40": "20–40 s",
  "40-60": "40–60 s",
  "60plus": "≥ 60 s",
  unmeasured: "Unmeasured",
};
const CYCLE_BIN_COLOR: Record<string, string> = {
  lt20: "var(--active)",
  "20-40": "var(--primary)",
  "40-60": "var(--warning)",
  "60plus": "var(--destructive)",
  unmeasured: "var(--border)",
};

const OUTCOME_ORDER: RunLifecycle[] = [
  "succeeded",
  "failed",
  "cancelled",
  "running",
  "paused",
  "queued",
];

export const OUTCOME_COLOR: Record<string, string> = {
  succeeded: "var(--active)",
  failed: "var(--destructive)",
  cancelled: "var(--muted-foreground)",
  running: "var(--primary)",
  paused: "var(--warning)",
  queued: "var(--border)",
};

export const CONDITION_COLOR: Record<string, string> = {
  good: "var(--active)",
  damaged: "var(--destructive)",
  notgood: "var(--warning)",
  skewed: "var(--primary)",
  unknown: "var(--border)",
};

const CONDITION_LABEL: Record<string, string> = {
  good: "Clean",
  damaged: "Holes",
  notgood: "Stains",
  skewed: "Rotated",
  unknown: "Unspecified",
};

const CLOTH_COLOR = [
  "var(--active)",
  "var(--primary)",
  "var(--warning)",
  "var(--active-ink)",
  "var(--destructive)",
  "var(--muted-foreground)",
];

export function filterChartRuns(runs: RunSummary[], filters: ChartFilters): RunSummary[] {
  const q = filters.query.trim().toLowerCase();
  return runs.filter((run) => {
    if (filters.lifecycle !== "all" && run.lifecycle !== filters.lifecycle) return false;
    if (filters.clothType !== "all" && clothKey(run) !== filters.clothType) return false;
    if (filters.clothCondition !== "all" && conditionKey(run) !== filters.clothCondition) return false;
    if (filters.batchId === "none" && run.batchId) return false;
    if (filters.batchId !== "all" && filters.batchId !== "none" && run.batchId !== filters.batchId) {
      return false;
    }
    if (!q) return true;
    return (
      run.id.toLowerCase().includes(q) ||
      String(run.seed).includes(q) ||
      (run.garment?.toLowerCase().includes(q) ?? false) ||
      (run.clothType?.toLowerCase().includes(q) ?? false) ||
      (run.name?.toLowerCase().includes(q) ?? false) ||
      (run.batchId?.toLowerCase().includes(q) ?? false)
    );
  });
}

export function uniqueValues(runs: RunSummary[], key: "clothType" | "clothCondition" | "batchId"): string[] {
  const set = new Set<string>();
  for (const run of runs) {
    if (key === "batchId") {
      if (run.batchId) set.add(run.batchId);
      continue;
    }
    set.add(key === "clothType" ? clothKey(run) : conditionKey(run));
  }
  return [...set].sort();
}

export type KpiSet = {
  runs: number;
  succeeded: number;
  failed: number;
  holes: number;
  stains: number;
  skewed: number;
  avgCycleS: number | null;
  avgWallS: number | null;
  clothTypes: number;
  bagRate: number | null;
};

export function kpis(runs: RunSummary[]): KpiSet {
  const cycles = runs.map((r) => r.metrics.cycleTimeSimS).filter((v): v is number => v != null);
  const walls = runs.map((r) => r.metrics.cycleTimeWallS).filter((v): v is number => v != null);
  const bagged = runs.filter((r) => r.metrics.shirtInBag != null);
  const types = new Set(runs.map(clothKey));
  return {
    runs: runs.length,
    succeeded: runs.filter((r) => r.lifecycle === "succeeded").length,
    failed: runs.filter((r) => r.lifecycle === "failed").length,
    holes: runs.filter((r) => conditionKey(r) === "damaged").length,
    stains: runs.filter((r) => conditionKey(r) === "notgood").length,
    skewed: runs.filter((r) => conditionKey(r) === "skewed").length,
    avgCycleS: mean(cycles),
    avgWallS: mean(walls),
    clothTypes: [...types].filter((k) => k !== "unknown").length,
    bagRate: bagged.length ? bagged.filter((r) => r.metrics.shirtInBag).length / bagged.length : null,
  };
}

export type Slice = { key: string; label: string; value: number; color: string };

export function outcomeSlices(runs: RunSummary[]): Slice[] {
  return countSlices(runs, (r) => r.lifecycle, (key) => lifecycleLabel(key), OUTCOME_COLOR, OUTCOME_ORDER);
}

export function conditionSlices(runs: RunSummary[]): Slice[] {
  const order = ["damaged", "notgood", "good", "skewed", "unknown"];
  return countSlices(runs, conditionKey, (key) => CONDITION_LABEL[key] ?? key, CONDITION_COLOR, order);
}

export function clothTypeSlices(runs: RunSummary[]): Slice[] {
  const slices = countSlices(runs, clothKey, clothChartLabel, {}, []);
  return slices.map((slice, i) => ({ ...slice, color: CLOTH_COLOR[i % CLOTH_COLOR.length] }));
}

export type GroupBar = { key: string; label: string; value: number; color: string };

export function groupedMetric(runs: RunSummary[], group: ChartGroup, metric: ChartMetric): GroupBar[] {
  const buckets = bucket(runs, group);
  return [...buckets.entries()].map(([key, list], i) => ({
    key,
    label: groupLabel(key, group),
    value: metricValue(list, metric),
    color: barColor(group, key, i),
  }));
}

export type StackedBar = {
  key: string;
  label: string;
  parts: { key: string; label: string; value: number; color: string }[];
};

export function outcomeByGroup(runs: RunSummary[], group: ChartGroup): StackedBar[] {
  const buckets = bucket(runs, group);
  return [...buckets.entries()].map(([key, list]) => ({
    key,
    label: groupLabel(key, group),
    parts: [
      { key: "succeeded", label: "Succeeded", value: list.filter((r) => r.lifecycle === "succeeded").length, color: OUTCOME_COLOR.succeeded },
      { key: "failed", label: "Failed", value: list.filter((r) => r.lifecycle === "failed").length, color: OUTCOME_COLOR.failed },
      { key: "cancelled", label: "Cancelled", value: list.filter((r) => r.lifecycle === "cancelled").length, color: OUTCOME_COLOR.cancelled },
    ],
  }));
}

export type SeriesPoint = { id: string; t: number; label: string; value: number };

export function metricSeries(runs: RunSummary[], metric: ChartMetric): SeriesPoint[] {
  const dated = [...runs].sort((a, b) => (a.startedAtIso ?? "").localeCompare(b.startedAtIso ?? ""));
  const points: SeriesPoint[] = [];
  dated.forEach((run, index) => {
    const value = pointMetric(run, metric, dated.slice(0, index + 1));
    if (value == null) return;
    points.push({
      id: run.id,
      t: Date.parse(run.startedAtIso ?? "") || index,
      label: run.id,
      value,
    });
  });
  return points;
}

function bucket(runs: RunSummary[], group: ChartGroup): Map<string, RunSummary[]> {
  const buckets = new Map<string, RunSummary[]>();
  for (const run of runs) {
    const key = groupKey(run, group);
    const list = buckets.get(key) ?? [];
    list.push(run);
    buckets.set(key, list);
  }
  const keys = [...buckets.keys()].sort((a, b) => {
    if (group === "outcome") return OUTCOME_ORDER.indexOf(a as RunLifecycle) - OUTCOME_ORDER.indexOf(b as RunLifecycle);
    if (group === "clothCondition") {
      const order = ["damaged", "notgood", "good", "skewed", "unknown"];
      return order.indexOf(a) - order.indexOf(b);
    }
    if (group === "cycle") return CYCLE_BIN_ORDER.indexOf(a) - CYCLE_BIN_ORDER.indexOf(b);
    return a.localeCompare(b);
  });
  return new Map(keys.map((key) => [key, buckets.get(key) ?? []]));
}

function countSlices(
  runs: RunSummary[],
  keyOf: (run: RunSummary) => string,
  labelOf: (key: string) => string,
  colors: Record<string, string>,
  order: string[],
): Slice[] {
  const counts = new Map<string, number>();
  for (const run of runs) {
    const key = keyOf(run);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const keys = order.length ? order.filter((key) => counts.get(key)) : [...counts.keys()].sort();
  return keys.map((key) => ({
    key,
    label: labelOf(key),
    value: counts.get(key) ?? 0,
    color: colors[key] ?? "var(--border)",
  }));
}

function groupKey(run: RunSummary, group: ChartGroup): string {
  if (group === "outcome") return run.lifecycle;
  if (group === "clothType") return clothKey(run);
  if (group === "clothCondition") return conditionKey(run);
  if (group === "cycle") return cycleBinKey(run.metrics.cycleTimeSimS);
  if (group === "batch") return run.batchId ?? "solo";
  return (run.startedAtIso ?? "").slice(0, 10) || "unknown";
}

function groupLabel(key: string, group: ChartGroup): string {
  if (group === "outcome") return lifecycleLabel(key);
  if (group === "clothType") return clothChartLabel(key);
  if (group === "clothCondition") return CONDITION_LABEL[key] ?? key;
  if (group === "cycle") return CYCLE_BIN_LABEL[key] ?? key;
  if (group === "batch") return key === "solo" ? "No batch" : key;
  return key;
}

function clothChartLabel(key: string): string {
  return key === "unknown" ? "Unspecified" : clothTypeLabel(key);
}

function barColor(group: ChartGroup, key: string, index: number): string {
  if (group === "outcome") return OUTCOME_COLOR[key] ?? "var(--active)";
  if (group === "clothCondition") return CONDITION_COLOR[key] ?? "var(--active)";
  if (group === "cycle") return CYCLE_BIN_COLOR[key] ?? "var(--active)";
  return CLOTH_COLOR[index % CLOTH_COLOR.length];
}

function cycleBinKey(seconds: number | null | undefined): string {
  if (seconds == null) return "unmeasured";
  if (seconds < 20) return "lt20";
  if (seconds < 40) return "20-40";
  if (seconds < 60) return "40-60";
  return "60plus";
}

export function compoundChartTitle(metric: ChartMetric, group: GraphGroup): string {
  const measure = GRAPH_MEASURES.find((item) => item.id === metric)?.label ?? metric;
  if (group === "run") return `${measure} over runs`;
  const by = GRAPH_GROUPS.find((item) => item.id === group)?.label ?? group;
  return `${measure} by ${by.toLowerCase()}`;
}

function metricValue(runs: RunSummary[], metric: ChartMetric): number {
  if (metric === "count") return runs.length;
  if (metric === "succeeded") return runs.filter((r) => r.lifecycle === "succeeded").length;
  if (metric === "failed") return runs.filter((r) => r.lifecycle === "failed").length;
  if (metric === "holes") return runs.filter((r) => conditionKey(r) === "damaged").length;
  if (metric === "stains") return runs.filter((r) => conditionKey(r) === "notgood").length;
  if (metric === "cycle") return mean(runs.map((r) => r.metrics.cycleTimeSimS).filter((v): v is number => v != null)) ?? 0;
  if (metric === "wall") return mean(runs.map((r) => r.metrics.cycleTimeWallS).filter((v): v is number => v != null)) ?? 0;
  if (metric === "success") {
    const finished = runs.filter((r) => r.lifecycle === "succeeded" || r.lifecycle === "failed");
    return finished.length ? runs.filter((r) => r.lifecycle === "succeeded").length / finished.length : 0;
  }
  if (metric === "bag") {
    const known = runs.filter((r) => r.metrics.shirtInBag != null);
    return known.length ? known.filter((r) => r.metrics.shirtInBag).length / known.length : 0;
  }
  if (metric === "fold") return mean(runs.map(foldQualityOf).filter((v): v is number => v != null)) ?? 0;
  return mean(runs.map((r) => r.metrics.flatnessPost).filter((v): v is number => v != null)) ?? 0;
}

function pointMetric(run: RunSummary, metric: ChartMetric, prefix: RunSummary[]): number | null {
  if (metric === "count") return prefix.length;
  if (metric === "succeeded") return prefix.filter((r) => r.lifecycle === "succeeded").length;
  if (metric === "failed") return prefix.filter((r) => r.lifecycle === "failed").length;
  if (metric === "holes") return prefix.filter((r) => conditionKey(r) === "damaged").length;
  if (metric === "stains") return prefix.filter((r) => conditionKey(r) === "notgood").length;
  if (metric === "cycle") return run.metrics.cycleTimeSimS;
  if (metric === "wall") return run.metrics.cycleTimeWallS;
  if (metric === "success") {
    const finished = prefix.filter((r) => r.lifecycle === "succeeded" || r.lifecycle === "failed");
    return finished.length ? prefix.filter((r) => r.lifecycle === "succeeded").length / finished.length : null;
  }
  if (metric === "bag") return run.metrics.shirtInBag == null ? null : run.metrics.shirtInBag ? 1 : 0;
  if (metric === "fold") return foldQualityOf(run);
  return run.metrics.flatnessPost;
}

export function formatMetric(metric: ChartMetric, value: number): string {
  if (metric === "cycle" || metric === "wall") return `${value.toFixed(1)} s`;
  if (metric === "success" || metric === "bag") return `${Math.round(value * 100)} %`;
  if (metric === "fold") return `${Math.round(value)} %`;
  if (metric === "flatness") return `${(value * 1000).toFixed(2)} mm`;
  return String(Math.round(value));
}

function foldQualityOf(run: RunSummary): number | null {
  return run.metrics.foldQuality ?? run.metrics.measurements?.foldQualityPct ?? null;
}

function clothKey(run: RunSummary): string {
  return run.clothType ?? run.garment ?? "unknown";
}

function conditionKey(run: RunSummary): string {
  return run.clothCondition ?? "unknown";
}

function mean(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}
