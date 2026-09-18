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
