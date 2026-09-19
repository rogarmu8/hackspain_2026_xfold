"use client";

import Link from "next/link";
import { ArrowUpRight, ClipboardList, RotateCcw } from "lucide-react";
import { NewExperimentDialog } from "@/components/NewExperimentDialog";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  formatFlatness,
  formatIso,
  formatSeconds,
  lifecycleLabel,
  stageLabel,
} from "@/lib/format";
import type { RunDetail } from "@/lib/types";
import type { CellState } from "@xfold/protocol";

/** Right-hand inspector for a finished run: result, metrics, config, events. */
export function RunSummaryPanel({
  run,
  selectedStage,
}: {
  run: RunDetail;
  /** Filter the event list to one stage (from the stepper). */
  selectedStage: CellState | null;
}) {
  const events = selectedStage
    ? run.events.filter((e) => e.stage === selectedStage)
    : run.events;
  const tone =
    run.lifecycle === "failed" ? "danger" : run.lifecycle === "succeeded" ? "success" : "neutral";

  return (
    <aside className="flex flex-col gap-4 border border-divider bg-surface p-4">
      <header>
        <p className="eyebrow flex items-center gap-1.5">
          <ClipboardList className="size-3.5" strokeWidth={1.75} aria-hidden />
          Ejecución finalizada
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-2">
          <h2 className="min-w-0 truncate text-[17px] font-semibold leading-tight">
            {run.name ?? run.id}
          </h2>
          <StatusBadge tone={tone}>{lifecycleLabel(run.lifecycle)}</StatusBadge>
        </div>
        <p className="mt-0.5 font-mono text-xs text-muted-foreground">
          {run.id} · seed {run.seed}
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

      <dl className="grid grid-cols-2 gap-x-3 gap-y-3 border-t border-divider pt-4">
        <Metric label="t ciclo sim" value={formatSeconds(run.metrics.cycleTimeSimS)} />
        <Metric label="t ciclo pared" value={formatSeconds(run.metrics.cycleTimeWallS)} />
        <Metric label="planitud pre" value={formatFlatness(run.metrics.flatnessPre)} />
        <Metric label="planitud post" value={formatFlatness(run.metrics.flatnessPost)} />
        <Metric
          label="en bolsa"
          value={run.metrics.shirtInBag == null ? "—" : run.metrics.shirtInBag ? "sí" : "no"}
        />
        <Metric label="escenario" value={run.config.scenario} />
        <div className="col-span-2">
          <dt className="eyebrow">inicio → fin</dt>
          <dd className="mt-1 text-xs text-muted-foreground">
            {formatIso(run.startedAtIso)} → {formatIso(run.finishedAtIso)}
          </dd>
        </div>
        {run.config.notes ? (
          <div className="col-span-2">
            <dt className="eyebrow">notas</dt>
            <dd className="mt-1 text-xs">{run.config.notes}</dd>
          </div>
        ) : null}
      </dl>

      <NewExperimentDialog
        defaults={{ mode: "individual", name: run.name ?? undefined, seed: run.seed }}
        trigger={
          <Button type="button" variant="outline" size="sm" className="w-full">
            <RotateCcw className="size-3.5" aria-hidden />
            Repetir configuración
          </Button>
        }
      />

      <section className="border-t border-divider pt-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="eyebrow">
            Eventos{selectedStage ? ` · ${stageLabel(selectedStage)}` : ""}
          </h3>
          <span className="font-mono text-[11px] tabular text-muted-foreground">{events.length}</span>
        </div>
        {events.length ? (
          <ol className="flex flex-col divide-y divide-divider">
            {events.map((event) => (
              <li key={event.id} className="py-2 text-sm">
                <p className="font-mono text-[11px] tabular text-muted-foreground">
                  t={formatSeconds(event.atSimS)}
                  {event.stage ? ` · ${stageLabel(event.stage)}` : ""}
                </p>
                <p className={event.level === "error" ? "text-danger" : ""}>{event.message}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs text-muted-foreground">Sin eventos registrados.</p>
        )}
      </section>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="eyebrow">{label}</dt>
      <dd className="mt-1 truncate font-mono text-sm tabular">{value}</dd>
    </div>
  );
}
