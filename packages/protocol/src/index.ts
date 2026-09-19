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
] as const;

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

/** What the bridge actually exposes right now. */
export type BridgeCapabilities = {
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
      seed: number;
      name: string | null;
      scenario: string;
      cycle: number;
    })
  | (JournalEnvelope & {
      type: "state_changed";
      state: CellState;
      t: number;
      cycle: number;
    })
  | (JournalEnvelope & {
      type: "metric_sample";
      t: number;
      flatness: number | null;
      shirt_in_bag: boolean;
      cycle: number;
      state: CellState;
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
    });

export type BridgeHealth = {
  ok: true;
  version: string;
};

export type BridgeLaunchRun = {
  name?: string;
  seed: number;
  scenario?: string;
};

export type BridgeLaunchBatch = {
  name?: string;
  count: number;
  baseSeed: number;
  seedStrategy?: "sequential";
  scenario?: string;
};
