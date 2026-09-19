import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);
function load(relative, mocks = {}) {
  const source = readFileSync(resolve(relative), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", outputText)(
    (name) => name in mocks ? mocks[name] : require(name), module, module.exports,
  );
  return module.exports;
}

const { stagesForT } = load("src/dashboard/src/lib/use-run-replay.ts", { react: {}, "@/lib/bridge-client": {} });
const stages = ["PRESS", "TO_FOLDER", "FOLD", "BAG"].map((state) => ({
  state, label: `sim:${state}`, station: "sim", status: "completed", startedAtSimS: null, durationSimS: null,
}));
const markers = [
  { t: 3.53, state: "PRESS" },
  { t: 11.03, state: "TO_FOLDER" },
  { t: 15.778, state: "FOLD" },
  { t: 31.878, state: "BAG" },
  { t: 43.544, state: "BAG", finished: true, lifecycle: "succeeded" },
];
const at35 = stagesForT(markers, 35, 43.544, stages);
assert.equal(at35.at(-1).status, "active");
assert.equal(at35.at(-1).startedAtSimS, 31.878);
assert.equal(at35[0].durationSimS, 7.5);
assert.equal(at35[1].label, "sim:TO_FOLDER");
assert.equal(stagesForT(markers, 43.544, 43.544, stages).at(-1).status, "completed");
const failed = [...markers.slice(0, 2), { t: 12, state: null, finished: true, lifecycle: "failed" }];
assert.equal(stagesForT(failed, 12, 12, stages)[1].status, "failed");
assert.equal(stagesForT(failed, 12, 12, stages)[2].status, "skipped");
const cancelled = [...markers.slice(0, 2), { t: 12, state: null, finished: true, lifecycle: "cancelled" }];
assert.equal(stagesForT(cancelled, 12, 12, stages)[1].status, "skipped");

const protocol = load("packages/protocol/src/index.ts");
const format = load("src/dashboard/src/lib/format.ts", { "@xfold/protocol": protocol });
assert.equal(format.stageLabel("FOLD", stages), "sim:FOLD");
assert.equal(format.stageLabel("NEW_SIM_PHASE"), "NEW_SIM_PHASE");
assert.equal(format.runResultLabel({ lifecycle: "succeeded", clothCondition: "good" }), "Succeeded · Clean");
assert.equal(format.runResultLabel({ lifecycle: "succeeded", clothCondition: "skewed" }), "Succeeded · Rotated");
assert.equal(format.runResultLabel({ lifecycle: "succeeded", clothCondition: "notgood" }), "Succeeded · Stained");
assert.equal(format.runResultLabel({ lifecycle: "failed", clothCondition: "notgood" }), "Failed · Stained");
assert.equal(format.runResultLabel({ lifecycle: "failed", clothCondition: "damaged" }), "Failed · Torn");
assert.equal(format.runProcessLabel({ lifecycle: "succeeded", clothCondition: "notgood" }), "Succeeded");
assert.equal(format.runGarmentLabel({ lifecycle: "succeeded", clothCondition: "notgood" }), "Stained");
const { consoleLines, lineFromRunEvent } = load("src/dashboard/src/lib/console.ts", { "@/lib/format": format });
const event = { id: "e1", atSimS: 15, atWallIso: "2026-09-19T13:00:00Z", stage: "FOLD", level: "debug", source: "bagger", message: "ready", operation: "BAG_READY", station: "bagger", parallel: true };
assert.equal(lineFromRunEvent(event).level, "debug");
assert.equal(lineFromRunEvent(event).source, "bagger");
assert.equal(lineFromRunEvent(event).parallel, true);
const run = { events: [event, { ...event, id: "e2", atSimS: 20, message: "later" }] };
const journal = [{ type: "log", seq: 30, runId: "RUN-001", tsIso: event.atWallIso, t: 20, level: "info", source: "line", message: "later" }];
assert.equal(consoleLines(run, journal).length, 2);

const { BridgeClient } = load("src/dashboard/src/lib/bridge-client.ts");
const originalFetch = globalThis.fetch;
const originalEventSource = globalThis.EventSource;
const sources = [];
globalThis.EventSource = class {
  constructor(url) { this.url = url; sources.push(this); }
  close() {}
};
const calls = [];
const launches = [];
globalThis.fetch = async (url, options) => {
  calls.push(url);
  if (options?.method === "POST") {
    launches.push(JSON.parse(options.body));
    return { ok: true, json: async () => ({ ok: true, id: "test-run" }) };
  }
  return { ok: true, json: async () => url.endsWith("/health") ? { ok: true }
    : url.endsWith("/snapshot") ? { journalSeq: 99, capabilities: {}, activeRun: null, activeBatch: null }
    : [] };
};
const client = new BridgeClient("http://127.0.0.1:8765");
try {
  await client.start();
  assert.ok(sources[0].url.endsWith("after_seq=0"));
  const fact = { type: "log", seq: 1, runId: "RUN-001", source: "line", message: "first", t: 0, level: "info" };
  sources[0].onmessage({ data: JSON.stringify(fact) });
  sources[0].onmessage({ data: JSON.stringify(fact) });
  assert.equal(client.listJournal("RUN-001").length, 1);
  calls.length = 0;
  await Promise.all([client.refreshSnapshot(), client.refreshSnapshot()]);
  assert.equal(calls.filter((url) => url.endsWith("/snapshot")).length, 1);
  await client.launch({ mode: "individual", name: "weighted", seed: 7, scenario: "line", clothType: "random", clothCondition: "skewed", clothTypeWeights: { tee: 0, polo: 1 } });
  assert.equal(launches[0].scenario, "line");
  assert.equal(launches[0].clothCondition, "skewed");
  assert.deepEqual(launches[0].clothTypeWeights, { tee: 0, polo: 1 });
  await client.launch({ mode: "batch", name: "mixed", count: 3, baseSeed: 8, seedStrategy: "sequential", scenario: "line", clothMix: "list", clothTypes: ["tee", "polo"], conditionMix: "random", conditions: [], clothConditionWeights: { good: 1, damaged: 0 } });
  assert.equal(launches[1].clothMix, "list");
  assert.deepEqual(launches[1].clothTypes, ["tee", "polo"]);
  assert.deepEqual(launches[1].clothConditionWeights, { good: 1, damaged: 0 });
} finally {
  client.stop();
  globalThis.fetch = originalFetch;
  globalThis.EventSource = originalEventSource;
}
console.log("dashboard observability: replay, simulator labels, console history, SSE cursor and snapshot coalescing OK");
