/**
 * Shared wire types for sim ↔ dashboard.
 * Binding contract: docs/INTEGRATION_CONTRACT.md
 * Keep in sync with xfold.bridge.schema (Python).
 * Verify: bash scripts/check-bridge-contract.sh
 */

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

export type PhaseId = string;

export type PhaseDefinition = {
  state: PhaseId;
  label?: string | null;
  station?: string | null;
};

export type ProcessDefinition = {
  scenario: string;
  stages: PhaseDefinition[];
  seedApplied: boolean | null;
};

export type SimOperation = {
  id: string;
  station: string | null;
  message: string;
  t: number;
  parallel: boolean;
};

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

/** Shared snapshot the sim materializes and the bridge streams to the dashboard. */
export type Telemetry = {
  t: number;
  state: PhaseId;
  cycle: number;
  flatness: number | null;
  shirt_in_bag: boolean | null;
  operation?: SimOperation | null;
  activities?: SimOperation[];
};

export const SAMPLE_TELEMETRY: Telemetry = {
  t: 0,
  state: "PICK",
  cycle: 1,
  flatness: null,
  shirt_in_bag: false,
};

// ---------------------------------------------------------------------------
// Bridge journal contract — keep in sync with xfold.bridge.schema (Python).
// See docs/BRIDGE.md.
// ---------------------------------------------------------------------------

export const COMMAND_KINDS = [
  "pause_run",
  "resume_run",
  "cancel_run",
  "pause_batch",
  "resume_batch",
  "cancel_batch",
] as const;

export type CommandKind = (typeof COMMAND_KINDS)[number];

export const JOURNAL_EVENT_TYPES = [
  "run_started",
  "state_changed",
  "metric_sample",
  "run_finished",
  "command_accepted",
  "command_rejected",
  "command_applied",
  "batch_updated",
  "log",
] as const;

export const LOG_LEVELS = ["debug", "info", "warning", "error"] as const;

export type LogLevel = (typeof LOG_LEVELS)[number];

export type JournalEventType = (typeof JOURNAL_EVENT_TYPES)[number];

export type RunLifecycle =
  | "queued"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "cancelled";

export type BatchLifecycle =
  | "queued"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "partial";

/** Foldable SKUs the operator can pick (matches `xfold.garments.CLOTH_TYPE_KEYS`). */
export const CLOTH_TYPE_KEYS = [
  "tee",
  "work_tee",
  "jersey",
  "tank",
  "polo",
  "dress",
  "custom",
] as const;

export type ClothType = (typeof CLOTH_TYPE_KEYS)[number];

/** Lay / damage / stain axes (matches `xfold.garments.CLOTH_CONDITION_KEYS`). */
export const CLOTH_CONDITION_KEYS = [
  "good",
  "damaged",
  "notgood",
  "skewed",
] as const;

export type ClothCondition = (typeof CLOTH_CONDITION_KEYS)[number];

/** How a batch row samples cloth or condition. */
export const CLOTH_MIX_KEYS = ["same", "random", "list"] as const;

export type ClothMix = (typeof CLOTH_MIX_KEYS)[number];

/** Relative draws for `clothType: "random"` / `clothMix: "random"`. 0 = never. */
export type ClothWeightMap = Partial<Record<ClothType, number>>;

/** Relative draws for `clothCondition: "random"` / `conditionMix: "random"`. */
export type ConditionWeightMap = Partial<Record<ClothCondition, number>>;

export type CatalogOption = {
  key: string;
  label: string;
  /** PNG-space silhouette for the launch preview (cut-out when ``custom``). */
  outlineUv?: number[][];
};

export type CustomDesignPayload = {
  mime: string;
  /** Raw base64, no ``data:`` prefix. Not a journal field. */
  data: string;
};

/** What the bridge actually exposes right now. */
export type BridgeCapabilities = {
  process?: ProcessDefinition | null;
  liveTelemetry: boolean;
  viewportStream: boolean;
  /** True once at least one JPEG has been published. */
  viewportReady?: boolean;
  /** UI transport hint: long-poll (primary) vs legacy mjpeg. */
  viewportTransport?: "long-poll" | "mjpeg";
  /** Server-side trajectory seek (`GET /runs/{id}/recording/frame?t=`). */
  recordingSeek?: boolean;
  startRun: boolean;
  startBatch: boolean;
  commands: Partial<Record<CommandKind, boolean>>;
  /** Live catalogue for the launch form. Empty ⇒ UI uses protocol defaults. */
  clothTypes?: CatalogOption[];
  clothConditions?: CatalogOption[];
};

export type CommandRequest = {
  clientCommandId: string;
  kind: CommandKind;
  runId?: string | null;
  batchId?: string | null;
};

export type CommandAckStatus = "accepted" | "rejected" | "applied";

type JournalEnvelope = {
  seq: number;
  tsIso: string;
  runId: string | null;
  batchId: string | null;
};

export type JournalEvent =
  | (JournalEnvelope & {
      type: "run_started";
      stages?: PhaseDefinition[];
      inputs?: Record<string, unknown>;
      driver?: string;
      seed: number;
      name: string | null;
      scenario: string;
      cycle: number;
      garment?: string | null;
      clothType?: string | null;
      clothCondition?: string | null;
      skewed?: boolean;
      customDesign?: boolean;
    })
  | (JournalEnvelope & {
      type: "state_changed";
      state: PhaseId;
      label?: string | null;
      station?: string | null;
      t: number;
      cycle: number;
    })
  | (JournalEnvelope & {
      type: "metric_sample";
      t: number;
      flatness: number | null;
      shirt_in_bag: boolean | null;
      measurements?: Record<string, number>;
      cycle: number;
      state: PhaseId;
    })
  | (JournalEnvelope & {
      type: "run_finished";
      lifecycle: Extract<
        RunLifecycle,
        "succeeded" | "failed" | "cancelled"
      >;
      reason: string | null;
      t: number;
    })
  | (JournalEnvelope & {
      type: "command_accepted" | "command_rejected" | "command_applied";
      clientCommandId: string;
      kind: CommandKind;
      reason: string | null;
    })
  | (JournalEnvelope & {
      type: "batch_updated";
      lifecycle: BatchLifecycle;
      finished: number;
      succeeded: number;
      failed: number;
      pending: number;
      activeRunId: string | null;
    })
  | (JournalEnvelope & {
      /** Free-form simulator log line for the live console (never pixels / verts). */
      type: "log";
      level: LogLevel;
      message: string;
      /** Emitter, e.g. "press-driver", "line", "sim-session". */
      source: string;
      t: number | null;
      stage?: PhaseId | null;
      operation?: string | null;
      station?: string | null;
      parallel?: boolean;
    });

export type BridgeHealth = {
  ok: true;
  version: string;
};

export type BridgeLaunchRun = {
  name?: string;
  seed: number;
  scenario?: string;
  /** Concrete type, or `"random"` to draw from the catalogue with `seed`. */
  clothType?: ClothType | "random";
  /** Concrete condition, or `"random"`. */
  clothCondition?: ClothCondition | "random";
  /** Used when `clothType` is `"random"`. Missing keys default to 1. */
  clothTypeWeights?: ClothWeightMap;
  /** Used when `clothCondition` is `"random"`. */
  clothConditionWeights?: ConditionWeightMap;
  /** Photo printed on both faces of the chosen SKU. */
  customDesign?: CustomDesignPayload;
};

export type BridgeLaunchBatch = {
  name?: string;
  count: number;
  baseSeed: number;
  seedStrategy?: "sequential";
  scenario?: string;
  /** All shirts the same type, independent draws, or draws from `clothTypes`. */
  clothMix?: ClothMix;
  clothTypes?: ClothType[];
  conditionMix?: ClothMix;
  conditions?: ClothCondition[];
  clothTypeWeights?: ClothWeightMap;
  clothConditionWeights?: ConditionWeightMap;
  customDesign?: CustomDesignPayload;
};
