import { PRODUCTIVE_CYCLE, type CellState, type Telemetry } from "@xfold/protocol";
import type {
  BatchSummary,
  ExperimentListItem,
  RunDetail,
  RunEvent,
  RunSummary,
  StageProgress,
} from "./types";

const NOW = "2026-09-18T22:14:08.000Z";

function stagesThrough(active: CellState, failed?: CellState): StageProgress[] {
  const activeIdx = PRODUCTIVE_CYCLE.indexOf(
    active as (typeof PRODUCTIVE_CYCLE)[number],
  );
  return PRODUCTIVE_CYCLE.map((state, index) => {
    if (failed && state === failed) {
      return {
        state,
        status: "failed",
        startedAtSimS: index * 7,
        durationSimS: 3.2,
      };
    }
    if (index < activeIdx) {
      return {
        state,
        status: "completed",
        startedAtSimS: index * 7,
        durationSimS: 6.4 + index * 0.3,
      };
    }
    if (index === activeIdx) {
      return {
        state,
        status: "active",
        startedAtSimS: index * 7,
        durationSimS: null,
      };
    }
    return {
      state,
      status: "pending",
      startedAtSimS: null,
      durationSimS: null,
    };
  });
}

function eventsFor(runId: string, upTo: CellState): RunEvent[] {
  const messages: Partial<Record<CellState, string>> = {
    PICK: "Agarre bimanual en el contenedor de entrada",
    ORIENT: "Cintas duales cuadran la camisa (collar aguas abajo)",
    SPREAD: "Tensado sobre la platina (OpenArm L+R)",
    PRESS: "Platina inferior fija; platen superior en descenso",
    FOLD: "Pliegue ninja: línea de pliegue + bajo",
    CHUTE: "Cama basculante; paquete en tolva",
    BAG: "Paquete en bolsa abierta",
  };
  const idx = PRODUCTIVE_CYCLE.indexOf(upTo as (typeof PRODUCTIVE_CYCLE)[number]);
  return PRODUCTIVE_CYCLE.slice(0, idx + 1).map((stage, i) => ({
    id: `${runId}-e${i + 1}`,
    atSimS: i * 7.1,
    atWallIso: NOW,
    stage,
    message: messages[stage] ?? stage,
    level: "info" as const,
  }));
}

const telemetryFold: Telemetry = {
  t: 28.4,
  state: "FOLD",
  cycle: 14,
  flatness: 0.002,
  shirt_in_bag: false,
};

export const FIXTURE_ACTIVE_RUN: RunDetail = {
  id: "RUN-014",
  batchId: "B-008",
  lifecycle: "running",
  seed: 42,
  name: "Pliegue estándar",
  currentState: "FOLD",
  startedAtIso: "2026-09-18T22:13:26.000Z",
  finishedAtIso: null,
  failReason: null,
  metrics: {
    cycleTimeSimS: null,
    cycleTimeWallS: null,
    flatnessPre: 0.041,
    flatnessPost: 0.002,
    shirtInBag: false,
  },
  config: {
    name: "Pliegue estándar",
    seed: 42,
    scenario: "openarm-ninja-bag",
    notes: "Fixture coherente con PICK→BAG; no es telemetría del sim.",
  },
  stages: stagesThrough("FOLD"),
  events: eventsFor("RUN-014", "FOLD"),
  telemetry: telemetryFold,
};

export const FIXTURE_BATCH: BatchSummary = {
  id: "B-008",
  name: "Lote camisetas · semillas 42–61",
  lifecycle: "running",
  total: 20,
  finished: 12,
  succeeded: 10,
  failed: 2,
  pending: 7,
  activeRunId: "RUN-014",
  queuePreview: [
    { runId: "RUN-015", seed: 43, name: null, lifecycle: "queued" },
    { runId: "RUN-016", seed: 44, name: null, lifecycle: "queued" },
    { runId: "RUN-017", seed: 45, name: null, lifecycle: "queued" },
  ],
  queueTotal: 7,
  seedStrategy: "sequential",
  baseSeed: 42,
};

export const FIXTURE_FAILED_RUN: RunDetail = {
  id: "RUN-012",
  batchId: "B-008",
  lifecycle: "failed",
  seed: 40,
  name: null,
  currentState: "SPREAD",
  startedAtIso: "2026-09-18T22:08:01.000Z",
  finishedAtIso: "2026-09-18T22:08:19.000Z",
  failReason: "Pérdida de agarre derecho durante el tensado",
  metrics: {
    cycleTimeSimS: 18.2,
    cycleTimeWallS: 19.1,
    flatnessPre: 0.038,
    flatnessPost: null,
    shirtInBag: false,
  },
  config: {
    name: null,
    seed: 40,
    scenario: "openarm-ninja-bag",
    notes: null,
  },
  stages: stagesThrough("SPREAD", "SPREAD"),
  events: [
    ...eventsFor("RUN-012", "PICK"),
    {
      id: "RUN-012-e-fail",
      atSimS: 9.4,
      atWallIso: "2026-09-18T22:08:19.000Z",
      stage: "SPREAD",
      message: "Pérdida de agarre derecho durante el tensado",
      level: "error",
    },
  ],
  telemetry: null,
};

export const FIXTURE_SUCCEEDED_RUN: RunDetail = {
  id: "RUN-011",
  batchId: "B-008",
  lifecycle: "succeeded",
  seed: 39,
  name: null,
  currentState: "BAG",
  startedAtIso: "2026-09-18T22:06:40.000Z",
  finishedAtIso: "2026-09-18T22:07:22.000Z",
  failReason: null,
  metrics: {
    cycleTimeSimS: 41.8,
    cycleTimeWallS: 42.3,
    flatnessPre: 0.036,
    flatnessPost: 0.0018,
    shirtInBag: true,
  },
  config: {
    name: null,
    seed: 39,
    scenario: "openarm-ninja-bag",
    notes: null,
  },
  stages: PRODUCTIVE_CYCLE.map((state, index) => ({
    state,
    status: "completed" as const,
    startedAtSimS: index * 7,
    durationSimS: 6.5 + index * 0.2,
  })),
  events: eventsFor("RUN-011", "BAG"),
  telemetry: {
    t: 41.8,
    state: "BAG",
    cycle: 11,
    flatness: 0.0018,
    shirt_in_bag: true,
  },
};

export const FIXTURE_HISTORY: RunSummary[] = [
  FIXTURE_ACTIVE_RUN,
  FIXTURE_FAILED_RUN,
  FIXTURE_SUCCEEDED_RUN,
  {
    id: "RUN-010",
    batchId: "B-007",
    lifecycle: "succeeded",
    seed: 12,
    name: "Smoke individual",
    currentState: "BAG",
    startedAtIso: "2026-09-18T21:50:00.000Z",
    finishedAtIso: "2026-09-18T21:50:44.000Z",
    failReason: null,
    metrics: {
      cycleTimeSimS: 43.1,
      cycleTimeWallS: 44.0,
      flatnessPre: 0.044,
      flatnessPost: 0.0022,
      shirtInBag: true,
    },
  },
  {
    id: "RUN-009",
    batchId: null,
    lifecycle: "cancelled",
    seed: 7,
    name: "Prueba cancelación",
    currentState: "PRESS",
    startedAtIso: "2026-09-18T21:40:00.000Z",
    finishedAtIso: "2026-09-18T21:40:18.000Z",
    failReason: "Cancelada por el operador",
    metrics: {
      cycleTimeSimS: null,
      cycleTimeWallS: 18,
      flatnessPre: 0.04,
      flatnessPost: null,
      shirtInBag: false,
    },
  },
];

export const FIXTURE_EXPERIMENTS: ExperimentListItem[] = [
  {
    kind: "batch",
    id: "B-008",
    title: FIXTURE_BATCH.name,
    lifecycle: "running",
    total: FIXTURE_BATCH.total,
    finished: FIXTURE_BATCH.finished,
    succeeded: FIXTURE_BATCH.succeeded,
    failed: FIXTURE_BATCH.failed,
    startedAtIso: "2026-09-18T22:05:00.000Z",
  },
  {
    kind: "batch",
    id: "B-007",
    title: "Lote corto · semillas 10–14",
    lifecycle: "succeeded",
    total: 5,
    finished: 5,
    succeeded: 5,
    failed: 0,
    startedAtIso: "2026-09-18T21:30:00.000Z",
  },
  {
    kind: "run",
    id: "RUN-010",
    title: "Smoke individual",
    lifecycle: "succeeded",
    seed: 12,
    startedAtIso: "2026-09-18T21:50:00.000Z",
    batchId: "B-007",
  },
  {
    kind: "run",
    id: "RUN-009",
    title: "Prueba cancelación",
    lifecycle: "cancelled",
    seed: 7,
    startedAtIso: "2026-09-18T21:40:00.000Z",
    batchId: null,
  },
];

export const FIXTURE_RUNS_BY_ID: Record<string, RunDetail> = {
  [FIXTURE_ACTIVE_RUN.id]: FIXTURE_ACTIVE_RUN,
  [FIXTURE_FAILED_RUN.id]: FIXTURE_FAILED_RUN,
  [FIXTURE_SUCCEEDED_RUN.id]: FIXTURE_SUCCEEDED_RUN,
  "RUN-010": {
    ...FIXTURE_SUCCEEDED_RUN,
    id: "RUN-010",
    batchId: "B-007",
    seed: 12,
    name: "Smoke individual",
    config: {
      name: "Smoke individual",
      seed: 12,
      scenario: "openarm-ninja-bag",
      notes: null,
    },
  },
  "RUN-009": {
    id: "RUN-009",
    batchId: null,
    lifecycle: "cancelled",
    seed: 7,
    name: "Prueba cancelación",
    currentState: "PRESS",
    startedAtIso: "2026-09-18T21:40:00.000Z",
    finishedAtIso: "2026-09-18T21:40:18.000Z",
    failReason: "Cancelada por el operador",
    metrics: {
      cycleTimeSimS: null,
      cycleTimeWallS: 18,
      flatnessPre: 0.04,
      flatnessPost: null,
      shirtInBag: false,
    },
    config: {
      name: "Prueba cancelación",
      seed: 7,
      scenario: "openarm-ninja-bag",
      notes: null,
    },
    stages: stagesThrough("PRESS").map((s) =>
      s.state === "PRESS" ? { ...s, status: "skipped" as const } : s,
    ),
    events: eventsFor("RUN-009", "PRESS"),
    telemetry: null,
  },
};
