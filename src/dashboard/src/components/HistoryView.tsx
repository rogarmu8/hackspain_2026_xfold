"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/table";
import { AppShell } from "@/components/AppShell";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { FoldMark } from "@/components/FoldMark";
import { NewExperimentDialog } from "@/components/NewExperimentDialog";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useDashboard } from "@/lib/dashboard-context";
import { formatIso, formatSeconds, lifecycleLabel } from "@/lib/format";
import type { RunLifecycle, RunSummary } from "@/lib/types";

const LIFECYCLES: [RunLifecycle | "all", string][] = [
  ["all", "Todos"],
  ["running", "En curso"],
  ["succeeded", "Correctas"],
  ["failed", "Fallidas"],
  ["cancelled", "Canceladas"],
  ["paused", "En pausa"],
  ["queued", "En cola"],
];

const tone = (lifecycle: RunLifecycle) =>
  lifecycle === "running" || lifecycle === "paused"
    ? "active"
    : lifecycle === "failed"
      ? "danger"
      : lifecycle === "succeeded"
        ? "success"
        : "neutral";

/** Single list of every run (individual or batch member). Opening one lands in the control view. */
export function HistoryView() {
  const { history, snapshot } = useDashboard();
  const router = useRouter();
  const [lifecycle, setLifecycle] = useState<"all" | RunLifecycle>("all");
  const [query, setQuery] = useState("");

  const active = snapshot.activeRun;
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return history.filter((run) => {
      if (run.id === active?.id) return false;
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
  }, [history, lifecycle, query, active?.id]);

  return (
    <AppShell
      title="Ejecuciones"
      eyebrow="individuales · batches"
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
      {snapshot.provenance === "fixture" ? (
        <p className="eyebrow mb-4">Datos de ejemplo</p>
      ) : null}

      {active ? (
        <Link
          href={`/historial/${active.id}`}
          className="mb-4 flex flex-wrap items-center gap-3 border border-active/40 bg-surface px-4 py-3 no-underline hover:border-active"
        >
          <StatusBadge tone="active">{lifecycleLabel(active.lifecycle)}</StatusBadge>
          <span className="font-mono font-semibold tabular">{active.id}</span>
          {active.name ? <span className="text-sm text-muted-foreground">{active.name}</span> : null}
          <span className="ml-auto inline-flex items-center gap-1 text-sm font-semibold">
            Abrir control <ArrowUpRight className="size-3.5" aria-hidden />
          </span>
        </Link>
      ) : null}

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="history-q" className="text-[13px] font-semibold">Buscar</label>
          <input
            id="history-q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="RUN-014, semilla, batch…"
            className="mt-1 block h-10 w-64 rounded-[var(--radius-sm)] border border-input bg-surface px-3 text-sm"
          />
        </div>
        <div>
          <label htmlFor="history-life" className="text-[13px] font-semibold">Estado</label>
          <select
            id="history-life"
            value={lifecycle}
            onChange={(e) => setLifecycle(e.target.value as "all" | RunLifecycle)}
            className="mt-1 block h-10 rounded-[var(--radius-sm)] border border-input bg-surface px-3 text-sm"
          >
            {LIFECYCLES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </div>
        <span className="ml-auto self-center font-mono text-[11px] tabular text-muted-foreground">
          {rows.length} / {history.length}
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="border border-divider bg-surface px-6 py-10">
          <FoldMark size={32} className="mb-4 opacity-40" />
          <h2 className="text-lg font-semibold">Sin ejecuciones</h2>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">
            {history.length
              ? "No hay filas con este filtro."
              : "Todavía no hay corridas registradas. Lanza la primera desde «Nuevo experimento»."}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto border border-divider bg-surface">
          <Table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <TableHeader>
              <TableRow className="border-b border-divider text-[13px] text-muted-foreground">
                <TableHead className="px-4 py-3 font-semibold">Ejecución</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Estado</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Batch</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Semilla</TableHead>
                <TableHead className="px-4 py-3 text-right font-semibold">t ciclo (sim)</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Inicio</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((run) => <RunRow key={run.id} run={run} onOpen={() => router.push(`/historial/${run.id}`)} />)}
            </TableBody>
          </Table>
        </div>
      )}
    </AppShell>
  );
}

function RunRow({ run, onOpen }: { run: RunSummary; onOpen: () => void }) {
  return (
    <TableRow
      className="cursor-pointer border-b border-divider hover:bg-canvas"
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
        <StatusBadge tone={tone(run.lifecycle)}>{lifecycleLabel(run.lifecycle)}</StatusBadge>
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
      <TableCell className="px-4 py-3 text-right font-mono tabular">{formatSeconds(run.metrics.cycleTimeSimS)}</TableCell>
      <TableCell className="px-4 py-3 text-muted-foreground">{formatIso(run.startedAtIso)}</TableCell>
    </TableRow>
  );
}
