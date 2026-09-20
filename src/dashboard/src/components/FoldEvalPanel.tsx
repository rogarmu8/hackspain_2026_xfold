"use client";

import { ScanSearch } from "lucide-react";
import { HoverPhoto } from "@/components/ProductShotPanel";
import { formatFoldQuality } from "@/lib/format";
import type { RunDetail } from "@/lib/types";

/** OpenCV overlay from fold_qc_cam: heatmap of wrinkles + the percent. */
export function FoldEvalPanel({ run, embed = false }: { run: RunDetail; embed?: boolean }) {
  const score = run.metrics.foldQuality ?? run.metrics.measurements?.foldQualityPct ?? null;
  const inner = (
    <>
      <HoverPhoto
        src={`/api/bridge/runs/${encodeURIComponent(run.id)}/fold-photo`}
        alt={`OpenCV fold evaluation for ${run.id}`}
        filename={`${run.id}-fold.jpg`}
        fit="contain"
      />
      <p className="shrink-0 font-mono text-sm tabular">
        {formatFoldQuality(score)}
        <span className="ml-2 text-xs text-muted-foreground">red = wrinkles · cyan = off the plates</span>
      </p>
    </>
  );

  if (embed) {
    return <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden p-4">{inner}</div>;
  }

  return (
    <aside className="flex flex-col gap-3 border border-divider bg-surface p-4">
      <header>
        <p className="eyebrow flex items-center gap-1.5">
          <ScanSearch className="size-3.5" strokeWidth={1.75} aria-hidden />
          Fold quality
        </p>
        <p className="mt-0.5 font-mono text-xs text-muted-foreground">
          opener camera · OpenCV overlay
        </p>
      </header>
      {inner}
    </aside>
  );
}
