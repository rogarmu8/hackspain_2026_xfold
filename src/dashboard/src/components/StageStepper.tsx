"use client";

import { PRODUCTIVE_CYCLE, type CellState } from "@xfold/protocol";
import { stageLabel, formatSeconds } from "@/lib/format";
import type { StageProgress } from "@/lib/types";

export function StageStepper({
  stages,
  selected,
  onSelect,
}: {
  stages: StageProgress[] | null;
  selected: CellState | null;
  onSelect: (state: CellState) => void;
}) {
  const items =
    stages ??
    PRODUCTIVE_CYCLE.map((state) => ({
      state,
      status: "pending" as const,
      startedAtSimS: null,
      durationSimS: null,
    }));

  return (
    <ol className="flex flex-wrap items-stretch gap-2" aria-label="Etapas del ciclo">
      {items.map((stage, index) => {
        const isSelected = selected === stage.state;
        const label = stageLabel(stage.state);
        return (
          <li key={stage.state} className="min-w-[6rem] flex-1">
            <button
              type="button"
              onClick={() => onSelect(stage.state)}
              aria-pressed={isSelected}
              style={isSelected ? { outline: "2px solid var(--color-ink)", outlineOffset: 2 } : undefined}
              className={`flex h-full w-full flex-col gap-1 rounded-[var(--radius-sm)] border px-2 py-3 text-left transition-colors duration-[120ms] ease-out ${
                stage.status === "active"
                  ? "border-active bg-active-surface text-active-ink"
                  : stage.status === "failed"
                    ? "border-danger text-danger"
                    : isSelected
                      ? "border-ink bg-surface"
                      : "border-divider bg-surface text-ink"
              }`}
            >
              <span className="flex items-center gap-2 text-[13px] font-semibold">
                <StageGlyph status={stage.status} index={index + 1} />
                {label}
              </span>
              <span className="tabular text-[12px] text-muted-foreground">
                {stage.status === "active"
                  ? "En curso"
                  : stage.status === "completed"
                    ? formatSeconds(stage.durationSimS)
                    : stage.status === "failed"
                      ? "Fallida"
                      : "Pendiente"}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function StageGlyph({
  status,
  index,
}: {
  status: StageProgress["status"];
  index: number;
}) {
  if (status === "completed") {
    return (
      <span className="inline-flex size-5 items-center justify-center rounded-full bg-active text-[11px] text-surface" aria-hidden>
        ✓
      </span>
    );
  }
  if (status === "active") {
    return (
      <span
        className="inline-flex size-5 items-center justify-center rounded-full border-2 border-active text-[10px] font-bold"
        aria-hidden
      >
        ●
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex size-5 items-center justify-center rounded-full border border-danger text-[11px]" aria-hidden>
        ×
      </span>
    );
  }
  return (
    <span className="inline-flex size-5 items-center justify-center rounded-full border border-input text-[11px] text-muted-foreground tabular" aria-hidden>
      {index}
    </span>
  );
}
