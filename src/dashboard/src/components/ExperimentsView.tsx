"use client";

import Link from "next/link";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/table";
import { lifecycleLabel } from "@/lib/format";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { NewExperimentDialog } from "@/components/NewExperimentDialog";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useDashboard } from "@/lib/dashboard-context";
import { formatCount, formatIso, formatPercent } from "@/lib/format";

export function ExperimentsView() {
  const { experiments, snapshot } = useDashboard();
  const [filter, setFilter] = useState<"all" | "batch" | "run">("all");

  const rows = useMemo(
    () =>
      experiments.filter((item) =>
        filter === "all" ? true : item.kind === filter,
      ),
    [experiments, filter],
  );

  return (
    <AppShell
      title="Experimentos"
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
        <p className="mb-4 text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
          Datos de ejemplo
        </p>
      ) : null}

      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Filtro">
        {(
          [
            ["all", "Todos"],
            ["batch", "Batches"],
            ["run", "Individuales"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={filter === id}
            onClick={() => setFilter(id)}
            className={`h-9 rounded-[var(--radius-sm)] border px-3 text-sm font-semibold ${
              filter === id
                ? "border-ink bg-surface"
                : "border-divider text-muted-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {rows.length === 0 ? (
        <div className="border border-divider bg-surface px-6 py-10">
          <h2 className="text-lg font-semibold">Sin experimentos</h2>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">
            Todavía no hay corridas registradas. El simulador no persiste
            experimentos; este listado usa el adaptador de ejemplo cuando está
            activo.
          </p>
          <NewExperimentDialog />
        </div>
      ) : (
        <div className="overflow-x-auto border border-divider bg-surface">
          <Table className="w-full min-w-[640px] border-collapse text-left text-sm">
            <TableHeader>
              <TableRow className="border-b border-divider text-[13px] text-muted-foreground">
                <TableHead className="px-4 py-3 font-semibold">ID</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Tipo</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Título</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Estado</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Resumen</TableHead>
                <TableHead className="px-4 py-3 font-semibold">Inicio</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((item) => (
                <TableRow key={`${item.kind}-${item.id}`} className="border-b border-divider">
                  <TableCell className="px-4 py-3">
                    <Link
                      href={
                        item.kind === "batch"
                          ? `/experimentos/${item.id}`
                          : `/historial/${item.id}`
                      }
                      className="font-mono font-semibold tabular underline-offset-2 hover:underline"
                    >
                      {item.id}
                    </Link>
                  </TableCell>
                  <TableCell className="px-4 py-3 text-muted-foreground">
                    {item.kind === "batch" ? "Batch" : "Individual"}
                  </TableCell>
                  <TableCell className="px-4 py-3">{item.title}</TableCell>
                  <TableCell className="px-4 py-3">
                    <StatusBadge
                      tone={
                        item.lifecycle === "running"
                          ? "active"
                          : item.lifecycle === "failed"
                            ? "danger"
                            : "neutral"
                      }
                    >
                      {lifecycleLabel(item.lifecycle)}
                    </StatusBadge>
                  </TableCell>
                  <TableCell className="px-4 py-3 tabular text-muted-foreground">
                    {item.kind === "batch"
                      ? `${formatCount(item.finished)}/${formatCount(item.total)} · éxito ${
                          formatPercent(
                            item.succeeded,
                            item.succeeded + item.failed,
                          ) ?? "—"
                        }`
                      : `semilla ${item.seed}`}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-muted-foreground">
                    {formatIso(item.startedAtIso)}
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
