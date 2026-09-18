"use client";

import Link from "next/link";
import { Button } from "./ui/button";
import { lifecycleLabel } from "@/lib/format";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { StageStepper } from "@/components/StageStepper";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useDashboard } from "@/lib/dashboard-context";
import {
  formatFlatness,
  formatIso,
  formatSeconds,
  stageLabel,
} from "@/lib/format";
import type { CellState } from "@xfold/protocol";

export function RunDetailView({ runId }: { runId: string }) {
  const { getRun, snapshot } = useDashboard();
  const run = getRun(runId);
  const [tab, setTab] = useState<"events" | "metrics" | "config">("events");
  const [selectedStage, setSelectedStage] = useState<CellState | null>(null);

  if (!run) {
    return (
      <AppShell title="Ejecución no encontrada">
        <div className="border border-divider bg-surface px-6 py-10">
          <p className="text-sm text-muted-foreground">
            No hay datos para <span className="font-mono">{runId}</span>. Puede
            ser un ID desconocido o un origen sin persistencia.
          </p>
          <Button asChild variant="outline"><Link href="/historial">Volver al historial</Link></Button>
        </div>
      </AppShell>
    );
  }

  const events =
    selectedStage == null
      ? run.events
      : run.events.filter((e) => e.stage === selectedStage);

  return (
    <AppShell
      title={run.id}
      description={
        run.name
          ? `${run.name} · semilla ${run.seed}`
          : `Semilla ${run.seed}${run.batchId ? ` · ${run.batchId}` : ""}`
      }
      actions={
        <>
          <StatusBadge
            tone={
              run.lifecycle === "running"
                ? "active"
                : run.lifecycle === "failed"
                  ? "danger"
                  : "neutral"
            }
          >
            {lifecycleLabel(run.lifecycle)}
          </StatusBadge>
          <Button asChild variant="default"><Link href="/experimentos/nuevo">Repetir configuración</Link></Button>
        </>
      }
    >
      {snapshot.provenance === "fixture" ? (
        <p className="mb-4 text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
          Datos de ejemplo
        </p>
      ) : null}

      <section className="mb-6 grid gap-4 border border-divider bg-surface p-6 sm:grid-cols-3">
        <div>
          <p className="text-[13px] text-muted-foreground">Resultado</p>
          <p className="mt-1 font-semibold">
            {run.lifecycle === "succeeded"
              ? "Correcta"
              : run.lifecycle === "failed"
                ? "Fallida"
                : lifecycleLabel(run.lifecycle)}
          </p>
          {run.failReason ? (
            <p className="mt-1 text-sm text-danger">{run.failReason}</p>
          ) : null}
        </div>
        <div>
          <p className="text-[13px] text-muted-foreground">Duración sim / pared</p>
          <p className="mt-1 font-mono tabular">
            {formatSeconds(run.metrics.cycleTimeSimS)} /{" "}
            {formatSeconds(run.metrics.cycleTimeWallS)}
          </p>
        </div>
        <div>
          <p className="text-[13px] text-muted-foreground">Inicio → fin</p>
          <p className="mt-1 text-sm">
            {formatIso(run.startedAtIso)} → {formatIso(run.finishedAtIso)}
          </p>
        </div>
      </section>

      <section className="mb-6 border border-divider bg-surface p-4">
        <h2 className="mb-3 text-lg font-semibold">Etapas</h2>
        <StageStepper
          stages={run.stages}
          selected={selectedStage}
          onSelect={(state) =>
            setSelectedStage((prev) => (prev === state ? null : state))
          }
        />
      </section>

      <div className="border border-divider bg-surface">
        <div className="flex gap-1 border-b border-divider px-2" role="tablist">
          {(
            [
              ["events", "Eventos"],
              ["metrics", "Métricas"],
              ["config", "Configuración"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={`h-11 px-4 text-sm font-semibold ${
                tab === id
                  ? "border-b-2 border-ink text-ink"
                  : "text-muted-foreground"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {tab === "events" ? (
            events.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sin eventos en este filtro.</p>
            ) : (
              <ol className="flex flex-col gap-3">
                {events.map((event) => (
                  <li key={event.id} className="text-sm">
                    <span className="font-mono tabular text-muted-foreground">
                      t={formatSeconds(event.atSimS)}
                    </span>
                    {event.stage ? (
                      <span className="ml-2 text-muted-foreground">
                        {stageLabel(event.stage)}
                      </span>
                    ) : null}
                    <p
                      className={
                        event.level === "error" ? "text-danger" : "text-ink"
                      }
                    >
                      {event.message}
                    </p>
                  </li>
                ))}
              </ol>
            )
          ) : null}

          {tab === "metrics" ? (
            <dl className="grid gap-4 sm:grid-cols-2">
              <Metric
                label="Planitud pre-prensa"
                value={formatFlatness(run.metrics.flatnessPre)}
                absent={run.metrics.flatnessPre == null}
              />
              <Metric
                label="Planitud post-prensa"
                value={formatFlatness(run.metrics.flatnessPost)}
                absent={run.metrics.flatnessPost == null}
              />
              <Metric
                label="Camiseta en bolsa"
                value={
                  run.metrics.shirtInBag == null
                    ? "—"
                    : run.metrics.shirtInBag
                      ? "sí"
                      : "no"
                }
                absent={run.metrics.shirtInBag == null}
              />
              <Metric
                label="t ciclo simulado"
                value={formatSeconds(run.metrics.cycleTimeSimS)}
                absent={run.metrics.cycleTimeSimS == null}
              />
              <Metric
                label="t ciclo pared"
                value={formatSeconds(run.metrics.cycleTimeWallS)}
                absent={run.metrics.cycleTimeWallS == null}
              />
            </dl>
          ) : null}

          {tab === "config" ? (
            <dl className="grid gap-4 sm:grid-cols-2 text-sm">
              <div>
                <dt className="text-muted-foreground">Nombre</dt>
                <dd>{run.config.name ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Semilla</dt>
                <dd className="font-mono tabular">{run.config.seed}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Escenario</dt>
                <dd className="font-mono">{run.config.scenario}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Notas</dt>
                <dd>{run.config.notes ?? "—"}</dd>
              </div>
              <p className="sm:col-span-2 text-[13px] text-muted-foreground">
                «Repetir configuración» crea otra ejecución; no modifica esta ni
                promete el mismo resultado.
              </p>
            </dl>
          ) : null}
        </div>
      </div>

      <p className="mt-6 text-sm">
        <Link href="/historial" className="font-semibold underline-offset-2 hover:underline">
          ← Historial
        </Link>
        {run.batchId ? (
          <>
            {" · "}
            <Link
              href={`/experimentos/${run.batchId}`}
              className="font-semibold underline-offset-2 hover:underline"
            >
              Batch {run.batchId}
            </Link>
          </>
        ) : null}
      </p>
    </AppShell>
  );
}

function Metric({
  label,
  value,
  absent,
}: {
  label: string;
  value: string;
  absent?: boolean;
}) {
  return (
    <div>
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd
        className="mt-1 font-mono text-base tabular"
        title={absent ? "Dato no disponible" : undefined}
      >
        {value}
      </dd>
    </div>
  );
}
