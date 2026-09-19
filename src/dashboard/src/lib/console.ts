import type { JournalEvent, LogLevel } from "@xfold/protocol";
import { stageLabel, runResultLabel } from "@/lib/format";
import type { RunDetail, RunEvent } from "@/lib/types";

/** One row of the live console; derived from journal facts or run events. */
export type ConsoleLine = {
  id: string;
  /** Wall-clock ISO of the fact. */
  tsIso: string | null;
  /** Simulated seconds when known. */
  atSimS: number | null;
  level: LogLevel;
  /** Emitter: "fsm", "press-driver", "line", "bridge", "ui"… */
  source: string;
  message: string;
  stage?: string | null;
  operation?: string | null;
  station?: string | null;
  parallel?: boolean;
};

/** Seconds of silence (no journal fact) after which a running run counts as stalled. */
export const STALL_AFTER_S = 8;

export function lineFromJournal(event: JournalEvent): ConsoleLine | null {
  const base = { id: `j${event.seq}`, tsIso: event.tsIso };
  switch (event.type) {
    case "log":
      return { ...base, atSimS: event.t, level: event.level, source: event.source, message: event.message, stage: event.stage, operation: event.operation, station: event.station, parallel: event.parallel };
    case "run_started":
      return {
        ...base,
        atSimS: 0,
        level: "info",
        source: "bridge",
        message: `run started · seed ${event.seed} · ${event.garment ?? event.scenario}${
          event.clothCondition ? ` · ${event.clothCondition}` : ""
        }`,
      };
    case "state_changed":
      return { ...base, atSimS: event.t, level: "info", source: "fsm", message: `→ ${event.label ?? stageLabel(event.state)}` };
    case "run_finished":
      return {
        ...base,
        atSimS: event.t,
        level: event.lifecycle === "succeeded" ? "info" : "warning",
        source: "bridge",
        message: runResultLabel({
          lifecycle: event.lifecycle,
          failReason: event.reason ?? null,
          clothCondition: event.clothCondition ?? null,
        }).toLowerCase(),
      };
    case "command_accepted":
    case "command_rejected":
    case "command_applied":
      return {
        ...base,
        atSimS: null,
        level: event.type === "command_rejected" ? "warning" : "debug",
        source: "cmd",
        message: `${event.kind} ${event.type.replace("command_", "")}${event.reason ? ` · ${event.reason}` : ""}`,
      };
    case "metric_sample":
    case "batch_updated":
      return null;
  }
}

export function lineFromRunEvent(event: RunEvent): ConsoleLine {
  return {
    id: event.id,
    tsIso: event.atWallIso,
    atSimS: event.atSimS,
    level: event.level,
    source: event.source ?? "run",
    message: event.message,
    stage: event.stage,
    operation: event.operation,
    station: event.station,
    parallel: event.parallel,
  };
}

/** Journal lines when the bridge is live; the run's own event list otherwise. */
export function consoleLines(run: RunDetail | null, journal: JournalEvent[]): ConsoleLine[] {
  if (!run) return [];
  const fromJournal = journal.map(lineFromJournal).filter((l): l is ConsoleLine => l !== null);
  if (!run.events.length) return fromJournal;
  const extras = journal.filter((e) => e.type.startsWith("command_") || e.runId == null)
    .map(lineFromJournal).filter((l): l is ConsoleLine => l !== null);
  return [...run.events.map(lineFromRunEvent), ...extras]
    .sort((a, b) => (a.tsIso ?? "").localeCompare(b.tsIso ?? ""));
}
