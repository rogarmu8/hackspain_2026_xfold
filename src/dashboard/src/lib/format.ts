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

export function stageLabel(state: string, stages?: readonly PhaseDefinition[]): string {
  return stages?.find((s) => s.state === state)?.label ?? CELL_STAGE_LABELS[state as CellState] ?? state;
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
  good: "Clean, square on the belt",
  damaged: "Torn",
  notgood: "Stained",
  skewed: "Flat, rotated (seed)",
};

export function clothTypeLabel(key: string): string {
  return CLOTH_TYPE_LABELS[key as ClothType] ?? key;
}

export function clothConditionLabel(key: string): string {
  return CLOTH_CONDITION_LABELS[key as ClothCondition] ?? key;
}

export const DEFAULT_CLOTH_TYPES: ClothType[] = [...CLOTH_TYPE_KEYS];
export const DEFAULT_CLOTH_CONDITIONS: ClothCondition[] = [...CLOTH_CONDITION_KEYS];
