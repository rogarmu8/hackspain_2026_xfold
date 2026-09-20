"use client";

import Link from "next/link";
import { ArrowUpRight, ClipboardList, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { NewExperimentDialog } from "@/components/NewExperimentDialog";
import { RunStatusBadges } from "@/components/RunStatusBadges";
import { formatFlatness, formatFoldQuality, formatIso, formatSeconds, DEFAULT_CLOTH_CONDITIONS, DEFAULT_CLOTH_TYPES } from "@/lib/format";
import { HoverPhoto } from "@/components/ProductShotPanel";
import type { RunDetail } from "@/lib/types";
import type { ClothCondition, ClothType } from "@xfold/protocol";

/** Compact result card for a finished run; the event log lives in the console below. */
export function RunSummaryPanel({ run, embed = false }: { run: RunDetail; embed?: boolean }) {
  const body = (
    <>
      <div className="flex shrink-0 flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="min-w-0 truncate text-[17px] font-semibold leading-tight">{run.name ?? run.id}</h3>
          <RunStatusBadges run={run} />
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
        {run.failReason ? (
          <p className="text-sm text-danger">{run.failReason}</p>
        ) : null}
        {run.hasFoldPhoto ? (
          <figure className="m-0 flex flex-col gap-1.5">
            <HoverPhoto
              src={`/api/bridge/runs/${encodeURIComponent(run.id)}/fold-photo`}
              alt={`OpenCV fold evaluation for ${run.id}`}
              filename={`${run.id}-fold.jpg`}
            />
            <figcaption className="eyebrow">Fold eval · OpenCV · warmer = more wrinkles</figcaption>
          </figure>
        ) : null}

        <dl className="grid grid-cols-3 gap-x-3 gap-y-2 border-t border-divider pt-3">
          <Metric label="duration" value={formatSeconds(run.metrics.cycleTimeSimS)} />
          <Metric label="wall t" value={formatSeconds(run.metrics.cycleTimeWallS)} />
          <Metric label="in bag" value={run.metrics.shirtInBag == null ? "not measured" : run.metrics.shirtInBag ? "yes" : "no"} />
          <Metric label="flatness pre" value={formatFlatness(run.metrics.flatnessPre)} />
          <Metric label="flatness post" value={formatFlatness(run.metrics.flatnessPost)} />
          <Metric label="fold quality" value={formatFoldQuality(run.metrics.foldQuality ?? run.metrics.measurements?.foldQualityPct)} />
          <Metric label="ended" value={formatIso(run.finishedAtIso)} />
        </dl>

        {run.metrics.measurements?.packLengthM != null ? (
          <p className="font-mono text-xs">
            Pack: {formatFlatness(run.metrics.measurements.packLengthM)} × {formatFlatness(run.metrics.measurements.packWidthM)} × {formatFlatness(run.metrics.measurements.packHeightM)}
          </p>
        ) : null}
        {run.config.inputs?.driver === "line" ? (
          <p className="text-xs text-muted-foreground">Flatness = vertex height deviation (σz). Missing the carton fails the run. Seal quality is not validated.</p>
        ) : null}
      </div>
      {run.config.inputs ? (
        <InputParams inputs={run.config.inputs} embed={embed} compact={Boolean(run.hasFoldPhoto)} />
      ) : null}

      <div className="shrink-0">
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
      </div>
    </>
  );

  if (embed) {
    return <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-4">{body}</div>;
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

function InputParams({
  inputs,
  embed,
  compact = false,
}: {
  inputs: Record<string, unknown>;
  embed: boolean;
  compact?: boolean;
}) {
  const grow = embed && !compact;
  return (
    <div className={grow ? "flex h-0 min-h-0 flex-1 flex-col overflow-hidden" : "shrink-0"}>
      <p className="shrink-0 text-xs font-semibold">Input and simulation parameters</p>
      <div className={`mt-2 min-h-0 overflow-y-auto overscroll-contain ${grow ? "flex-1" : compact ? "max-h-[min(20vh,8rem)]" : "max-h-[min(40vh,16rem)]"}`}>
        <dl className="grid grid-cols-2 gap-1 font-mono text-xs">
          {Object.entries(inputs).map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="truncate text-muted-foreground">{key}</dt>
              <dd className="truncate" title={String(value)}>{String(value)}</dd>
            </div>
          ))}
        </dl>
        {inputs.seedApplied === false ? (
          <p className="mt-2 text-xs text-muted-foreground">This run uses a fixed input: the seed does not change it.</p>
        ) : null}
      </div>
    </div>
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
