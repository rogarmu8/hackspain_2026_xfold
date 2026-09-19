"use client";

import Link from "next/link";
import { ArrowUpRight, ClipboardList, RotateCcw } from "lucide-react";
import { NewExperimentDialog } from "@/components/NewExperimentDialog";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatFlatness, formatIso, formatSeconds, lifecycleLabel, DEFAULT_CLOTH_CONDITIONS, DEFAULT_CLOTH_TYPES } from "@/lib/format";
import type { RunDetail } from "@/lib/types";
import type { ClothCondition, ClothType } from "@xfold/protocol";

/** Compact result card for a finished run; the event log lives in the console below. */
export function RunSummaryPanel({ run, embed = false }: { run: RunDetail; embed?: boolean }) {
  const tone =
    run.lifecycle === "failed" ? "danger" : run.lifecycle === "succeeded" ? "success" : "neutral";

  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <h3 className="min-w-0 truncate text-[17px] font-semibold leading-tight">{run.name ?? run.id}</h3>
        <StatusBadge tone={tone}>{run.lifecycle === "succeeded" ? "Cycle completed" : lifecycleLabel(run.lifecycle)}</StatusBadge>
      </div>
      <p className="font-mono text-xs text-muted-foreground">
        {run.id} · seed {run.seed}
        {run.config.clothType ? ` · ${run.config.clothType}` : ""}
        {run.config.clothCondition ? ` · ${run.config.clothCondition}` : ""}
        {" · "}
        {run.config.scenario}
        {run.batchId ? (
          <>
            {" · "}
            <Link href={`/experimentos/${run.batchId}`} className="inline-flex items-center gap-0.5 text-ink">
              {run.batchId} <ArrowUpRight className="size-3" aria-hidden />
            </Link>
          </>
        ) : null}
      </p>
      {run.failReason ? <p className="text-sm text-danger">{run.failReason}</p> : null}

      <dl className="grid grid-cols-3 gap-x-3 gap-y-2 border-t border-divider pt-3">
        <Metric label="sim t" value={formatSeconds(run.metrics.cycleTimeSimS)} />
        <Metric label="wall t" value={formatSeconds(run.metrics.cycleTimeWallS)} />
        <Metric label="in bag" value={run.metrics.shirtInBag == null ? "not measured" : run.metrics.shirtInBag ? "yes" : "no"} />
        <Metric label="flatness pre" value={formatFlatness(run.metrics.flatnessPre)} />
        <Metric label="flatness post" value={formatFlatness(run.metrics.flatnessPost)} />
        <Metric label="ended" value={formatIso(run.finishedAtIso)} />
      </dl>

      {run.metrics.measurements?.packLengthM != null ? (
        <p className="font-mono text-xs">
          Pack: {formatFlatness(run.metrics.measurements.packLengthM)} × {formatFlatness(run.metrics.measurements.packWidthM)} × {formatFlatness(run.metrics.measurements.packHeightM)}
        </p>
      ) : null}
      {run.config.inputs?.driver === "line" ? (
        <p className="text-xs text-muted-foreground">Flatness = vertex height deviation (σz). Finishing the sequence does not validate seal quality or containment.</p>
      ) : null}
      {run.config.inputs ? (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold">Input and simulation parameters</summary>
          <dl className="mt-2 grid grid-cols-2 gap-1 font-mono">{Object.entries(run.config.inputs).map(([key, value]) => <div key={key} className="contents"><dt className="truncate text-muted-foreground">{key}</dt><dd className="truncate" title={String(value)}>{String(value)}</dd></div>)}</dl>
          {run.config.inputs.seedApplied === false ? <p className="mt-2 text-muted-foreground">This run uses a fixed input: the seed does not change it.</p> : null}
        </details>
      ) : null}

      <NewExperimentDialog
        defaults={{
          mode: "individual",
          name: run.name ?? undefined,
          seed: run.seed,
          count: 1,
          clothMix: "same",
          clothTypes: [
            DEFAULT_CLOTH_TYPES.includes(run.config.clothType as ClothType)
              ? (run.config.clothType as ClothType)
              : "tee",
          ],
          conditionMix: "same",
          conditions: [
            DEFAULT_CLOTH_CONDITIONS.includes(run.config.clothCondition as ClothCondition)
              ? (run.config.clothCondition as ClothCondition)
              : "good",
          ],
        }}
        trigger={
          <Button type="button" variant="outline" size="sm" className="w-full">
            <RotateCcw className="size-3.5" aria-hidden />
            Repeat setup
          </Button>
        }
      />
    </>
  );

  if (embed) {
    return <div className="flex flex-col gap-3 overflow-y-auto p-4">{body}</div>;
  }

  return (
    <aside className="flex flex-col gap-3 border border-divider bg-surface p-4">
      <header>
        <p className="eyebrow flex items-center gap-1.5">
          <ClipboardList className="size-3.5" strokeWidth={1.75} aria-hidden />
          Run finished
        </p>
      </header>
      {body}
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
