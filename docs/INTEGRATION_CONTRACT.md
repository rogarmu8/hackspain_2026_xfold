# XFOLD — Integration contract (sim ↔ dashboard)

**Read this before changing anything that moves data between the simulator and the monitor.**

This is the binding contract for humans and agents. Implementation detail and rationale live in [`BRIDGE.md`](BRIDGE.md). Types live in [`packages/protocol/src/index.ts`](../packages/protocol/src/index.ts) and [`src/sim/src/xfold/bridge/schema.py`](../src/sim/src/xfold/bridge/schema.py).

If you change the contract, you **must** update: protocol TS → Python schema → this file → `BRIDGE.md` event/route tables → run `scripts/check-bridge-contract.sh`.

---

## 0. One-sentence model

> The **physics / FSM driver** emits **journal facts** into **Runtime**; the **bridge HTTP** exposes that journal (SSE) and accepts commands (REST); the **dashboard** renders snapshots and never talks to MuJoCo directly.

Live default: `LineDriver` on a shared `SimSession` (the belt/press/folder/bagger line). Fallbacks, in order: `PressBridgeDriver` (older arm cell), then `MockDriver` when MuJoCo is unavailable. `GET /capabilities` reports the winner as `scene` + `driver`.

---

## 1. Layers (do not skip or merge)

| Layer | Owns | Must not |
|-------|------|----------|
| **Driver** (`mock_driver.py` → later MuJoCo loop) | Advance the cell; call `runtime.emit_state` / `finish_*` | Import FastAPI, touch the browser, block on network |
| **Runtime + Journal** (`runtime.py`, `journal.py`) | Runs/batches, command apply, append-only events, snapshots | Know about React/Next, invent ad-hoc JSON outside protocol |
| **HTTP bridge** (`app.py`) | REST + SSE on `127.0.0.1:8765` | Contain FSM logic or physics |
| **Dashboard** (`bridge-client.ts`, `dashboard-context.tsx`) | Probe bridge → `live` or fall back to **fixtures** | Call Python, spawn MuJoCo, invent a second bus (WS/gRPC) |

```text
Driver ──emit_*──► Runtime ──append──► Journal ──SSE──► Dashboard
                      ▲                      │
                      └── REST /commands ────┘
```

---

## 2. Stable wire contract

### Simulator authority (bridge 0.2)

The running simulator is the source of truth for phases, operations and measurements. For the line, `xfold.line.LINE_PHASES` declares the ordered `{state, label, station}` catalogue; `Line._enter` emits observations via `on_event`. `LineDriver` queues them under the simulation lock and publishes after releasing it. It must not translate these observations into the legacy six-state cycle or suppress backward-looking names.

The line emits `LOAD → TO_PRESS → PRESS → TO_QC → PHOTO → SORT → TO_FOLDER → FOLD → INSERT → TO_SEAL → SEAL → TO_CARTON → DONE`. Sub-operations preserve the physical stage (`PRESS/STEAM/LIFT`, each flap, `BAG/TILT/PEEL/RELEASE`, etc.). Bag preparation emits parallel operations on station `bagger`, without replacing the main operation. QC transport and the photo stop have separate timings; photo outcomes (`PHOTO_SAVED`, `PHOTO_UNAVAILABLE`, `PHOTO_FAILED`) are structured observations on station `qc`. After the shot, `SORT` either passes the garment to the folder or suction-diverts a stained/torn shirt into a reject tote (`REJECT_STAINED` / `REJECT_BROKEN`) and jumps to `DONE`. Process `succeeded` means the line handled the SKU correctly (stained → stained tote, torn → broken tote, clean/rotated → pack). Packing a reject SKU is `failed`; the garment mark (Clean / Rotated / Stained / Torn) stays on `clothCondition` either way. `run_finished` includes `clothCondition`. Missing GL/capture failures emit warnings, not a false successful photo; image bytes remain outside the journal.

`/capabilities.process` (also in snapshot capabilities) advertises `{scenario, stages, seedApplied}` before launch. `run.stages` supplies phase IDs, labels, stations and timings to the UI; live consumers never construct a cycle from `PRODUCTIVE_CYCLE`. `PhaseId` is a string supplied by the simulator; `CellState`/`PRODUCTIVE_CYCLE` remain legacy types for press/mock and fixtures. Unknown, undeclared runtime phases fail explicitly. Launch does not imply physical phase entry; only the driver's first observation does. Repeated observations in the same phase do not restart its timer.

A `log` additionally carries `stage`, `operation`, `station`, `parallel`. These fields and the original `source`/`level` survive in `run.events`. Observations use the simulation timestamp captured at the operation boundary, not the time the driver flushes them. A phase transition is published before its operation log. Telemetry optionally includes `operation` and `activities` (latest parallel milestone per station, not a claim that it is still moving).

`metric_sample.measurements` contains measured scalar values with units in their keys. Current line measurements: `flatnessPreM` and `flatnessPostM` are standard deviation of vertex z immediately before lowering and after raising the platen; `packLengthM`, `packWidthM`, `packHeightM` are folded AABB dimensions. These are observations, not quality gates. Missing measurements stay null; `shirt_in_bag` is nullable and is not inferred from phase. `succeeded` means the line handled this SKU correctly (pack a clean/rotated shirt, or divert stain/tear to the matching tote), not that containment or seal quality was validated. `cycleTimeWallS` is elapsed wall time including pauses.

`config.inputs` stores the effective per-run garment/mesh/texture/cloth/solver configuration, condition, pose flag, seed and whether it is actually applied. `/capabilities.process.seedApplied: true` advertises seed support; per-run `seedApplied` is true for random/list selections, stain variants or skewed poses, and false for fixed clean/torn selections. `spawnYawRad` and `spawnOffsetYM` are emitted at LOAD from the actual initial pose. Inputs are resolved for each run, not copied from the garment compiled at process startup. Scenario is `line`, regardless of stale UI launch defaults. Legacy drivers retain their own process catalogue. `run_started` persists the run's `stages`, `inputs` and `driver` in the journal as well, so configuration is not confined to the in-memory snapshot.

Timeline terminal markers have `state: null`; they must not overwrite phase start markers. Replay uses `run.stages`, not a hard-coded sequence. Trajectory remains qpos-only: line replay is explicitly **partial**, because mocap and mutable visual geometry are not recorded. Durable run recovery uses SQLite at `data/experiments.sqlite` (see §2 REST `/experiments`); geometric quality gates remain separate work.

### Shared package

- TypeScript: `@xfold/protocol` — **canonical names** for agents generating code.
- Python: `xfold.bridge.schema` — must match (hackathon: hand-sync; verify with `bash scripts/check-bridge-contract.sh`).

### Telemetry snapshot fields (unchanged shape)

`t`, `state`, `cycle`, `flatness`, `shirt_in_bag` — see `Telemetry` in protocol.

### Journal events (append-only facts)

| `type` | When to emit |
|--------|----------------|
| `run_started` | Run enters running |
| `state_changed` | Simulator phase entry (`state`, optional `label` / `station`, `t`, `cycle`); line catalogue comes from `LINE_PHASES` (includes `ORIENT`) |
| `metric_sample` | Metrics tick (may be coalesced; never instead of `state_changed`) |
| `run_finished` | Terminal lifecycle + `clothCondition` |
| `command_accepted` / `command_rejected` / `command_applied` | Command pipeline |
| `batch_updated` | Batch counters / active child |
| `log` | Simulator log line for the live console (`level` debug/info/warning/error, `message`, `source`, `t`). Via `runtime.emit_log` |

Every event has: `seq`, `tsIso`, `type`, `runId`, `batchId`.

### REST (commands & reads)

| Method | Path | Use |
|--------|------|-----|
| GET | `/health` | Dashboard probe |
| GET | `/capabilities` | What UI may enable |
| GET | `/snapshot` | Control-room materialization |
| GET | `/events/stream?after_seq=N` | Live journal (SSE) |
| GET | `/viewport/meta` | Viewport readiness (`seq`, `ageMs`, …) |
| GET | `/viewport/frame?after_seq=&wait_ms=` | **Primary** live view: long-poll JPEG |
| GET | `/viewport/stream` | Legacy MJPEG (curl/VLC only — not the dashboard) |
| GET | `/runs`, `/runs/{id}` | Run list / detail (memory + durable SQLite) |
| GET | `/runs/{id}/timeline` | FSM markers for scrubber (journal, then SQLite after restart) |
| GET | `/runs/{id}/recording` | Trajectory metadata |
| GET | `/runs/{id}/recording/frame?t=` | Replay seek (JPEG + state) |
| GET | `/batches/{id}` | Batch summary |
| GET | `/experiments` | Launch list for Experimentos (survives bridge restart; `data/experiments.sqlite`) |
| GET | `/experiments/{id}` | Durable experiment detail (`kind: run|batch`) |
| POST | `/runs`, `/batches` | Launch. Run: `name`, `seed`, `scenario`, `clothType` (`tee`… / `custom` or `random`), `clothCondition` (`good`/`damaged`/`notgood`/`skewed` or `random`), optional `clothTypeWeights` / `clothConditionWeights` when random (0 = never). `custom` is a silhouette sheet: send `customDesign` `{ mime, data }` (base64 photo; the bridge cuts the garment out of the photo, builds a flexcomp to that outline, and prints both faces; never a journal payload). Batch: `count`, `baseSeed`, `clothMix`/`conditionMix` (`same`/`random`/`list`) + `clothTypes`/`conditions` + the same weight maps; the photo is required if the mix can draw `custom`. `seed` also draws a skewed heading (flat on the belt). Catalogue on `GET /capabilities`. |
| POST | `/commands` | `{ clientCommandId, kind, runId?, batchId? }` |

**Two planes (do not mix):**

| Plane | Transport | Carries |
|-------|-----------|---------|
| Control | Journal + REST/SSE | FSM, metrics, commands |
| Media | Long-poll JPEG (`/viewport/frame`) | Live camera pixels |

Dashboard reaches the media plane via same-origin Next proxy `/api/bridge/*` → Python `:8765` (avoids CORS + Safari MJPEG bugs). Do **not** put JPEG in the journal. Do **not** use multipart MJPEG in `<img>` for Control.

---

## 3. Invariants (non-negotiable)

1. Journal is the source of truth for “what happened”.
2. `seq` is monotone per process; never reuse.
3. **Never block `mj_step` / the driver on I/O.** Queue → consumer → `emit_*`.
4. Never drop `state_changed` or `command_*`.
5. Commands are idempotent on `clientCommandId`.
6. HTTP 200/202 ≠ physical success; confirmation is `command_applied` / `command_rejected` in the journal.
7. Dashboard must label data honestly: `provenance: "live" | "fixture" | "stale" | "absent"`.
8. UI buttons follow `/capabilities` — never hard-enable unsupported commands.

---

## 4. What to edit when integrating MuJoCo (checklist)

**Goal:** replace or complement `MockDriver` without rewriting the dashboard.

1. Keep `moon run sim:bridge` (HTTP process) running — or embed the same `Runtime`+`Journal` in-process with a background uvicorn thread (prefer same process boundaries as today unless you update this doc).
2. From the physics side, after a **stage transition** (not every substep):

   ```python
   from xfold.fsm import CellState
   # run_id from Runtime after launch / active run
   runtime.emit_state(run_id, CellState.PRESS, t=float(data.time))
   # anything an operator should see live (replaces print):
   runtime.emit_log(run_id, "platen closed", level="info", source="press", t=float(data.time))
   # when cycle completes:
   runtime.finish_success(run_id, t=float(data.time))
   ```

3. Respect pause/cancel: read the active run via `runtime.driver_active_run()` (or equivalent flags). If `paused` / `lifecycle == "paused"`, do not advance stages. If cancelled, stop emitting.
4. Put flatness (or other metrics) into `emit_state` / a dedicated metric path that still ends as `metric_sample` — do not invent a parallel `/telemetry` WebSocket.
5. Viewport = **separate** media plane: long-poll `GET /viewport/frame` (dashboard via `/api/bridge`). MJPEG `/viewport/stream` is legacy only. Do not jam JPEG into the journal. Set `viewportStream: true` when the producer is running; `viewportReady` when a frame exists.
6. Run: bridge up → `curl /snapshot` shows your states → dashboard badge “Bridge conectado”; with mujoco env, Control shows live 3D via `/viewport/stream`.
7. Note the change in `TRACKING.md` (decision or obstacle).

**Reference implementations:** [`press_driver.py`](../src/sim/src/xfold/bridge/press_driver.py) (live PressCycle) and [`mock_driver.py`](../src/sim/src/xfold/bridge/mock_driver.py) (fallback).

---

## 4b. Teammate tracks — arm sequence & cloth physics (agents)

Bridge/dashboard owners ship the **bus + Control UI + MJPEG viewport**. Other tracks keep ownership of physics and motion. Integrate at the Driver layer only.

### Arm / scripted cycle (FSM + UR5e / peel)

- **Do:** drive joints/mocap in your loop; on each **productive stage transition** call:

  ```python
  runtime.emit_state(run_id, CellState.FOLD, t=float(data.time))
  runtime.emit_log(run_id, "peel under collar", source="arm", t=float(data.time))
  # … later …
  runtime.finish_success(run_id, t=float(data.time))
  ```

- **Do:** route your `print`/`log` callback into `emit_log` so the dashboard console sees it (e.g. `Line(log=lambda m: runtime.emit_log(run_id, m, source="line"))`). Stage-level granularity; warnings/errors with the right `level`.
- **Do:** poll `runtime.driver_active_run()` — if `paused` / cancelled, do not advance.
- **Do not:** import FastAPI, open sockets from the physics thread, or change `@xfold/protocol` event names without syncing Python schema + this doc.
- **Reference:** replace `MockDriver` gradually; keep the same `emit_*` surface.

### Cloth / flexcomp (shirt physics)

- **Do:** iterate `flexcomp` (grid first) in your MJCF / scripts until stable 10s+; metrics → CSV when ready.
- **Do:** when the shirt should appear in Control’s 3D view, put it in the scene `SimSession` compiles (`xfold.line.build()`, else `scene.build()`). Viewport is render-only on that session.
- **Do not:** stream flex vertices over SSE; do not block the cloth solver on dashboard I/O.
- **Do not:** add a second independent MuJoCo loop for MJPEG — share `SimSession`.

### Shared scene etiquette

- Preserve `<camera name="overview"/>` (live viewport depends on it).
- Prefer **additive** bodies/geoms over renaming plant frames used by others.
- Live driver: `LineDriver` (fallbacks `PressBridgeDriver`, then `MockDriver`).
- Arm teammates: emit into the same `Runtime`; extend the press cycle or replace driver — do not fight the viewport render thread.

### Viewport vs journal vs recording

| Channel | Carries | Owner concern |
|---------|---------|----------------|
| Journal + SSE | FSM stage, metrics, commands, **log lines** | Arm emits stages + logs; cloth may later emit flatness |
| `GET /viewport/frame` (long-poll) | Live JPEG from shared `SimSession` | Primary UI path; Next `/api/bridge` proxy |
| `GET /viewport/stream` | Legacy multipart MJPEG | curl/VLC only |
| `GET /runs/{id}/recording/frame?t=` | Replay seek JPEG + FSM state | NPZ trajectory; badge must say **Replay**, never live |

**Shared session:** [`sim_session.py`](../src/sim/src/xfold/bridge/sim_session.py). Drivers call `runtime.emit_state(..., t=float(data.time))`. Do not invent a second MjData for the live viewport.

Do **not** add WebSocket or gRPC to the browser without an explicit team decision in `TRACKING.md` and an update to this contract.

---

## 5. What NOT to do

| Forbidden | Do instead |
|-----------|------------|
| `fetch` from Next to a one-off Python script / stdout scrape | Use the bridge |
| Put FSM or command logic in `app.py` routes | Put it in `Runtime` |
| Change event field names only in TS or only in Python | Both + this contract + check script |
| Fake live camera with the design mockup | Keep `viewportStream: false` + honest UI |
| Present fixtures as live when bridge is down | `provenance: "fixture"` |
| Add ROS / Isaac / gRPC-Web “because integration” | Out of scope until team agrees in TRACKING |

---

## 6. Offline vs live (dashboard)

| Condition | Behavior |
|-----------|----------|
| `GET /health` fails | `source: "fixture"` — local demo data; scenario toggles allowed |
| Health OK + SSE | `source: "live"` — real journal; scenario toggles hidden |
| SSE drops mid-session | `connection: "disconnected"`, last snapshot `stale`, commands disabled |

Env (optional): `NEXT_PUBLIC_XFOLD_BRIDGE_URL` (default `http://127.0.0.1:8765`).

---

## 7. Agent / teammate playbook

**Before coding:**

1. Read this file end-to-end.
2. Skim [`BRIDGE.md`](BRIDGE.md) for routes/events.
3. Identify which **layer** you are in (driver / runtime / HTTP / UI).

**If adding a journal event or command:** follow the checklists in `BRIDGE.md` (“How to add…”) and sync protocol ↔ schema.

**If wiring MuJoCo:** only §4 of this file — do not redesign the bus.

**If unsure:** prefer extending `Runtime.emit_*` + a journal `type` over a new transport.

---

## 8. Quick commands

```bash
moon run pack                # bridge + dashboard
# or:
moon run sim:bridge
curl -s http://127.0.0.1:8765/health
bash scripts/check-bridge-contract.sh
moon run dashboard:dev
```

OpenAPI: http://127.0.0.1:8765/docs
