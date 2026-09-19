"use client";

import Link from "next/link";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/table";
import { lifecycleLabel } from "@/lib/format";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useDashboard } from "@/lib/dashboard-context";
import { formatIso, formatSeconds } from "@/lib/format";
import type { RunLifecycle } from "@/lib/types";

export function HistoryView() {
  const { history, snapshot } = useDashboard();
  const [lifecycle, setLifecycle] = useState<"all" | RunLifecycle>("all");
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    return history.filter((run) => {
      if (lifecycle !== "all" && run.lifecycle !== lifecycle) return false;
      if (!query.trim()) return true;
      const q = query.trim().toLowerCase();
      return (
        run.id.toLowerCase().includes(q) ||
        String(run.seed).includes(q) ||
        (run.name?.toLowerCase().includes(q) ?? false)
      );
    });
  }, [history, lifecycle, query]);

  return (
    <AppShell
      title="Historial"
      eyebrow="trazabilidad · ejecuciones"
      actions={
        <ConnectionBadge
          connection={snapshot.connection}
          provenance={snapshot.provenance}
          lastUpdatedIso={snapshot.lastUpdatedIso}
        />
      }
    >
      {snapshot.provenance === "fixture" ? (
        <p className="mb-4 text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
          Datos de ejemplo
        </p>
      ) : null}

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="history-q" className="text-[13px] font-semibold">
            Buscar
          </label>
          <input
            id="history-q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="RUN-014, semilla…"
            className="mt-1 block h-11 w-56 rounded-[var(--radius-sm)] border border-input bg-surface px-3"
          />
        </div>
        <div>
          <label htmlFor="history-life" className="text-[13px] font-semibold">
            Estado
          </label>
          <select
            id="history-life"
            value={lifecycle}
            onChange={(e) =>
              setLifecycle(e.target.value as "all" | RunLifecycle)
            }
            className="mt-1 block h-11 rounded-[var(--radius-sm)] border border-input bg-surface px-3"
          >
            <option value="all">Todos</option>
            <option value="running">En curso</option>
            <option value="succeeded">Correctas</option>
            <option value="failed">Fallidas</option>
            <option value="cancelled">Canceladas</option>
            <option value="paused">En pausa</option>
            <option value="queued">En cola</option>
          </select>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="border border-divider bg-surface px-6 py-10">
          <h2 className="text-lg font-semibold">Sin ejecuciones</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            No hay filas con este filtro. La ausencia de datos no es un cero de
            éxito.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto border border-divider bg-surface">
          <Table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <TableHeader>
              <TableRow className="border-b border-divider text-[13px] text-muted-foreground">
                <TableHead className="px-4 py-3 font-semibold">Ejecución</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Batch</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Semilla</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Estado</TableHead>
                <TableHead className="px-4 py-3 font-semibold text-right">t ciclo (sim)</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Inicio</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((run) => (
                <TableRow key={run.id} className="border-b border-divider">
                  <TableCell className="px-4 py-3">
                    <Link
                      href={`/historial/${run.id}`}
                      className="font-mono font-semibold tabular underline-offset-2 hover:underline"
                    >
                      {run.id}
                    </Link>
                    {run.name ? (
                      <span className="mt-0.5 block text-[13px] text-muted-foreground">
                        {run.name}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="px-4 py-3 font-mono text-muted-foreground tabular">
                    {run.batchId ? (
                      <Link
                        href={`/experimentos/${run.batchId}`}
                        className="underline-offset-2 hover:underline"
                      >
                        {run.batchId}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="px-4 py-3 font-mono tabular">{run.seed}</TableCell>
                  <TableCell className="px-4 py-3">
                    <StatusBadge
                      tone={
                        run.lifecycle === "running"
                          ? "active"
                          : run.lifecycle === "failed"
                            ? "danger"
                            : run.lifecycle === "succeeded"
                              ? "success"
                              : "neutral"
                      }
                    >
                      {lifecycleLabel(run.lifecycle)}
                    </StatusBadge>
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right font-mono tabular">
                    {formatSeconds(run.metrics.cycleTimeSimS)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-muted-foreground">
                    {formatIso(run.startedAtIso)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </AppShell>
  );
}
