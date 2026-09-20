"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type CSSProperties } from "react";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/table";
import { AppShell } from "@/components/AppShell";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { GraphsView, conditionFilterLabel } from "@/components/GraphsView";
import { NewExperimentDialog } from "@/components/NewExperimentDialog";
import { RunStatusBadges } from "@/components/RunStatusBadges";
import { XFoldLoader } from "@/components/XFoldLoader";
import { cycleFill, groupOperatorSteps } from "@/lib/cycle-progress";
import { useDashboard } from "@/lib/dashboard-context";
import { formatIso, formatSeconds, clothTypeLabel } from "@/lib/format";
import { filterChartRuns, GRAPH_GROUPS, GRAPH_MEASURES, uniqueValues, type ChartMetric, type GraphGroup } from "@/lib/run-charts";
import type { RunLifecycle, RunSummary } from "@/lib/types";

const LIFECYCLES: [RunLifecycle | "all", string][] = [
  ["all", "All"],
  ["running", "Running"],
  ["succeeded", "Succeeded"],
  ["failed", "Failed"],
  ["cancelled", "Cancelled"],
  ["paused", "Paused"],
  ["queued", "Queued"],
];

const CONTROL =
  "h-10 rounded-[var(--radius-sm)] border border-input bg-surface px-3 text-sm";
const FIELD = `mt-1 block ${CONTROL}`;

/** Single list of every run (individual or batch member). Opening one lands in the control view. */
export function HistoryView() {
  const { history, snapshot, ready } = useDashboard();
  const router = useRouter();
  const [lifecycle, setLifecycle] = useState<"all" | RunLifecycle>("all");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"list" | "graphs">("list");
  const [clothType, setClothType] = useState("all");
  const [clothCondition, setClothCondition] = useState("all");
  const [metric, setMetric] = useState<ChartMetric>("cycle");
  const [group, setGroup] = useState<GraphGroup>("clothType");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    // Running first, then queued, then the rest as the bridge ordered them
    // (newest first): the live ones sit at the top of the same list.
    const rank = (run: RunSummary) =>
      run.lifecycle === "running" || run.lifecycle === "paused" ? 0 : run.lifecycle === "queued" ? 1 : 2;
    const matches = history.filter((run) => {
      if (lifecycle !== "all" && run.lifecycle !== lifecycle) return false;
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
    return matches
      .map((run, index) => ({ run, index }))
      .sort((a, b) => rank(a.run) - rank(b.run) || a.index - b.index)
      .map(({ run }) => run);
  }, [history, lifecycle, query]);

  const graphRows = useMemo(
    () => filterChartRuns(history, { lifecycle, query, clothType, clothCondition, batchId: "all" }),
    [history, lifecycle, query, clothType, clothCondition],
  );

  const listBody = !ready ? (
    <div
      className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 border border-divider bg-surface px-6 py-10"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <XFoldLoader size={72} showLabel label="Loading runs…" decorative={false} />
    </div>
  ) : view === "graphs" ? (
    <GraphsView
      runs={history}
      lifecycle={lifecycle}
      query={query}
      clothType={clothType}
      clothCondition={clothCondition}
      metric={metric}
      group={group}
    />
  ) : rows.length === 0 ? (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center border border-divider bg-surface px-8 py-16 text-center">
      <p className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
        {history.length
          ? "No rows match this filter"
          : snapshot.connection === "disconnected"
            ? "Bridge offline"
            : "No runs"}
      </p>
      <p className="mt-3 max-w-md text-base text-muted-foreground sm:text-lg">
        {history.length
          ? "Try clearing search or status."
          : snapshot.connection === "disconnected"
            ? "Connect the simulator — the list stays empty until real runs exist."
            : "Launch the first from “New experiment”."}
      </p>
    </div>
  ) : (
    <div className="min-h-0 flex-1 overflow-auto border border-divider bg-surface">
      <Table className="w-full min-w-[720px] border-collapse text-left text-sm">
        <TableHeader>
          <TableRow className="border-b border-divider text-[13px] text-muted-foreground">
            <TableHead className="px-4 py-3 font-semibold">Run</TableHead>
            <TableHead className="px-4 py-3 font-semibold">Status</TableHead>
            <TableHead className="px-4 py-3 font-semibold">Batch</TableHead>
            <TableHead className="px-4 py-3 font-semibold">Seed</TableHead>
            <TableHead className="px-4 py-3 text-right font-semibold">cycle t (sim)</TableHead>
            <TableHead className="px-4 py-3 font-semibold">Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((run) => <RunRow key={run.id} run={run} onOpen={() => router.push(`/historial/${run.id}`)} />)}
        </TableBody>
      </Table>
    </div>
  );

  return (
    <AppShell
      fit
      title="Runs"
      eyebrow="individual · batches"
      actions={
        <>
          <ConnectionBadge
            connection={snapshot.connection}
            provenance={snapshot.provenance}
            lastUpdatedIso={snapshot.lastUpdatedIso}
          />
          <NewExperimentDialog />
        </>
      }
    >
      <div className="mb-3 flex shrink-0 items-end gap-3 overflow-x-auto">
        <div>
          <p className="text-[13px] font-semibold" id="history-view-label">View</p>
          <div className="mt-1 flex gap-2" role="group" aria-labelledby="history-view-label">
            <button
              type="button"
              aria-pressed={view === "list"}
              onClick={() => setView("list")}
              className={`${CONTROL} ${view === "list" ? "font-semibold text-ink" : "text-muted-foreground hover:text-ink"}`}
            >
              List
            </button>
            <button
              type="button"
              aria-pressed={view === "graphs"}
              onClick={() => setView("graphs")}
              className={`${CONTROL} ${view === "graphs" ? "font-semibold text-ink" : "text-muted-foreground hover:text-ink"}`}
            >
              Graphs
            </button>
          </div>
        </div>
        <div>
          <label htmlFor="history-q" className="text-[13px] font-semibold">Search</label>
          <input
            id="history-q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="RUN-014, seed, batch…"
            className={`${FIELD} w-52`}
          />
        </div>
        <div>
          <label htmlFor="history-life" className="text-[13px] font-semibold">Status</label>
          <select
            id="history-life"
            value={lifecycle}
            onChange={(e) => setLifecycle(e.target.value as "all" | RunLifecycle)}
            className={FIELD}
          >
            {LIFECYCLES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </div>
        {view === "graphs" ? (
          <>
            <div>
              <label htmlFor="graph-cloth" className="text-[13px] font-semibold">Clothing</label>
              <select id="graph-cloth" className={FIELD} value={clothType} onChange={(e) => setClothType(e.target.value)}>
                <option value="all">All types</option>
                {uniqueValues(history, "clothType").map((id) => (
                  <option key={id} value={id}>{id === "unknown" ? "Unspecified" : clothTypeLabel(id)}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="graph-cond" className="text-[13px] font-semibold">Condition</label>
              <select id="graph-cond" className={FIELD} value={clothCondition} onChange={(e) => setClothCondition(e.target.value)}>
                <option value="all">All conditions</option>
                {uniqueValues(history, "clothCondition").map((id) => (
                  <option key={id} value={id}>{id === "unknown" ? "Unspecified" : conditionFilterLabel(id)}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="graph-metric" className="text-[13px] font-semibold">Measure</label>
              <select
                id="graph-metric"
                className={FIELD}
                value={metric}
                onChange={(e) => setMetric(e.target.value as ChartMetric)}
              >
                {GRAPH_MEASURES.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="graph-group" className="text-[13px] font-semibold">By</label>
              <select
                id="graph-group"
                className={FIELD}
                value={group}
                onChange={(e) => setGroup(e.target.value as GraphGroup)}
              >
                {GRAPH_GROUPS.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </div>
          </>
        ) : null}
        <span className="ml-auto self-center font-mono text-[11px] tabular text-muted-foreground">
          {ready
            ? `${view === "graphs" ? graphRows.length : rows.length} / ${history.length}`
            : "…"}
        </span>
      </div>

      {listBody}
    </AppShell>
  );
}

function RunRow({ run, onOpen }: { run: RunSummary; onOpen: () => void }) {
  const { getRun } = useDashboard();
  const live = run.lifecycle === "running" || run.lifecycle === "paused";
  const stages = live ? getRun(run.id)?.stages ?? [] : [];
  const fill = stages.length ? cycleFill(groupOperatorSteps(stages)) : 0;
  const pct = `${Math.round(fill * 1000) / 10}%`;

  return (
    <TableRow
      className={`cursor-pointer border-b border-divider hover:bg-canvas ${
        live && fill > 0 && run.lifecycle === "running" ? "row-fill-live" : ""
      }`}
      style={
        live && fill > 0
          ? ({
              "--row-fill": pct,
              ...(run.lifecycle === "paused"
                ? { backgroundImage: `linear-gradient(90deg, var(--active-surface) ${pct}, transparent ${pct})` }
                : null),
            } as CSSProperties)
          : undefined
      }
      aria-busy={run.lifecycle === "running" || undefined}
      onClick={onOpen}
    >
      <TableCell className="px-4 py-3">
        <Link
          href={`/historial/${run.id}`}
          onClick={(e) => e.stopPropagation()}
          className="font-mono font-semibold tabular underline-offset-2 hover:underline"
        >
          {run.id}
        </Link>
        {run.name ? <span className="mt-0.5 block text-[13px] text-muted-foreground">{run.name}</span> : null}
      </TableCell>
      <TableCell className="px-4 py-3">
        <RunStatusBadges run={run} />
      </TableCell>
      <TableCell className="px-4 py-3 font-mono text-muted-foreground tabular">
        {run.batchId ? (
          <Link
            href={`/experimentos/${run.batchId}`}
            onClick={(e) => e.stopPropagation()}
            className="underline-offset-2 hover:underline"
          >
            {run.batchId}
          </Link>
        ) : "—"}
      </TableCell>
      <TableCell className="px-4 py-3 font-mono tabular">{run.seed}</TableCell>
      <TableCell className="px-4 py-3 font-mono tabular">
        {run.speed && run.speed !== 1 ? `${run.speed}x` : "—"}
      </TableCell>
      <TableCell className="px-4 py-3 text-right font-mono tabular">{formatSeconds(run.metrics.cycleTimeSimS)}</TableCell>
      <TableCell className="px-4 py-3 text-muted-foreground">{formatIso(run.startedAtIso)}</TableCell>
    </TableRow>
  );
}
