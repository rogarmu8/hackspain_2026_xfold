"use client";

import Link from "next/link";
import { ArrowUpRight, ClipboardList, RotateCcw } from "lucide-react";
import { NewExperimentDialog } from "@/components/NewExperimentDialog";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatFlatness, formatIso, formatSeconds, lifecycleLabel } from "@/lib/format";
import type { RunDetail } from "@/lib/types";

/** Compact result card for a finished run; the event log lives in the console below. */
export function RunSummaryPanel({ run }: { run: RunDetail }) {
  const tone =
    run.lifecycle === "failed" ? "danger" : run.lifecycle === "succeeded" ? "success" : "neutral";

  return (
    <aside className="flex flex-col gap-3 border border-divider bg-surface p-4">
      <header>
        <p className="eyebrow flex items-center gap-1.5">
          <ClipboardList className="size-3.5" strokeWidth={1.75} aria-hidden />
          Ejecución finalizada
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-2">
          <h2 className="min-w-0 truncate text-[17px] font-semibold leading-tight">{run.name ?? run.id}</h2>
          <StatusBadge tone={tone}>{run.lifecycle === "succeeded" ? "Ciclo completado" : lifecycleLabel(run.lifecycle)}</StatusBadge>
        </div>
        <p className="mt-0.5 font-mono text-xs text-muted-foreground">
          {run.id} · seed {run.seed} · {run.config.scenario}
          {run.batchId ? (
            <>
              {" · "}
              <Link href={`/experimentos/${run.batchId}`} className="inline-flex items-center gap-0.5 text-ink">
                {run.batchId} <ArrowUpRight className="size-3" aria-hidden />
              </Link>
            </>
          ) : null}
        </p>
        {run.failReason ? <p className="mt-2 text-sm text-danger">{run.failReason}</p> : null}
      </header>

      <dl className="grid grid-cols-3 gap-x-3 gap-y-2 border-t border-divider pt-3">
        <Metric label="t sim" value={formatSeconds(run.metrics.cycleTimeSimS)} />
        <Metric label="t pared" value={formatSeconds(run.metrics.cycleTimeWallS)} />
        <Metric label="en bolsa" value={run.metrics.shirtInBag == null ? "no medido" : run.metrics.shirtInBag ? "sí" : "no"} />
        <Metric label="planitud pre" value={formatFlatness(run.metrics.flatnessPre)} />
        <Metric label="planitud post" value={formatFlatness(run.metrics.flatnessPost)} />
        <Metric label="fin" value={formatIso(run.finishedAtIso)} />
      </dl>

      {run.metrics.measurements?.packLengthM != null ? (
        <p className="font-mono text-xs">
          Paquete: {formatFlatness(run.metrics.measurements.packLengthM)} × {formatFlatness(run.metrics.measurements.packWidthM)} × {formatFlatness(run.metrics.measurements.packHeightM)}
        </p>
      ) : null}
      {run.config.inputs?.driver === "line" ? (
        <p className="text-xs text-muted-foreground">Planitud = desviación de altura de vértices (σz). Completar la secuencia no valida la calidad del sellado ni la contención.</p>
      ) : null}
      {run.config.inputs ? (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold">Entrada y parámetros de simulación</summary>
          <dl className="mt-2 grid grid-cols-2 gap-1 font-mono">{Object.entries(run.config.inputs).map(([key, value]) => <div key={key} className="contents"><dt className="truncate text-muted-foreground">{key}</dt><dd className="truncate" title={String(value)}>{String(value)}</dd></div>)}</dl>
          {run.config.inputs.seedApplied === false ? <p className="mt-2 text-muted-foreground">Esta línea no utiliza la seed para variar la entrada.</p> : null}
        </details>
      ) : null}

      <NewExperimentDialog
        defaults={{ mode: "individual", name: run.name ?? undefined, seed: run.seed }}
        trigger={
          <Button type="button" variant="outline" size="sm" className="w-full">
            <RotateCcw className="size-3.5" aria-hidden />
            Repetir configuración
          </Button>
        }
      />
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="eyebrow">{label}</dt>
      <dd className="mt-0.5 truncate font-mono text-[13px] tabular" title={value}>{value}</dd>
    </div>
  );
}
