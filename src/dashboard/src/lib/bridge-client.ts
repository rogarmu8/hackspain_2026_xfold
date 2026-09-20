/**
 * HTTP + SSE client for the XFOLD Python bridge.
 * Binding contract: docs/INTEGRATION_CONTRACT.md
 * Detail: docs/BRIDGE.md
 */

import type {
  BridgeCapabilities,
  BridgeLaunchBatch,
  BridgeLaunchRun,
  CommandKind,
  CommandRequest,
  JournalEvent,
} from "@xfold/protocol";
import type {
  BatchSummary,
  ControlSnapshot,
  ExperimentListItem,
  LaunchRequest,
  RecordingFrame,
  RecordingMeta,
  RunDetail,
  RunSummary,
  RunTimeline,
} from "./types";

export const DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765";

export function bridgeBaseUrl(): string {
  return "/api/bridge";
}

export async function probeBridge(baseUrl: string = bridgeBaseUrl()): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl}/health`, {
      method: "GET",
      signal: AbortSignal.timeout(1500),
    });
    if (!res.ok) return false;
    const body = (await res.json()) as { ok?: boolean };
    return body.ok === true;
  } catch {
    return false;
  }
}

type SnapshotListener = () => void;

const JOURNAL_BUFFER = 2000;

export class BridgeClient {
  readonly baseUrl: string;
  private es: EventSource | null = null;
  private lastSeq = 0;
  private listeners = new Set<SnapshotListener>();
  private _connection: "connected" | "disconnected" | "unknown" = "unknown";
  private _snapshot: ControlSnapshot | null = null;
  private _runs = new Map<string, RunDetail>();
  private _batches = new Map<string, BatchSummary>();
  private _experiments: ExperimentListItem[] = [];
  /** Ring buffer of journal facts (SSE replays from seq 0, so history is included). */
  private _journal: JournalEvent[] = [];
  private _pendingCommandId: string | null = null;
  private _pendingKind: CommandKind | null = null;
  private _capabilities: BridgeCapabilities | null = null;
  private snapshotRequest: Promise<ControlSnapshot | null> | null = null;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  constructor(baseUrl: string = bridgeBaseUrl()) {
    this.baseUrl = baseUrl;
  }

  get connection() {
    return this._connection;
  }

  get pendingCommandId() {
    return this._pendingCommandId;
  }

  get pendingKind() {
    return this._pendingKind;
  }

  subscribe(listener: SnapshotListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    for (const listener of this.listeners) listener();
  }

  async start(): Promise<boolean> {
    const ok = await probeBridge(this.baseUrl);
    if (!ok) {
      this._connection = "disconnected";
      this.notify();
      return false;
    }
    await this.refreshSnapshot();
    this.openEventSource();
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => {
      void this.refreshSnapshot();
    }, 1000);
    return true;
  }

  stop() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    this.pollTimer = null;
    this.refreshTimer = null;
    this.es?.close();
    this.es = null;
    this._connection = "disconnected";
    this.notify();
  }

  private openEventSource() {
    this.es?.close();
    const url = `${this.baseUrl}/events/stream?after_seq=${this.lastSeq}`;
    const es = new EventSource(url);
    this.es = es;
    es.onopen = () => {
      this._connection = "connected";
      void this.refreshSnapshot();
    };
    es.onerror = () => {
      this._connection = "disconnected";
      this.notify();
    };
    es.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as JournalEvent;
        if (event.seq <= this.lastSeq) return;
        this.lastSeq = event.seq;
        this.applyEvent(event);
        this.notify();
        if (!this.refreshTimer) this.refreshTimer = setTimeout(() => {
          this.refreshTimer = null;
          void this.refreshSnapshot();
        }, 100);
      } catch {
        /* ignore malformed frames */
      }
    };
  }

  private applyEvent(event: JournalEvent) {
    if (this._journal.at(-1)?.seq !== event.seq) {
      this._journal.push(event);
      if (this._journal.length > JOURNAL_BUFFER) this._journal.splice(0, this._journal.length - JOURNAL_BUFFER);
    }
    if (
      event.type === "command_applied" ||
      event.type === "command_rejected"
    ) {
      if (event.clientCommandId === this._pendingCommandId) {
        this._pendingCommandId = null;
        this._pendingKind = null;
      }
    }
  }

  refreshSnapshot(): Promise<ControlSnapshot | null> {
    if (!this.snapshotRequest) {
      this.snapshotRequest = this.loadSnapshot().finally(() => { this.snapshotRequest = null; });
    }
    return this.snapshotRequest;
  }

  private async loadSnapshot(): Promise<ControlSnapshot | null> {
    try {
      const res = await fetch(`${this.baseUrl}/snapshot`);
      if (!res.ok) throw new Error(`snapshot ${res.status}`);
      const raw = (await res.json()) as ControlSnapshot & {
        journalSeq?: number;
      };
      this._capabilities = raw.capabilities as BridgeCapabilities;
      this._snapshot = {
        ...raw,
        provenance: "live",
        connection: this._connection === "disconnected" ? "disconnected" : "connected",
      };
      if (raw.activeRun) this._runs.set(raw.activeRun.id, raw.activeRun);
      if (raw.activeBatch) this._batches.set(raw.activeBatch.id, raw.activeBatch);
      this._connection = "connected";
      await this.refreshLists();
      this.notify();
      return this._snapshot;
    } catch {
      this._connection = "disconnected";
      if (this._snapshot) {
        this._snapshot = {
          ...this._snapshot,
          provenance: "stale",
          connection: "disconnected",
        };
      }
      this.notify();
      return this._snapshot;
    }
  }

  private async refreshLists() {
    try {
      const [runsRes, expRes] = await Promise.all([
        fetch(`${this.baseUrl}/runs`),
        fetch(`${this.baseUrl}/experiments`),
      ]);
      if (runsRes.ok) {
        const runs = (await runsRes.json()) as RunDetail[];
        for (const run of runs) this._runs.set(run.id, run);
      }
      if (expRes.ok) {
        this._experiments = (await expRes.json()) as ExperimentListItem[];
      }
    } catch {
      /* keep last known lists */
    }
  }

  getControlSnapshot(): ControlSnapshot {
    if (this._snapshot) {
      return {
        ...this._snapshot,
        connection: this._connection,
        provenance:
          this._connection === "connected" ? "live" : this._snapshot.provenance === "live" ? "stale" : this._snapshot.provenance,
        capabilities: this._capabilities ?? this._snapshot.capabilities,
      };
    }
    return {
      provenance: "absent",
      connection: this._connection,
      lastUpdatedIso: null,
      capabilities: this._capabilities ?? {
        liveTelemetry: false,
        viewportStream: false,
        recordingSeek: false,
        startRun: false,
        startBatch: false,
        commands: {},
      },
      activeRun: null,
      activeBatch: null,
      incident: {
        id: "bridge-down",
        message: "No connection to the XFOLD bridge",
        runId: null,
      },
    };
  }

  listExperiments(): ExperimentListItem[] {
    return this._experiments;
  }

  /** Journal facts for one run (plus run-less bridge notes), oldest first. */
  listJournal(runId: string): JournalEvent[] {
    return this._journal.filter((e) => e.runId === runId || (e.runId == null && e.type === "log"));
  }

  listHistory(): RunSummary[] {
    return [...this._runs.values()].sort((a, b) =>
      (b.startedAtIso ?? "").localeCompare(a.startedAtIso ?? ""),
    );
  }

  getRun(id: string): RunDetail | null {
    return this._runs.get(id) ?? null;
  }

  getBatch(id: string): BatchSummary | null {
    return this._batches.get(id) ?? null;
  }

  async launch(
    request: LaunchRequest,
  ): Promise<{ ok: true; id: string } | { ok: false; reason: string }> {
    try {
      if (request.mode === "individual") {
        const body: BridgeLaunchRun = {
          name: request.name,
          seed: request.seed,
          scenario: request.scenario,
          clothType: request.clothType,
          clothCondition: request.clothCondition,
          clothTypeWeights: request.clothTypeWeights,
          clothConditionWeights: request.clothConditionWeights,
          customDesign: request.customDesign,
          speed: request.speed,
        };
        const res = await fetch(`${this.baseUrl}/runs`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = (await res.json()) as { ok?: boolean; id?: string; detail?: string };
        if (!res.ok) return { ok: false, reason: data.detail ?? `HTTP ${res.status}` };
        await this.refreshSnapshot();
        return { ok: true, id: data.id! };
      }
      const body: BridgeLaunchBatch = {
        name: request.name,
        count: request.count,
        baseSeed: request.baseSeed,
        seedStrategy: "sequential",
        scenario: request.scenario,
        clothMix: request.clothMix,
        clothTypes: request.clothTypes,
        conditionMix: request.conditionMix,
        conditions: request.conditions,
        clothTypeWeights: request.clothTypeWeights,
        clothConditionWeights: request.clothConditionWeights,
        customDesign: request.customDesign,
        speed: request.speed,
      };
      const res = await fetch(`${this.baseUrl}/batches`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await res.json()) as { ok?: boolean; id?: string; detail?: string };
      if (!res.ok) return { ok: false, reason: data.detail ?? `HTTP ${res.status}` };
      await this.refreshSnapshot();
      return { ok: true, id: data.id! };
    } catch (err) {
      return {
        ok: false,
        reason: err instanceof Error ? err.message : "Network error",
      };
    }
  }

  async requestCommand(
    kind: CommandKind,
    runId?: string | null,
    batchId?: string | null,
  ): Promise<{ ok: true; clientCommandId: string } | { ok: false; reason: string }> {
    if (this._pendingCommandId) {
      return { ok: false, reason: "A command is already pending" };
    }
    const clientCommandId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `cmd-${Date.now()}`;
    const body: CommandRequest = {
      clientCommandId,
      kind,
      runId: runId ?? null,
      batchId: batchId ?? null,
    };
    try {
      this._pendingCommandId = clientCommandId;
      this._pendingKind = kind;
      this.notify();
      const res = await fetch(`${this.baseUrl}/commands`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await res.json()) as {
        status?: string;
        reason?: string | null;
        clientCommandId?: string;
      };
      if (res.status === 409 || data.status === "rejected") {
        this._pendingCommandId = null;
        this._pendingKind = null;
        this.notify();
        return { ok: false, reason: data.reason ?? "Command rejected" };
      }
      if (!res.ok) {
        this._pendingCommandId = null;
        this._pendingKind = null;
        this.notify();
        return { ok: false, reason: `HTTP ${res.status}` };
      }
      // Applied synchronously on the mock bridge; clear pending after refresh.
      await this.refreshSnapshot();
      this._pendingCommandId = null;
      this._pendingKind = null;
      this.notify();
      return { ok: true, clientCommandId };
    } catch (err) {
      this._pendingCommandId = null;
      this._pendingKind = null;
      this.notify();
      return {
        ok: false,
        reason: err instanceof Error ? err.message : "Network error",
      };
    }
  }

  async fetchTimeline(runId: string): Promise<RunTimeline | null> {
    try {
      const res = await fetch(`${this.baseUrl}/runs/${encodeURIComponent(runId)}/timeline`);
      if (!res.ok) return null;
      return (await res.json()) as RunTimeline;
    } catch {
      return null;
    }
  }

  async fetchRecording(runId: string): Promise<RecordingMeta | null> {
    try {
      const res = await fetch(
        `${this.baseUrl}/runs/${encodeURIComponent(runId)}/recording`,
      );
      if (!res.ok) return null;
      return (await res.json()) as RecordingMeta;
    } catch {
      return null;
    }
  }

  async fetchRecordingFrame(
    runId: string,
    t: number,
  ): Promise<RecordingFrame | null> {
    try {
      const url = `${this.baseUrl}/runs/${encodeURIComponent(runId)}/recording/frame?t=${encodeURIComponent(String(t))}`;
      const res = await fetch(url);
      if (!res.ok) return null;
      return (await res.json()) as RecordingFrame;
    } catch {
      return null;
    }
  }
}
