"use client";

import type { PhaseId } from "@xfold/protocol";
import { Check, X, type LucideIcon } from "lucide-react";
import { cycleFill, groupOperatorSteps } from "@/lib/cycle-progress";
import { formatSeconds } from "@/lib/format";
import { STAGE_ICONS, DEFAULT_STAGE_ICON } from "@/lib/stage-icons";
import type { StageProgress } from "@/lib/types";

/**
 * Single process strip: node + connector rail per operator step.
 * Consecutive simulator phases that share a title (Rotate → Pack) collapse.
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
  const items = groupOperatorSteps(stages ?? []);

  const done = items.filter((s) => s.status === "completed" || s.status === "skipped").length;
  const running = items.some((s) => s.status === "active");
  const failed = items.some((s) => s.status === "failed");
  const fill = cycleFill(items);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="eyebrow">Cycle · {items.length} stages</h2>
        <span className="font-mono text-[11px] tabular text-muted-foreground">
          {done}/{items.length}
        </span>
      </div>
      <ol className="flex items-stretch overflow-x-auto" aria-label="Cycle stages">
        {items.map((step, index) => {
          const isSelected = selected != null && step.states.includes(selected);
          const isLast = index === items.length - 1;
          const Icon = STAGE_ICONS[step.state] ?? DEFAULT_STAGE_ICON;
          const status = step.status;
          const reached = status !== "pending";
          const passed = status === "completed" || status === "skipped";
          return (
            <li key={step.states.join("-")} className="flex min-w-24 flex-1 items-start">
              <button
                type="button"
                onClick={() => onSelect(step.state)}
                aria-pressed={isSelected}
                aria-label={`${step.label} · ${statusLabel(step)}`}
                className={`group flex w-full min-w-0 flex-col items-center gap-1.5 rounded-[var(--radius-sm)] px-1 py-1.5 text-center outline-none transition-colors duration-[var(--motion-feedback)] ease-[var(--motion-ease)] hover:bg-canvas focus-visible:ring-2 focus-visible:ring-ink ${
                  isSelected ? "bg-canvas" : ""
                }`}
              >
                <span className="flex w-full items-center">
                  {index === 0 ? (
                    <span className="h-px flex-1 bg-transparent" aria-hidden />
                  ) : (
                    <FillRail filled={reached ? 1 : 0} from="right" />
                  )}
                  <Node status={status} Icon={Icon} />
                  {isLast ? (
                    <span className="h-px flex-1 bg-transparent" aria-hidden />
                  ) : (
                    <FillRail filled={passed ? 1 : 0} from="left" />
                  )}
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
                  {step.label}
                </span>
                <span className="font-mono text-[11px] tabular text-muted-foreground">
                  {status === "completed"
                    ? formatSeconds(step.durationSimS)
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
      <div
        className="relative mt-2 h-0.5 w-full overflow-hidden bg-divider"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fill * 100)}
        aria-label="Cycle progress"
      >
        <div
          className={`absolute inset-y-0 left-0 w-full origin-left transition-transform duration-[var(--motion-progress)] ease-[var(--motion-ease)] ${
            failed && !running ? "bg-danger" : "bg-active"
          }`}
          style={{ transform: `scaleX(${fill})` }}
        />
        {running ? (
          <div
            className="rail-active absolute inset-y-0 left-0 w-full origin-left transition-transform duration-[var(--motion-progress)] ease-[var(--motion-ease)]"
            style={{ transform: `scaleX(${fill})` }}
          />
        ) : null}
      </div>
    </div>
  );
}

function FillRail({ filled, from }: { filled: number; from: "left" | "right" }) {
  return (
    <span className="relative h-px flex-1 overflow-hidden bg-divider" aria-hidden>
      <span
        className={`absolute inset-0 bg-active transition-transform duration-[var(--motion-progress)] ease-[var(--motion-ease)] ${
          from === "left" ? "origin-left" : "origin-right"
        }`}
        style={{ transform: `scaleX(${filled})` }}
      />
    </span>
  );
}

function statusLabel(stage: { status: StageProgress["status"]; durationSimS: number | null }): string {
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
