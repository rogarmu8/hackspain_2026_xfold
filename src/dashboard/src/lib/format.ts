import {
  CELL_STAGE_LABELS,
  CLOTH_CONDITION_KEYS,
  CLOTH_TYPE_KEYS,
  type CellState,
  type PhaseDefinition,
  type ClothCondition,
  type ClothType,
} from "@xfold/protocol";

/** Manual en-US formatting — avoids Intl SSR/client drift. */
function formatEn(value: number, fractionDigits: number): string {
  const fixed = value.toFixed(fractionDigits);
  const [intPart, frac] = fixed.split(".");
  const withSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  if (!frac || fractionDigits === 0) return withSep;
  const trimmed = frac.replace(/0+$/, "");
  return trimmed ? `${withSep}.${trimmed}` : withSep;
}

/** Line phases that are not in the legacy CellState union. */
const LINE_STEP_LABELS: Record<string, string> = {
  LOAD: "Rotate",
  TO_PRESS: "Press",
  TO_QC: "Press",
  PHOTO: "Press",
  SORT: "Press",
  TO_FOLDER: "Fold",
  INSERT: "Bag",
  TO_SEAL: "Pack",
  SEAL: "Pack",
  TO_CARTON: "Pack",
  DONE: "Pack",
};

export function stageLabel(state: string, stages?: readonly PhaseDefinition[]): string {
  return (
    stages?.find((s) => s.state === state)?.label ??
    CELL_STAGE_LABELS[state as CellState] ??
    LINE_STEP_LABELS[state] ??
    state
  );
}

/** Operator-facing cycle title. Known stations stay Rotate / Press / Fold / Bag / Pack. */
export function operatorStepTitle(state: string, stages?: readonly PhaseDefinition[]): string {
  return (
    CELL_STAGE_LABELS[state as CellState] ??
    LINE_STEP_LABELS[state] ??
    stages?.find((s) => s.state === state)?.label ??
    state
  );
}

export function formatPercent(
  numerator: number,
  denominator: number,
): string | null {
  if (denominator <= 0) return null;
  return `${formatEn((numerator / denominator) * 100, 1)} %`;
}

export function formatSeconds(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${formatEn(value, 1)} s`;
}

export function formatFlatness(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${formatEn(value * 1000, 2)} mm`;
}

/** Deterministic UTC stamp — avoids SSR/client locale hydration drift. */
export function formatIso(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  const ss = String(date.getUTCSeconds()).padStart(2, "0");
  return `${y}-${m}-${d} ${hh}:${mm}:${ss} UTC`;
}

export function formatCount(value: number | null | undefined): string {
  if (value == null) return "—";
  return formatEn(value, 0);
}

export function absentTitle(reason: string): string {
  return reason;
}

export function lifecycleLabel(value: string): string {
  return ({ running: "Running", paused: "Paused", succeeded: "Succeeded", failed: "Failed", cancelled: "Cancelled", queued: "Queued", partial: "Partial", completed: "Completed", active: "Active", pending: "Pending", skipped: "Skipped" } as Record<string, string>)[value] ?? value;
}

export type RunResultSource = {
  lifecycle: string;
  clothCondition?: string | null;
  skewed?: boolean | null;
  failReason?: string | null;
  config?: { clothCondition?: string | null; skewed?: boolean | null };
};

function runCondition(run: RunResultSource): string | null {
  return run.clothCondition ?? run.config?.clothCondition ?? null;
}

function runSkewed(run: RunResultSource): boolean {
  if (run.skewed != null) return Boolean(run.skewed);
  if (run.config?.skewed != null) return Boolean(run.config.skewed);
  return runCondition(run) === "skewed";
}

/** Process status: did the line do the right thing with this garment. */
export function runProcessLabel(run: RunResultSource): string {
  return lifecycleLabel(run.lifecycle);
}

export function runProcessTone(run: RunResultSource): "active" | "neutral" | "danger" | "success" | "pending" {
  if (run.lifecycle === "running" || run.lifecycle === "paused") return "active";
  if (run.lifecycle === "succeeded") return "success";
  if (run.lifecycle === "failed") return "danger";
  if (run.lifecycle === "queued") return "pending";
  return "neutral";
}

/** Garment mark: Clean / Rotated / Stained / Torn (and combinations). */
export function runGarmentLabel(run: RunResultSource): string | null {
  const condition = runCondition(run);
  const skewed = runSkewed(run);
  const parts: string[] = [];
  if (condition && condition !== "skewed") {
    parts.push(clothConditionLabel(condition));
  }
  if (skewed) {
    parts.push(clothConditionLabel("skewed"));
  } else if (condition === "skewed") {
    parts.push(clothConditionLabel("skewed"));
  }
  if (!parts.length && condition) {
    parts.push(clothConditionLabel(condition));
  }
  return parts.length ? parts.join(" · ") : null;
}

export function runGarmentTone(run: RunResultSource): "active" | "neutral" | "danger" | "success" | "pending" {
  const label = runGarmentLabel(run);
  if (!label) return "neutral";
  if (label.includes("Stained") || label.includes("Torn")) return "danger";
  return "neutral";
}

/** Console / single-line form: "Succeeded · Stained". */
export function runResultLabel(run: RunResultSource): string {
  const process = runProcessLabel(run);
  if (run.lifecycle === "running" || run.lifecycle === "paused" || run.lifecycle === "queued") {
    return process;
  }
  const garment = runGarmentLabel(run);
  return garment ? `${process} · ${garment}` : process;
}

export function runResultTone(run: RunResultSource): "active" | "neutral" | "danger" | "success" | "pending" {
  return runProcessTone(run);
}

const CLOTH_TYPE_LABELS: Record<ClothType, string> = {
  tee: "T-shirt",
  work_tee: "Work tee",
  jersey: "Jersey",
  tank: "Tank",
  polo: "Polo",
  dress: "Pinafore",
  custom: "Custom",
};

const CLOTH_CONDITION_LABELS: Record<ClothCondition, string> = {
  good: "Clean",
  damaged: "Torn",
  notgood: "Stained",
  skewed: "Rotated",
};

export function clothTypeLabel(key: string): string {
  return CLOTH_TYPE_LABELS[key as ClothType] ?? key;
}

export function clothConditionLabel(key: string): string {
  return CLOTH_CONDITION_LABELS[key as ClothCondition] ?? key;
}

export const DEFAULT_CLOTH_TYPES: ClothType[] = [...CLOTH_TYPE_KEYS];
export const DEFAULT_CLOTH_CONDITIONS: ClothCondition[] = [...CLOTH_CONDITION_KEYS];
