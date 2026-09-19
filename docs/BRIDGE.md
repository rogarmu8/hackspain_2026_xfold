# XFOLD bridge — journal + REST/SSE

> **Agents & teammates:** the binding integration contract is  
> [`INTEGRATION_CONTRACT.md`](INTEGRATION_CONTRACT.md).  
> This file is the detailed companion (routes, events, how-tos).

Source of truth for **sim ↔ dashboard** communication transport and event catalogue.

The physics loop (today: mock FSM; later: MuJoCo) never talks to the browser
directly. It appends **facts** to an append-only **journal**. A small HTTP
process exposes that journal over **SSE** and accepts **REST** commands.

```text
MockDriver / MuJoCo          Runtime              Journal           Browser
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
  -d '{"name":"demo","seed":1,"scenario":"mock"}'
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
| `GET` | `/viewport/stream` | Live MJPEG (MuJoCo `overview` camera) — `<img src>` |
| `GET` | `/viewport/frame` | Single latest JPEG/PNG frame |
| `GET` | `/events/stream?after_seq=N` | SSE journal (replay + live) |

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
| `state_changed` | FSM stage changed (`PICK`…`BAG`) |
| `metric_sample` | Throttled metrics (flatness, bag flag) |
| `run_finished` | Terminal lifecycle + reason |
| `command_accepted` | Command passed validation |
| `command_rejected` | Invalid / unsupported |
| `command_applied` | Side effects applied |
| `batch_updated` | Batch counters / active child run |

Envelope on every event: `seq`, `tsIso`, `runId`, `batchId`.

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
