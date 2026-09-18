import Link from "next/link";
import { CellSchematic } from "./CellSchematic";
import type { ReactNode } from "react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatFlatness, formatSeconds, stageLabel } from "@/lib/format";
import type { DataProvenance, RunDetail } from "@/lib/types";

export function SimulationViewport({
  run,
  provenance,
  streamAvailable,
}: {
  run: RunDetail | null;
  provenance: DataProvenance;
  streamAvailable: boolean;
}) {
  const live = Boolean(run && run.lifecycle === "running" && streamAvailable);
  const title = run
    ? `${run.id}${run.seed != null ? ` · Semilla ${run.seed}` : ""}`
    : "Sin ejecución activa";

  return (
    <section className="flex min-h-0 flex-col border border-divider bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-divider px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-mono text-sm font-semibold tabular">{title}</h2>
          {live ? (
            <StatusBadge tone="active">En directo</StatusBadge>
          ) : run?.lifecycle === "running" ? (
            <StatusBadge tone="neutral">Telemetría sin imagen</StatusBadge>
          ) : run ? (
            <StatusBadge tone="neutral">Revisión</StatusBadge>
          ) : null}
        </div>
        {provenance === "fixture" ? (
          <span className="text-[12px] font-semibold tracking-wide text-muted-foreground uppercase">
            Datos de ejemplo
          </span>
        ) : null}
      </div>

      <div className="relative min-h-[220px] bg-viewport text-surface viewport-focus">
        {!run ? (
          <Placeholder
            title="Sin ejecución activa"
            body="Lanza un experimento para supervisar la celda OpenArm. La vista aparecerá cuando el simulador publique imagen."
          />
        ) : streamAvailable ? (
          <Placeholder
            title="Flujo de imagen"
            body="El simulador aún no publica frames al dashboard."
          />
        ) : (
          <Placeholder
            title="Celda OpenArm"
            body="Esquema ilustrativo · sin señal de cámara"
          >
            <CellSchematic stage={run.currentState} />
            {run.telemetry ? (
              <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-3 text-left sm:grid-cols-5">
                <Metric label="Fase" value={stageLabel(run.telemetry.state)} />
                <Metric label="Ciclo" value={String(run.telemetry.cycle)} mono />
                <Metric
                  label="Planitud"
                  value={formatFlatness(run.telemetry.flatness)}
                  mono
                  title={
                    run.telemetry.flatness == null
                      ? "Planitud aún no medida en esta fase"
                      : undefined
                  }
                />
                <Metric
                  label="En bolsa"
                  value={run.telemetry.shirt_in_bag ? "sí" : "no"}
                />
                <Metric
                  label="t sim"
                  value={formatSeconds(run.telemetry.t)}
                  mono
                />
              </dl>
            ) : (
              <p className="mt-4 text-[13px] text-surface/70">
                Sin muestra de telemetría para esta ejecución.
              </p>
            )}
          </Placeholder>
        )}

        <div className="pointer-events-none flex justify-between gap-3 bg-viewport/90 px-4 py-2 text-[12px] text-surface/80">
          <span>OpenArm v2 · 7-DOF × 2</span>
          <span className="tabular">
            {run?.currentState ? stageLabel(run.currentState) : "—"}
          </span>
        </div>
      </div>

      {run ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-divider px-4 py-3 text-sm">
          <p className="text-muted-foreground">
            {run.lifecycle === "running"
              ? `Fase actual: ${run.currentState ? stageLabel(run.currentState) : "—"}`
              : lifecycleCopy(run)}
          </p>
          <Link
            href={`/historial/${run.id}`}
            className="font-semibold text-ink underline-offset-2 hover:underline"
          >
            Ver detalle de ejecución
          </Link>
        </div>
      ) : null}
    </section>
  );
}

function lifecycleCopy(run: RunDetail): string {
  if (run.lifecycle === "succeeded") return "Ejecución finalizada correctamente";
  if (run.lifecycle === "failed")
    return run.failReason ?? "Ejecución fallida";
  if (run.lifecycle === "cancelled") return "Ejecución cancelada";
  if (run.lifecycle === "paused") return "Ejecución en pausa";
  return "Ejecución en cola";
}

function Placeholder({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start justify-center px-5 py-5">
      <p className="text-base font-semibold text-surface">{title}</p>
      <p className="mt-2 max-w-md text-sm text-surface/70">{body}</p>
      {children}
    </div>
  );
}

function Metric({
  label,
  value,
  mono,
  title,
}: {
  label: string;
  value: string;
  mono?: boolean;
  title?: string;
}) {
  return (
    <div title={title}>
      <dt className="text-[11px] tracking-wide text-surface/70 uppercase">
        {label}
      </dt>
      <dd className={`mt-0.5 text-sm text-surface ${mono ? "font-mono tabular" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
