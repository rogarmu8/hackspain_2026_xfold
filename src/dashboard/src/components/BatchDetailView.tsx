"use client";

import Link from "next/link";
import { Button } from "./ui/button";
import { lifecycleLabel } from "@/lib/format";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useDashboard } from "@/lib/dashboard-context";
import { formatCount, formatPercent } from "@/lib/format";


export function BatchDetailView({ batchId }: { batchId: string }) {
  const { getBatch, snapshot, history } = useDashboard();
  const batch = getBatch(batchId);

  if (!batch) {
    return (
      <AppShell title="Batch no encontrado">
        <div className="border border-divider bg-surface px-6 py-10">
          <p className="text-sm text-muted-foreground">
            No hay datos para <span className="font-mono">{batchId}</span>.
          </p>
          <Button asChild variant="outline"><Link href="/experimentos">Volver a experimentos</Link></Button>
        </div>
      </AppShell>
    );
  }

  const successRate = formatPercent(
    batch.succeeded,
    batch.succeeded + batch.failed,
  );

  const runs = history.filter((r) => r.batchId === batch.id);

  return (
    <AppShell
      title={batch.id}
      description={batch.name}
      actions={
        <StatusBadge
          tone={batch.lifecycle === "running" ? "active" : "neutral"}
        >
          {lifecycleLabel(batch.lifecycle)}
        </StatusBadge>
      }
    >
      {snapshot.provenance === "fixture" ? (
        <p className="mb-4 text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
          Datos de ejemplo
        </p>
      ) : null}

      <section className="mb-6 grid gap-4 border border-divider bg-surface p-6 sm:grid-cols-3">
        <div>
          <p className="text-[13px] text-muted-foreground">Finalizadas / total</p>
          <p className="mt-1 font-mono text-lg tabular">
            {formatCount(batch.finished)}/{formatCount(batch.total)}
          </p>
        </div>
        <div>
          <p className="text-[13px] text-muted-foreground">Correctas / fallidas</p>
          <p className="mt-1 font-mono text-lg tabular">
            {formatCount(batch.succeeded)} / {formatCount(batch.failed)}
          </p>
        </div>
        <div>
          <p className="text-[13px] text-muted-foreground">Tasa de éxito</p>
          <p className="mt-1 font-mono text-lg tabular">{successRate ?? "—"}</p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            correctas / (correctas + fallidas); excluye pendientes y canceladas
          </p>
        </div>
      </section>

      <section className="border border-divider bg-surface">
        <div className="border-b border-divider px-4 py-3">
          <h2 className="text-lg font-semibold">Ejecuciones del batch</h2>
        </div>
        {runs.length === 0 && batch.queuePreview.length === 0 ? (
          <p className="px-4 py-6 text-sm text-muted-foreground">Sin ejecuciones listadas.</p>
        ) : (
          <ul className="divide-y divide-divider">
            {batch.activeRunId ? (
              <li className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                <Link
                  href={`/historial/${batch.activeRunId}`}
                  className="font-mono font-semibold tabular underline-offset-2 hover:underline"
                >
                  {batch.activeRunId}
                </Link>
                <StatusBadge tone="active">{history.find((r) => r.id === batch.activeRunId)?.lifecycle === "paused" ? "En pausa" : "Activa"}</StatusBadge>
              </li>
            ) : null}
            {runs
              .filter((r) => r.id !== batch.activeRunId)
              .map((run) => (
                <li
                  key={run.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm"
                >
                  <Link
                    href={`/historial/${run.id}`}
                    className="font-mono font-semibold tabular underline-offset-2 hover:underline"
                  >
                    {run.id}
                  </Link>
                  <span className="text-muted-foreground">Semilla {run.seed}</span>
                  <StatusBadge
                    tone={run.lifecycle === "failed" ? "danger" : "neutral"}
                  >
                    {lifecycleLabel(run.lifecycle)}
                  </StatusBadge>
                </li>
              ))}
            {batch.queuePreview.filter((item) => !runs.some((run) => run.id === item.runId)).map((item) => (
              <li
                key={item.runId}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm"
              >
                <span className="font-mono tabular text-muted-foreground">{item.runId}</span>
                <span className="text-muted-foreground">Semilla {item.seed}</span>
                <StatusBadge tone="pending">En cola</StatusBadge>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="mt-6 text-sm">
        <Link
          href="/experimentos"
          className="font-semibold underline-offset-2 hover:underline"
        >
          ← Experimentos
        </Link>
      </p>
    </AppShell>
  );
}
