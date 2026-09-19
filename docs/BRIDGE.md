# XFOLD bridge — journal + REST/SSE

> **Agents & teammates:** the binding integration contract is  
> [`INTEGRATION_CONTRACT.md`](INTEGRATION_CONTRACT.md).  
> This file is the detailed companion (routes, events, how-tos).

Source of truth for **sim ↔ dashboard** communication transport and event catalogue.

The physics loop (today: mock FSM; later: MuJoCo) never talks to the browser
directly. It appends **facts** to an append-only **journal**. A small HTTP
process exposes that journal over **SSE** and accepts **REST** commands.

```text
LineDriver / PressBridgeDriver / MockDriver   Runtime      Journal       Browser
     │                          │                    │                  │
     │  emit_state / finish     │                    │                  │
     │─────────────────────────►│  append(event)     │                  │
     │                          │───────────────────►│                  │
     │                          │                    │  SSE /events     │
     │                          │                    │─────────────────►│
     │                          │◄── POST /commands ────────────────────│
     │                          │  command_* events  │                  │
     │                          │───────────────────►│─────────────────►│
```

Live physics uses a shared **`SimSession`** (`MjModel`/`MjData`). The Driver
advances it; the viewport only **renders**. Trajectory NPZ under
`data/trajectories/` powers replay seek (`recording/frame?t=`) — never JPEG in the journal.

`SimSession` picks the best scene that compiles, and the driver follows it
(`GET /capabilities` reports both as `scene` and `driver`):

| `scene` | what it is | driver |
|---|---|---|
| `line` | `line.xml` — belt, press, flap folder, bagger | `LineDriver` |
| `press_cell` | the older arm cell | `PressBridgeDriver` |
| `stub` | `cell.xml`; renders, nothing drives it | `MockDriver` |
| *(none)* | MuJoCo missing | `MockDriver` |

Offscreen GL is probed once at startup. Without it the bridge keeps serving the
journal with `viewportStream: false` — the dashboard shows the FSM and the live
console, just no video — instead of taking the process down with it.

**QC station.** Just past the press, the belt stops the pressed garment under
`qc_cam`, the line's own lights dip to `QC_DIP` and two flash heads fire. The
Driver renders one square 768 px frame at the top of the flash and writes it to
`data/photos/{run}.jpg`; the run detail then carries `hasPhoto: true` and the
dashboard shows it. The dip is not decoration: the overview lighting blows a
white garment to flat white from 1 m up, taking the print and any stain with
it. The image is a file, never a journal event — same rule as the viewport.

`LineDriver` logs which input a cycle got as its first console line and stores the effective per-run garment, mesh, texture, condition and seed usage in `run.config.inputs`.

### Simulator-defined process (0.2)

`xfold.line.LINE_PHASES` is the sole line phase catalogue. The driver registers it with Runtime and forwards `Line.on_event` observations; the browser consumes `run.stages` and simulator labels. `/capabilities.process` advertises the scenario/catalogue/seed support before launch; `run_started` journals `stages`, `inputs` and `driver` for traceability. The old six-state mapping is no longer used for the line. Main phases distinguish conveyor trips (including `TO_QC`), the `PHOTO` stop, insertion, sealing and completion. Photo outcomes (`PHOTO_SAVED`, `PHOTO_UNAVAILABLE`, `PHOTO_FAILED`) retain structured phase/station/timestamp context; unavailable/failed captures are warnings. Flatness post is sampled immediately after the press raises, before transport to QC. Sub-operations distinguish each flap, press motion and peel action. Bag preparation logs `parallel: true`, without advancing the main phase.

Structured log context: `stage`, `operation`, `station`, `parallel`, plus existing `source`, `level`, `t`. Run snapshots preserve it for history/reconnect. The console uses complete `run.events` plus journal command events, rather than replacing history with a partial SSE tail. SSE cursors advance only on received events; snapshot sequence numbers cannot skip unread facts. Snapshot refreshes are coalesced and a 1 Hz refresh keeps the sim clock current between observations.

Metrics are observations only: z-standard-deviation before/after the press (`flatnessPreM`, `flatnessPostM`) and folded AABB dimensions (`packLengthM`, `packWidthM`, `packHeightM`). All units are metres on the wire. No hard-coded flatness or bag success; unknown containment is null. Completing the script is not quality validation. Wall time includes pauses. The process advertises seed support; each run records whether selection, stain variant or skewed pose actually uses it. Fixed clean/torn selections do not vary with seed. `spawnYawRad` and `spawnOffsetYM` record the actual seeded heading and lateral offset at LOAD.

Timeline final markers have no phase. Replay follows the supplied phase catalogue, including failed/cancelled endings, and labels qpos-only line reconstruction as partial. The console silence warning means **no signal**, not physical jam detection. Full replay fidelity, durable restart recovery and measured progress/quality gates are not implemented by this change.

The line's input garment is chosen at **launch**, not only at process start.
`POST /runs` and `POST /batches` carry cloth type + condition; `random` draws
use `seed` and optional `clothTypeWeights` / `clothConditionWeights` (0 = never).
`LineDriver` calls `select_garment` and rebuilds the shared `SimSession` when
the SKU mesh or texture changes. Pose-only `skewed` does not rebuild: the shirt
stays flat on the belt and `seed` picks the heading. `GET /capabilities` lists
`clothTypes` and `clothConditions` for the dashboard form. `XFOLD_GARMENT`
and `[garment] type` in `shirt.toml` remain the compile-time default.

## Why this shape (and not WS / gRPC)

| Need | Choice |
|------|--------|
| Discrete FSM + rare operator commands | Event journal, not a dense full-duplex pipe |
| Command ack / 4xx / idempotency | REST (`POST /commands`) |
| Live UI + reconnect | SSE (`GET /events/stream`) |
| Browser client | No gRPC-Web proxy; no custom WS framing |
| Demo-day debug | `curl` + OpenAPI at `/docs` |

WebSocket remains reserved for denser viewport protocols later; **today** the live 3D view is **MJPEG** over HTTP (`GET /viewport/stream`), which works in a plain `<img>` without a second bus. gRPC is fine later between Python workers — not to the Next.js UI.

## Run

From the repo root (Pixi + moon already set up):

```bash
moon run pack                # bridge (:8765) + dashboard (:3000) together
# or separately:
moon run sim:bridge          # http://127.0.0.1:8765  · OpenAPI /docs
moon run dashboard:dev       # probes the bridge; fixtures if offline
```

Optional dashboard env ([`src/dashboard/.env.example`](../src/dashboard/.env.example)):

```bash
NEXT_PUBLIC_XFOLD_BRIDGE_URL=http://127.0.0.1:8765
```

If unset, the UI still probes `http://127.0.0.1:8765`. If `/health` fails, it
keeps using local **fixtures** (honest `provenance: "fixture"`).

### Smoke

```bash
curl -s http://127.0.0.1:8765/health
curl -s -X POST http://127.0.0.1:8765/runs \
  -H 'content-type: application/json' \
  -d '{"name":"demo","seed":1,"scenario":"mock","clothType":"tee","clothCondition":"good"}'
curl -sN 'http://127.0.0.1:8765/events/stream?after_seq=0'
```

## HTTP API

| Method | Path | Role |
|--------|------|------|
| `GET` | `/health` | Liveness |
| `GET` | `/capabilities` | What the UI may enable |
| `GET` | `/snapshot` | Materialized control-room snapshot |
| `GET` | `/runs`, `/runs/{id}` | Run list / detail |
| `GET` | `/batches/{id}` | Batch summary |
| `GET` | `/experiments` | Launch list for Experimentos |
| `POST` | `/runs`, `/batches` | Launch individual / batch |
| `POST` | `/commands` | Operator command (`202` / `409`) |
| `GET` | `/viewport/meta` | Readiness: `seq`, `ageMs`, `source`, `available` |
| `GET` | `/viewport/frame?after_seq=&wait_ms=` | **Primary** live view — long-poll JPEG (+ `X-Viewport-Seq`) |
| `GET` | `/viewport/stream` | Legacy multipart MJPEG (curl/VLC only; dashboard must not use) |
| `GET` | `/runs/{id}/timeline` | FSM markers (`state_changed`) for scrubber |
| `GET` | `/runs/{id}/recording` | Trajectory meta (`tMax`, `hasTrajectory`, …) |
| `GET` | `/runs/{id}/recording/frame?t=` | Seek nearest sample → JPEG base64 + `state` |
| `GET` | `/runs/{id}/photo` | QC camera's product shot (JPEG, 404 until the flash fires) |
| `GET` | `/events/stream?after_seq=N` | SSE journal (replay + live) |

### Viewport architecture (media plane)

```text
MuJoCo Renderer ──publish──► ViewportHub(seq, jpeg)
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
  GET /viewport/frame     GET /viewport/meta     GET /viewport/stream
  (long-poll, primary)    (status JSON)          (legacy MJPEG)
         │
         ▼
  Next /api/bridge/*  ←── same-origin proxy ──►  Dashboard <img>
```

Why not MJPEG-in-`<img>`? Safari/WebKit and several Chrome setups leave multipart
streams as a black box even when frames are valid. Long-poll JPEG is universal,
works with CORS/proxy, and keeps last-good-frame UX.

Dashboard hook: `useLiveViewport` — visibility pause, backoff, last frame, honest
`live|waiting|stale|offline` status.

Interactive schema: `http://127.0.0.1:8765/docs`.

### SSE frame format

```text
id: 12
data: {"seq":12,"tsIso":"...","type":"state_changed",...}

: keepalive
```

- `id` == `seq` (monotone, starts at 1).
- Reconnect with `after_seq=<last seen>` (query param; EventSource `Last-Event-ID` is optional later).

## Journal event catalogue

Shared TypeScript types live in [`packages/protocol/src/index.ts`](../packages/protocol/src/index.ts).
Python models live in [`src/sim/src/xfold/bridge/schema.py`](../src/sim/src/xfold/bridge/schema.py).
**Keep them in sync by hand** (hackathon; no protobuf codegen).

| `type` | Meaning |
|--------|---------|
| `run_started` | New run entered `running` |
| `state_changed` | Simulator phase entry (`state`, `label`, `station`, `t`, `cycle`); no fixed six-stage cycle for line |
| `metric_sample` | Measured metrics (`measurements` with unit-suffixed keys; nullable flatness/bag flag) |
| `run_finished` | Terminal lifecycle + reason |
| `command_accepted` | Command passed validation |
| `command_rejected` | Invalid / unsupported |
| `command_applied` | Side effects applied |
| `batch_updated` | Batch counters / active child run |
| `log` | Free-form simulator line for the dashboard **console** (`level`, `message`, `source`, `t`). Emit via `runtime.emit_log(...)`; never per physics step, never pixels/verts |

Envelope on every event: `seq`, `tsIso`, `runId`, `batchId`.

### Console (dashboard)

`bridge-client` keeps a ring buffer (2000) of journal facts; `ControlRoom` renders them for the open run in `ConsolePanel` (`src/dashboard/src/lib/console.ts` maps each `type` to a line; `metric_sample`/`batch_updated` are hidden). A UI **silence watchdog** flags a `running` run with no console fact for `STALL_AFTER_S` (8 s). It is a signal-health warning, not a physical stall detector; heartbeats do not prove material progress.

## Invariants

1. **Journal is the source of truth** for “what happened”. Snapshots are a
   fold of state for the UI, not a second bus.
2. **`seq` is monotone** and never reused in a process lifetime.
3. **Do not block the driver/physics on network.** The mock driver only calls
   `Runtime.emit_*` / waits on an in-process wake event. SSE subscribers must
   not stall append (fan-out via queues).
4. **Never drop** `state_changed` or `command_*`. Metric samples may be
   coalesced *before* append if rates grow.
5. **Commands are idempotent** on `clientCommandId` (duplicates return
   `status: "duplicate"` without re-applying).
6. **Confirmation is a journal fact** (`command_applied` / `command_rejected`),
   not “HTTP 200 means cloth moved”.

## Module map (Python)

| File | Responsibility |
|------|----------------|
| `bridge/journal.py` | Thread-safe log + optional JSONL under `data/journal/` |
| `bridge/runtime.py` | Runs/batches, command apply, snapshot |
| `bridge/mock_driver.py` | Background PICK→BAG walker |
| `bridge/app.py` | FastAPI routes + CORS for localhost UI |
| `bridge/schema.py` | Wire models (sync with protocol) |

## Dashboard wiring

| File | Role |
|------|------|
| `src/dashboard/src/lib/bridge-client.ts` | `fetch` + `EventSource` |
| `src/dashboard/src/lib/dashboard-context.tsx` | Probes bridge → `source: "live" \| "fixture"` |
| `src/dashboard/src/lib/adapter.ts` | Fixture-only demo when offline |

The control room consumes the same `ControlSnapshot` either way. Fixture
scenario toggles are hidden while live.

## How to add a new journal fact

1. Add the discriminant to `JOURNAL_EVENT_TYPES` in `@xfold/protocol`.
2. Mirror the payload fields in `xfold.bridge.schema` / `Journal.append(...)`.
3. Emit from `Runtime` (not from `app.py`).
4. Document the row in the catalogue above.
5. If the UI must react, handle it in `BridgeClient.applyEvent` / snapshot refresh.

## How to add a new command

1. Add to `COMMAND_KINDS` in protocol + `capabilities.commands`.
2. Validate + apply in `Runtime.handle_command` / `_apply_command_locked`.
3. Dashboard `CommandKind` / panel buttons follow capabilities (never hard-enable).

## Hooking MuJoCo later

Keep the HTTP process. From the viewer loop (or a worker thread):

```python
# after a stage transition — never inside a tight mj_step without a queue
runtime.emit_state(run_id, CellState.PRESS, t=data.time)
```

Prefer a `queue.SimpleQueue` from the physics thread → a thin consumer that
calls `runtime.emit_*`, same as today’s mock driver pattern.

## Persistence

When enabled, events append to `data/journal/events.jsonl` (gitignored via
`data/`). Enough for hackathon replay; not a durable multi-node store.
