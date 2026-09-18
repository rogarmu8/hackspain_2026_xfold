export const CELL_STATES = [
  "PICK",
  "SPREAD",
  "PRESS",
  "FOLD",
  "CHUTE",
  "BAG",
  "RESET",
] as const;

export type CellState = (typeof CELL_STATES)[number];

/** Productive cycle order (RESET is lifecycle-only, not a fold step). */
export const PRODUCTIVE_CYCLE = [
  "PICK",
  "SPREAD",
  "PRESS",
  "FOLD",
  "CHUTE",
  "BAG",
] as const satisfies readonly CellState[];

/** Spanish labels for the OpenArm → ninja fold → bag chute cell. */
export const CELL_STAGE_LABELS: Record<CellState, string> = {
  PICK: "Recogida",
  SPREAD: "Tensado",
  PRESS: "Prensado",
  FOLD: "Plegado ninja",
  CHUTE: "Tolva",
  BAG: "Embolsado",
  RESET: "Reinicio",
};

/** Shared snapshot the sim will later stream to the dashboard. */
export type Telemetry = {
  t: number;
  state: CellState;
  cycle: number;
  flatness: number | null;
  shirt_in_bag: boolean;
};

export const SAMPLE_TELEMETRY: Telemetry = {
  t: 0,
  state: "PICK",
  cycle: 1,
  flatness: null,
  shirt_in_bag: false,
};
