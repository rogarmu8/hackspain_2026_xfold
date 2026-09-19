import type {
  PhaseId,
  PhaseDefinition,
  ProcessDefinition,
  LogLevel,
  ClothCondition,
  ClothMix,
  ClothType,
  ClothWeightMap,
  ConditionWeightMap,
  CatalogOption,
  CustomDesignPayload,
  Telemetry,
} from "@xfold/protocol";

/** Provenance of every value shown in the UI. */
export type DataProvenance = "live" | "fixture" | "stale" | "absent";

export type ConnectionStatus = "connected" | "disconnected" | "unknown";

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

export type CommandKind =
  | "pause_run"
  | "resume_run"
  | "cancel_run"
  | "pause_batch"
  | "resume_batch"
  | "cancel_batch";

export type CommandStatus = "idle" | "pending" | "confirmed" | "rejected";

/** What the current backend actually accepts. Unknown ⇒ do not show as active. */
export type SimulatorCapabilities = {
  process?: ProcessDefinition | null;
  liveTelemetry: boolean;
  viewportStream: boolean;
  recordingSeek?: boolean;
  startRun: boolean;
  startBatch: boolean;
  commands: Partial<Record<CommandKind, boolean>>;
  clothTypes?: CatalogOption[];
  clothConditions?: CatalogOption[];
};

export type TimelineMarker = {
  t: number;
  state: PhaseId | null;
  seq?: number;
  finished?: boolean;
  lifecycle?: string;
};

export type RunTimeline = {
  runId: string;
  tMax: number;
  markers: TimelineMarker[];
  hasTrajectory: boolean;
};

export type RecordingMeta = {
  runId: string;
  tMax: number;
  sampleHz: number;
  hasTrajectory: boolean;
  frameCount: number;
  nq: number;
};

export type RecordingFrame = {
  runId: string;
  t: number;
  requestedT: number;
  state: PhaseId;
  mime: string;
  imageBase64: string;
};

export type StageProgress = PhaseDefinition & {
  status: "completed" | "active" | "pending" | "failed" | "skipped";
  startedAtSimS: number | null;
  durationSimS: number | null;
};

export type RunEvent = {
  id: string;
  atSimS: number;
  atWallIso: string | null;
  stage: PhaseId | null;
  message: string;
  level: LogLevel;
  source?: string;
  operation?: string | null;
  station?: string | null;
  parallel?: boolean;
};

export type RunMetrics = {
  cycleTimeSimS: number | null;
  cycleTimeWallS: number | null;
  flatnessPre: number | null;
  flatnessPost: number | null;
  shirtInBag: boolean | null;
  measurements?: Record<string, number>;
};

export type RunConfig = {
  name: string | null;
  seed: number;
  scenario: string;
  notes: string | null;
  inputs?: Record<string, unknown>;
  garment?: string | null;
  clothType?: string | null;
  clothCondition?: string | null;
  skewed?: boolean;
  customDesign?: boolean;
};

export type RunSummary = {
  id: string;
  batchId: string | null;
  lifecycle: RunLifecycle;
  seed: number;
  name: string | null;
  garment?: string | null;
  clothType?: string | null;
  clothCondition?: string | null;
  currentState: PhaseId | null;
  startedAtIso: string | null;
  finishedAtIso: string | null;
  failReason: string | null;
  metrics: RunMetrics;
};

export type RunDetail = RunSummary & {
  config: RunConfig;
  /** The QC camera fired for this run; GET /runs/{id}/photo has the shot. */
  hasPhoto?: boolean;
  stages: StageProgress[];
  events: RunEvent[];
  telemetry: Telemetry | null;
};

export type QueueItem = {
  runId: string;
  seed: number;
  name: string | null;
  lifecycle: Extract<RunLifecycle, "queued" | "running" | "paused">;
};

export type BatchSummary = {
  id: string;
  name: string;
  lifecycle: BatchLifecycle;
  total: number;
  finished: number;
  succeeded: number;
  failed: number;
  pending: number;
  activeRunId: string | null;
  queuePreview: QueueItem[];
  queueTotal: number;
  seedStrategy: "sequential" | "list";
  baseSeed: number | null;
};

export type ExperimentListItem =
  | {
      kind: "run";
      id: string;
      title: string;
      lifecycle: RunLifecycle;
      seed: number;
      startedAtIso: string | null;
      batchId: string | null;
    }
  | {
      kind: "batch";
      id: string;
      title: string;
      lifecycle: BatchLifecycle;
      total: number;
      finished: number;
      succeeded: number;
      failed: number;
      startedAtIso: string | null;
    };

export type ControlSnapshot = {
  provenance: DataProvenance;
  connection: ConnectionStatus;
  lastUpdatedIso: string | null;
  capabilities: SimulatorCapabilities;
  activeRun: RunDetail | null;
  activeBatch: BatchSummary | null;
  incident: { id: string; message: string; runId: string | null } | null;
};

export type LaunchRequest =
  | {
      mode: "individual";
      name: string;
      seed: number;
      scenario: string;
      clothType: ClothType | "random";
      clothCondition: ClothCondition | "random";
      clothTypeWeights?: ClothWeightMap;
      clothConditionWeights?: ConditionWeightMap;
      customDesign?: CustomDesignPayload;
    }
  | {
      mode: "batch";
      name: string;
      count: number;
      seedStrategy: "sequential" | "list";
      baseSeed: number;
      scenario: string;
      clothMix: ClothMix;
      clothTypes: ClothType[];
      conditionMix: ClothMix;
      conditions: ClothCondition[];
      clothTypeWeights?: ClothWeightMap;
      clothConditionWeights?: ConditionWeightMap;
      customDesign?: CustomDesignPayload;
    };
