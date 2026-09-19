# XFOLD — Integration contract (sim ↔ dashboard)

**Read this before changing anything that moves data between the simulator and the monitor.**

This is the binding contract for humans and agents. Implementation detail and rationale live in [`BRIDGE.md`](BRIDGE.md). Types live in [`packages/protocol/src/index.ts`](../packages/protocol/src/index.ts) and [`src/sim/src/xfold/bridge/schema.py`](../src/sim/src/xfold/bridge/schema.py).

If you change the contract, you **must** update: protocol TS → Python schema → this file → `BRIDGE.md` event/route tables → run `scripts/check-bridge-contract.sh`.

---

## 0. One-sentence model

> The **physics / FSM driver** emits **journal facts** into **Runtime**; the **bridge HTTP** exposes that journal (SSE) and accepts commands (REST); the **dashboard** renders snapshots and never talks to MuJoCo directly.

The sim does **not** need to be finished for this to work. Today `MockDriver` fakes the process. Tomorrow MuJoCo calls the **same** `Runtime.emit_*` API.

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

### Shared package

- TypeScript: `@xfold/protocol` — **canonical names** for agents generating code.
- Python: `xfold.bridge.schema` — must match (hackathon: hand-sync; verify with `bash scripts/check-bridge-contract.sh`).

### Telemetry snapshot fields (unchanged shape)

`t`, `state`, `cycle`, `flatness`, `shirt_in_bag` — see `Telemetry` in protocol.

### Journal events (append-only facts)

| `type` | When to emit |
|--------|----------------|
| `run_started` | Run enters running |
| `state_changed` | FSM stage changes (`PICK`…`BAG`) |
| `metric_sample` | Metrics tick (may be coalesced; never instead of `state_changed`) |
| `run_finished` | Terminal lifecycle |
| `command_accepted` / `command_rejected` / `command_applied` | Command pipeline |
| `batch_updated` | Batch counters / active child |

Every event has: `seq`, `tsIso`, `type`, `runId`, `batchId`.

### REST (commands & reads)

| Method | Path | Use |
|--------|------|-----|
| GET | `/health` | Dashboard probe |
| GET | `/capabilities` | What UI may enable |
| GET | `/snapshot` | Control-room materialization |
| GET | `/events/stream?after_seq=N` | Live journal (SSE) |
| POST | `/runs`, `/batches` | Launch |
| POST | `/commands` | `{ clientCommandId, kind, runId?, batchId? }` |

Do **not** add WebSocket or gRPC to the browser without an explicit team decision recorded in `TRACKING.md` and an update to this contract.

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
   # when cycle completes:
   runtime.finish_success(run_id, t=float(data.time))
   ```

3. Respect pause/cancel: read the active run via `runtime.driver_active_run()` (or equivalent flags). If `paused` / `lifecycle == "paused"`, do not advance stages. If cancelled, stop emitting.
4. Put flatness (or other metrics) into `emit_state` / a dedicated metric path that still ends as `metric_sample` — do not invent a parallel `/telemetry` WebSocket.
5. Viewport = **separate** image channel (`GET /viewport/stream` MJPEG). Do not jam JPEG into the journal. Set `viewportStream: true` only when MuJoCo Renderer is actually producing frames.
6. Run: bridge up → `curl /snapshot` shows your states → dashboard badge “Bridge conectado”; with mujoco env, Control shows live 3D via `/viewport/stream`.
7. Note the change in `TRACKING.md` (decision or obstacle).

**Reference implementation to copy:** [`src/sim/src/xfold/bridge/mock_driver.py`](../src/sim/src/xfold/bridge/mock_driver.py).

---

## 4b. Teammate tracks — arm sequence & cloth physics (agents)

Bridge/dashboard owners ship the **bus + Control UI + MJPEG viewport**. Other tracks keep ownership of physics and motion. Integrate at the Driver layer only.

### Arm / scripted cycle (FSM + UR5e / peel)

- **Do:** drive joints/mocap in your loop; on each **productive stage transition** call:

  ```python
  runtime.emit_state(run_id, CellState.FOLD, t=float(data.time))
  # … later …
  runtime.finish_success(run_id, t=float(data.time))
  ```

- **Do:** poll `runtime.driver_active_run()` — if `paused` / cancelled, do not advance.
- **Do not:** import FastAPI, open sockets from the physics thread, or change `@xfold/protocol` event names without syncing Python schema + this doc.
- **Reference:** replace `MockDriver` gradually; keep the same `emit_*` surface.

### Cloth / flexcomp (shirt physics)

- **Do:** iterate `flexcomp` (grid first) in your MJCF / scripts until stable 10s+; metrics → CSV when ready.
- **Do:** when the shirt should appear in Control’s 3D view, ensure it lives in the model rendered by `viewport_mujoco.MODEL_PATH` (today [`src/sim/models/cell.xml`](../src/sim/models/cell.xml)), **or** change `MODEL_PATH` once and note it in `TRACKING.md`.
- **Do not:** stream flex vertices over SSE; do not block the cloth solver on dashboard I/O.
- **Stub note:** `shirt_proxy` (blue box + `shirt_free`) is a **placeholder** for the viewport/MockDriver. Prefer adding real cloth beside it, then remove the proxy when cloth is demo-ready.

### Shared `cell.xml` etiquette

- Preserve `<camera name="overview"/>` (viewport MJPEG depends on it).
- Prefer **additive** bodies/geoms over renaming plant frames used by others.
- If you must rename `shirt_free` / `shirt_proxy`, update `_STAGE_POSE` in `viewport_mujoco.py` or delete that pose hack once real cloth/arm drive the scene.

### Viewport vs journal

| Channel | Carries | Owner concern |
|---------|---------|----------------|
| Journal + SSE | FSM stage, metrics, commands | Arm emits stages; cloth may later emit flatness |
| `GET /viewport/stream` | JPEG frames from `mujoco.Renderer` | Whoever owns the loaded MJCF scene |

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
moon run dev                 # bridge + dashboard together
# or:
moon run sim:bridge
moon run dashboard:dev
curl -s http://127.0.0.1:8765/health
curl -sI http://127.0.0.1:8765/viewport/frame
bash scripts/check-bridge-contract.sh
```

OpenAPI: http://127.0.0.1:8765/docs · Viewport: `/viewport/stream`
