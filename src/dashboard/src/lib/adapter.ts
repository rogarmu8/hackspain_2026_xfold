import { PRODUCTIVE_CYCLE, SAMPLE_TELEMETRY } from "@xfold/protocol";
import { FIXTURE_CAPABILITIES, LIVE_CAPABILITIES } from "./capabilities";
import {
  FIXTURE_ACTIVE_RUN,
  FIXTURE_BATCH,
  FIXTURE_EXPERIMENTS,
  FIXTURE_RUNS_BY_ID,
} from "./fixtures";
import type {
  BatchSummary,
  CommandKind,
  ControlSnapshot,
  ExperimentListItem,
  LaunchRequest,
  RunDetail,
  RunSummary,
} from "./types";

/** Fixed clock for fixture mutations triggered outside first paint. */
const FIXTURE_CLOCK = "2026-09-18T22:14:08.000Z";
/**
 * Scenario knobs for the fixture adapter.
 * These are UI demos — they do not talk to MuJoCo.
 */
export type FixtureScenario =
  | "active"
  | "empty"
  | "disconnected"
  | "failed"
  | "finished";

export type AdapterMode = "fixture" | "protocol-sample";

export type PendingCommand = {
  kind: CommandKind;
  scopeLabel: string;
  requestedAtIso: string;
};

/**
 * Separates real protocol data from dashboard fixtures.
 * Never pretends SAMPLE_TELEMETRY is a live stream.
 */
export class DashboardAdapter {
  mode: AdapterMode;
  scenario: FixtureScenario;
  pendingCommand: PendingCommand | null = null;
  /** Local fixture mutations after “confirmed” demo commands / launches. */
  private fixtureRun: RunDetail | null;
  private fixtureBatch: BatchSummary | null;
  private launches: ExperimentListItem[];
  private runs: Record<string, RunDetail> = structuredClone(FIXTURE_RUNS_BY_ID);
  private batches: Record<string, BatchSummary> = {};

  private remember() {
    if (this.fixtureRun) this.runs[this.fixtureRun.id] = structuredClone(this.fixtureRun);
    if (this.fixtureBatch) this.batches[this.fixtureBatch.id] = structuredClone(this.fixtureBatch);
  }

  serialize() {
    this.remember();
    return JSON.stringify({ version: 1, runs: this.runs, batches: this.batches,
      launches: this.launches, run: this.fixtureRun, batch: this.fixtureBatch, scenario: this.scenario });
  }

  restore(raw: string) {
    try {
      const saved = JSON.parse(raw);
      if (saved.version !== 1 || !Array.isArray(saved.launches) || !saved.runs || !saved.batches) return;
      this.runs = saved.runs; this.batches = saved.batches; this.launches = saved.launches;
      this.fixtureRun = saved.run; this.fixtureBatch = saved.batch; this.scenario = saved.scenario;
    } catch { /* An unreadable local demo starts from clean fixtures. */ }
  }

  private freshRun(
    id: string,
    seed: number,
    name: string,
    scenario: string,
    batchId: string | null,
    extras?: {
      garment?: string;
      clothType?: string;
      clothCondition?: string;
      skewed?: boolean;
    },
  ): RunDetail {
    const clothType = extras?.clothType ?? "tee";
    const clothCondition = extras?.clothCondition ?? "good";
    const garment = extras?.garment ?? clothType;
    const skewed = extras?.skewed ?? clothCondition === "skewed";
    return { id, seed, name: name || null, batchId, lifecycle: "running", currentState: "PICK",
      garment, clothType, clothCondition,
      startedAtIso: FIXTURE_CLOCK, finishedAtIso: null, failReason: null,
      config: {
        name: name || null,
        seed,
        scenario,
        notes: "Local demo, not connected to the simulator.",
        garment,
        clothType,
        clothCondition,
        skewed,
      },
      metrics: { cycleTimeSimS: null, cycleTimeWallS: null, flatnessPre: null, flatnessPost: null, shirtInBag: null },
      telemetry: { t: 0, state: "PICK", cycle: 1, flatness: null, shirt_in_bag: false },
      stages: PRODUCTIVE_CYCLE.map((state, i) => ({ state, status: i === 0 ? "active" : "pending", startedAtSimS: i === 0 ? 0 : null, durationSimS: null })),
      events: [{ id: `${id}-start`, atSimS: 0, atWallIso: FIXTURE_CLOCK, stage: "PICK", message: "Local sample created; nothing was sent to the simulator.", level: "info" }],
    };
  }

  constructor(
    mode: AdapterMode = "fixture",
    scenario: FixtureScenario = "active",
  ) {
    this.mode = mode;
    this.scenario = scenario;
    this.fixtureRun = structuredClone(FIXTURE_ACTIVE_RUN);
    this.fixtureBatch = structuredClone(FIXTURE_BATCH);
    this.launches = [...FIXTURE_EXPERIMENTS];
  }

  setScenario(scenario: FixtureScenario) {
    this.remember();
    this.scenario = scenario;
    this.pendingCommand = null;
    if (scenario === "active") {
      this.fixtureRun = structuredClone(FIXTURE_ACTIVE_RUN);
      this.fixtureBatch = structuredClone(FIXTURE_BATCH);
    } else if (scenario === "failed") {
      this.fixtureRun = structuredClone(FIXTURE_RUNS_BY_ID["RUN-012"]);
      this.fixtureBatch = {
        ...structuredClone(FIXTURE_BATCH),
        activeRunId: "RUN-012",
        lifecycle: "partial",
      };
    } else if (scenario === "finished") {
      this.fixtureRun = structuredClone(FIXTURE_RUNS_BY_ID["RUN-011"]);
      this.fixtureBatch = null;
    } else if (scenario === "empty") {
      this.fixtureRun = null;
      this.fixtureBatch = null;
    }
  }

  getControlSnapshot(): ControlSnapshot {
    if (this.mode === "protocol-sample") {
      return {
        provenance: "absent",
        connection: "disconnected",
        lastUpdatedIso: null,
        capabilities: LIVE_CAPABILITIES,
        activeRun: null,
        activeBatch: null,
        incident: {
          id: "no-bus",
          message:
            "The simulator does not publish live telemetry or accept commands yet. Only SAMPLE_TELEMETRY exists in @xfold/protocol.",
          runId: null,
        },
      };
    }

    if (this.scenario === "disconnected") {
      return {
        provenance: "stale",
        connection: "disconnected",
        lastUpdatedIso: "2026-09-18T22:12:01.000Z",
        capabilities: { ...FIXTURE_CAPABILITIES, commands: {} },
        activeRun: this.fixtureRun
          ? { ...this.fixtureRun, telemetry: this.fixtureRun.telemetry }
          : structuredClone(FIXTURE_ACTIVE_RUN),
        activeBatch: this.fixtureBatch,
        incident: {
          id: "link-down",
          message: "No connection to the simulation process",
          runId: this.fixtureRun?.id ?? null,
        },
      };
    }

    if (this.scenario === "empty") {
      return {
        provenance: "fixture",
        connection: "connected",
        // Stable stamp — never Date.now() during render (hydration).
        lastUpdatedIso: "2026-09-18T22:14:08.000Z",
        capabilities: FIXTURE_CAPABILITIES,
        activeRun: null,
        activeBatch: null,
        incident: null,
      };
    }

    return {
      provenance: "fixture",
      connection: "connected",
      lastUpdatedIso: "2026-09-18T22:14:08.000Z",
      capabilities: FIXTURE_CAPABILITIES,
      activeRun: this.fixtureRun,
      activeBatch: this.fixtureBatch,
      incident:
        this.fixtureRun?.lifecycle === "failed"
          ? {
              id: "run-fail",
              message: this.fixtureRun.failReason ?? "Run failed",
              runId: this.fixtureRun.id,
            }
          : null,
    };
  }

  listExperiments(): ExperimentListItem[] {
    if (this.mode === "protocol-sample") return [];
    this.remember();
    return this.launches.map((item) => {
      if (item.kind === "run") return { ...item, lifecycle: this.runs[item.id]?.lifecycle ?? item.lifecycle };
      const batch = this.batches[item.id];
      return batch ? { ...item, lifecycle: batch.lifecycle, finished: batch.finished, succeeded: batch.succeeded, failed: batch.failed } : item;
    });
  }

  listHistory(): RunSummary[] {
    if (this.mode === "protocol-sample") return [];
    this.remember();
    return Object.values(this.runs).sort((a, b) => (b.startedAtIso ?? "").localeCompare(a.startedAtIso ?? ""));
  }

  getRun(id: string): RunDetail | null {
    if (this.mode === "protocol-sample") return null;
    if (this.fixtureRun?.id === id) return this.fixtureRun;
    return this.runs[id] ?? null;
  }

  getBatch(id: string): BatchSummary | null {
    if (this.mode === "protocol-sample") return null;
    if (this.fixtureBatch?.id === id) return this.fixtureBatch;
    if (this.batches[id]) return this.batches[id];
    if (id === "B-008") return structuredClone(FIXTURE_BATCH);
    if (id === "B-007") {
      return {
        id: "B-007",
        name: "Short batch · seeds 10–14",
        lifecycle: "succeeded",
        total: 5,
        finished: 5,
        succeeded: 5,
        failed: 0,
        pending: 0,
        activeRunId: null,
        queuePreview: [],
        queueTotal: 0,
        seedStrategy: "sequential",
        baseSeed: 10,
      };
    }
    return null;
  }

  /** Protocol sample only — never presented as a live feed. */
  getProtocolSample() {
    return SAMPLE_TELEMETRY;
  }

  requestCommand(kind: CommandKind, scopeLabel: string): PendingCommand | null {
    const caps = this.getControlSnapshot().capabilities;
    if (!caps.commands[kind]) return null;
    if (this.pendingCommand) return null;
    this.pendingCommand = {
      kind,
      scopeLabel,
      requestedAtIso: "2026-09-18T22:14:08.000Z",
    };
    return this.pendingCommand;
  }

  /** Fixture-only: pretend the (nonexistent) sim confirmed the command. */
  confirmPendingCommand() {
    if (!this.pendingCommand || this.mode !== "fixture") return;
    const kind = this.pendingCommand.kind;
    this.pendingCommand = null;

    if (!this.fixtureRun) return;

    if (kind === "pause_run") {
      this.fixtureRun = { ...this.fixtureRun, lifecycle: "paused" };
    } else if (kind === "resume_run") {
      this.fixtureRun = { ...this.fixtureRun, lifecycle: "running" };
    } else if (kind === "cancel_run") {
      this.fixtureRun = {
        ...this.fixtureRun,
        lifecycle: "cancelled",
        finishedAtIso: FIXTURE_CLOCK,
        failReason: "Cancelled by the operator (fixture)",
      };
    } else if (kind === "pause_batch" && this.fixtureBatch) {
      this.fixtureBatch = { ...this.fixtureBatch, lifecycle: "paused" };
    } else if (kind === "resume_batch" && this.fixtureBatch) {
      this.fixtureBatch = { ...this.fixtureBatch, lifecycle: "running" };
    } else if (kind === "cancel_batch" && this.fixtureBatch) {
      this.fixtureBatch = {
        ...this.fixtureBatch,
        lifecycle: "cancelled",
        pending: 0,
        queuePreview: [],
        queueTotal: 0,
        activeRunId: null,
      };
      if (this.fixtureRun && ["running", "paused"].includes(this.fixtureRun.lifecycle)) {
        this.fixtureRun = {
          ...this.fixtureRun,
          lifecycle: "cancelled",
          finishedAtIso: FIXTURE_CLOCK,
          failReason: "Batch cancelado (fixture)",
        };
      }
    }
    const now = new Date().toISOString();
    if (this.fixtureRun) {
      this.fixtureRun.events.push({ id: `${this.fixtureRun.id}-${kind}-${now}`, atSimS: this.fixtureRun.telemetry?.t ?? 0, atWallIso: now, stage: this.fixtureRun.currentState, message: `Sample command confirmed: ${kind}`, level: "info" });
      if (kind === "cancel_run" && this.fixtureBatch) this.fixtureBatch = { ...this.fixtureBatch, activeRunId: null };
    }
    if (kind === "cancel_batch" && this.fixtureBatch) {
      for (const run of Object.values(this.runs)) {
        if (run.batchId === this.fixtureBatch.id && ["queued", "running", "paused"].includes(run.lifecycle)) {
          run.lifecycle = "cancelled"; run.finishedAtIso = now;
        }
      }
    }
    this.remember();
  }

  rejectPendingCommand() {
    this.pendingCommand = null;
  }

  launch(request: LaunchRequest): { ok: true; id: string } | { ok: false; reason: string } {
    if (this.mode !== "fixture") {
      return {
        ok: false,
        reason: "The simulator does not expose a launch API yet.",
      };
    }
    if (!this.getControlSnapshot().capabilities.startRun) {
      return { ok: false, reason: "Launch is not available." };
    }

    const seed = request.mode === "individual" ? request.seed : request.baseSeed;
    if (!Number.isSafeInteger(seed) || seed < 0 || seed > 2147483547) return { ok: false, reason: "Seed must be an integer between 0 and 2147483547." };
    if (request.mode === "batch" && (!Number.isInteger(request.count) || request.count < 1 || request.count > 100 || request.seedStrategy !== "sequential")) return { ok: false, reason: "Choose between 1 and 100 runs with sequential seeds." };
    this.remember();
    if (request.mode === "individual") {
      const id = `RUN-${String(100 + this.launches.length).padStart(3, "0")}`;
      this.launches = [
        {
          kind: "run",
          id,
          title: request.name || `Seed ${request.seed}`,
          lifecycle: "running",
          seed: request.seed,
          startedAtIso: FIXTURE_CLOCK,
          batchId: null,
        },
        ...this.launches,
      ];
      this.scenario = "active";
      this.fixtureBatch = null;
      this.fixtureRun = this.freshRun(id, request.seed, request.name, request.scenario, null, {
        clothType: request.clothType === "random" ? "tee" : request.clothType,
        clothCondition: request.clothCondition === "random" ? "good" : request.clothCondition,
        garment: request.clothType === "random" ? "tee" : request.clothType,
        skewed: request.clothCondition === "skewed",
      });
      this.remember();
      return { ok: true, id };
    }

    const id = `B-${String(20 + this.launches.length).padStart(3, "0")}`;
    this.launches = [
      {
        kind: "batch",
        id,
        title: request.name || `Batch ×${request.count}`,
        lifecycle: "running",
        total: request.count,
        finished: 0,
        succeeded: 0,
        failed: 0,
        startedAtIso: FIXTURE_CLOCK,
      },
      ...this.launches,
    ];
    const firstRunId = `RUN-${String(200 + this.launches.length).padStart(3, "0")}`;
    this.scenario = "active";
    this.fixtureBatch = {
      id,
      name: request.name || `Batch ×${request.count}`,
      lifecycle: "running",
      total: request.count,
      finished: 0,
      succeeded: 0,
      failed: 0,
      pending: Math.max(0, request.count - 1),
      activeRunId: firstRunId,
      queuePreview: Array.from({ length: Math.min(3, request.count - 1) }, (_, i) => ({
        runId: `${firstRunId}-${i + 2}`,
        seed: request.baseSeed + i + 1,
        name: null,
        lifecycle: "queued" as const,
      })),
      queueTotal: Math.max(0, request.count - 1),
      seedStrategy: request.seedStrategy,
      baseSeed: request.baseSeed,
    };
    const batchCloth = request.clothMix === "same" ? request.clothTypes[0] : request.clothTypes[0] ?? "tee";
    const batchCond = request.conditionMix === "same" ? request.conditions[0] : request.conditions[0] ?? "good";
    this.fixtureRun = this.freshRun(firstRunId, request.baseSeed, request.name, request.scenario, id, {
      clothType: batchCloth,
      clothCondition: batchCond,
      garment: batchCloth,
      skewed: batchCond === "skewed",
    });
    for (let i = 1; i < request.count; i++) {
      const queued = this.freshRun(`${firstRunId}-${i + 1}`, request.baseSeed + i, request.name, request.scenario, id, {
        clothType: batchCloth,
        clothCondition: batchCond,
        garment: batchCloth,
        skewed: batchCond === "skewed",
      });
      queued.lifecycle = "queued"; queued.startedAtIso = null; queued.currentState = null; queued.events = []; queued.telemetry = null;
      queued.stages = queued.stages.map((stage) => ({ ...stage, status: "pending", startedAtSimS: null }));
      this.runs[queued.id] = queued;
    }
    this.remember();
    return { ok: true, id };
  }
}

export function getAdapter(): DashboardAdapter {
  // Browser singleton so scenario/commands survive navigation within the SPA.
  if (typeof window !== "undefined") {
    const w = window as Window & { __xfoldAdapter?: DashboardAdapter };
    if (!w.__xfoldAdapter) {
      w.__xfoldAdapter = new DashboardAdapter("fixture", "active");
    }
    return w.__xfoldAdapter;
  }
  // SSR: fresh instance with stable fixtures (no Date.now in snapshots).
  return new DashboardAdapter("fixture", "active");
}
