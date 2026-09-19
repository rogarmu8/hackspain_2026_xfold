"use client";

import type { PhaseId } from "@xfold/protocol";
import { Check, X, type LucideIcon } from "lucide-react";
import { stageLabel, formatSeconds } from "@/lib/format";
import { STAGE_ICONS, DEFAULT_STAGE_ICON } from "@/lib/stage-icons";
import type { StageProgress } from "@/lib/types";

/**
 * Single process strip: node + connector rail per stage. Status is encoded by
 * icon + rail texture + label, never by colour alone.
 */
export function StageStepper({
  stages,
  selected,
  onSelect,
}: {
  stages: StageProgress[] | null;
  selected: PhaseId | null;
  onSelect: (state: PhaseId) => void;
}) {
  const items = stages ?? [];

  const done = items.filter((s) => s.status === "completed").length;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="eyebrow">Cycle · {items.length} stages</h2>
        <span className="font-mono text-[11px] tabular text-muted-foreground">
          {done}/{items.length}
        </span>
      </div>
      <ol className="flex items-stretch overflow-x-auto" aria-label="Cycle stages">
        {items.map((stage, index) => {
          const isSelected = selected === stage.state;
          const isLast = index === items.length - 1;
          const Icon = STAGE_ICONS[stage.state] ?? DEFAULT_STAGE_ICON;
          const status = stage.status;
          return (
            <li key={stage.state} className="flex min-w-24 flex-1 items-start">
              <button
                type="button"
                onClick={() => onSelect(stage.state)}
                aria-pressed={isSelected}
                aria-label={`${stageLabel(stage.state, items)} · ${statusLabel(stage)}`}
                className={`group flex w-full min-w-0 flex-col items-center gap-1.5 rounded-[var(--radius-sm)] px-1 py-1.5 text-center outline-none transition-colors duration-[var(--motion-feedback)] ease-[var(--motion-ease)] hover:bg-canvas focus-visible:ring-2 focus-visible:ring-ink ${
                  isSelected ? "bg-canvas" : ""
                }`}
              >
                <span className="flex w-full items-center">
                  <span
                    className={`h-px flex-1 ${
                      index === 0 ? "bg-transparent" : status === "pending" ? "bg-divider" : "bg-active"
                    }`}
                    aria-hidden
                  />
                  <Node status={status} Icon={Icon} />
                  <span
                    className={`h-px flex-1 ${
                      isLast ? "bg-transparent" : status === "completed" ? "bg-active" : "bg-divider"
                    }`}
                    aria-hidden
                  />
                </span>
                <span
                  className={`truncate text-[12px] font-semibold ${
                    status === "active"
                      ? "text-active-ink"
                      : status === "failed"
                        ? "text-danger"
                        : status === "pending"
                          ? "text-muted-foreground"
                          : "text-ink"
                  }`}
                >
                  {stageLabel(stage.state, items)}
                </span>
                <span className="font-mono text-[11px] tabular text-muted-foreground">
                  {status === "completed"
                    ? formatSeconds(stage.durationSimS)
                    : status === "active"
                      ? "running"
                      : status === "failed"
                        ? "failed"
                        : "—"}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {items.some((s) => s.status === "active") ? (
        <div className="mt-2 h-0.5 w-full overflow-hidden bg-divider" aria-hidden>
          <div
            className="rail-active h-full"
            style={{ width: `${((done + 0.5) / items.length) * 100}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

function statusLabel(stage: StageProgress): string {
  if (stage.status === "completed") return `completed in ${formatSeconds(stage.durationSimS)}`;
  if (stage.status === "active") return "running";
  if (stage.status === "failed") return "failed";
  return "pending";
}

function Node({
  status,
  Icon,
}: {
  status: StageProgress["status"];
  Icon: LucideIcon;
}) {
  const base =
    "relative inline-flex size-8 shrink-0 items-center justify-center rounded-full border transition-colors duration-[var(--motion-feedback)]";
  if (status === "completed") {
    return (
      <span className={`${base} border-active bg-active text-surface`} aria-hidden>
        <Check className="size-4" strokeWidth={2.25} />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span
        className={`${base} pulse-dot border-2 border-active bg-active-surface text-active-ink`}
        aria-hidden
      >
        <Icon className="size-4" strokeWidth={1.75} />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className={`${base} border-danger bg-surface text-danger`} aria-hidden>
        <X className="size-4" strokeWidth={2.25} />
      </span>
    );
  }
  return (
    <span className={`${base} border-input bg-surface text-muted-foreground`} aria-hidden>
      <Icon className="size-4" strokeWidth={1.5} />
    </span>
  );
}
