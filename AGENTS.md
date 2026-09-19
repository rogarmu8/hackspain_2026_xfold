# AGENTS.md — contexto para Cursor

You are helping the XFOLD HackSpain '26 team. Read `SOLUTION.md` before inventing architecture. The running simulation is authoritative for the current process: `xfold.line.LINE_PHASES` + `Line.on_event`. Older design prose and legacy fixtures must not override its phases or measurements.

## Integration (sim ↔ dashboard) — mandatory

**Binding contract:** [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md)  
**Transport/detail:** [`docs/BRIDGE.md`](docs/BRIDGE.md)  
**Types:** `packages/protocol` ↔ `src/sim/src/xfold/bridge/schema.py` (`bash scripts/check-bridge-contract.sh`)

Before wiring MuJoCo or changing live data: follow the contract checklist (Driver → Runtime → HTTP → UI). Do not scrape sim stdout from Next, and do not add WebSocket/gRPC to the browser without updating those docs + `TRACKING.md`.

### For agents on other tracks (arm / cloth) — read this

Bridge + dashboard work does **not** own arm IK or `flexcomp` physics. Integrate by **emitting** into the existing Runtime; do not fork the bus.

| Your track | Own these paths | How to talk to the dashboard |
|------------|-----------------|------------------------------|
| **Arm / FSM sequence** | controller Python, Menagerie overlays, arm MJCF | After each **stage change**, call `runtime.emit_state(run_id, CellState.…, t=data.time)`. Copy [`mock_driver.py`](src/sim/src/xfold/bridge/mock_driver.py). Respect `runtime.driver_active_run()` pause/cancel. |
| **Press / line** | `xfold/line.py`, `line.xml`, `shirt.*` | **Fuente de verdad:** `xfold.line.LINE_PHASES` + `Line.on_event`. [`line_driver.py`](src/sim/src/xfold/bridge/line_driver.py) solo transmite observaciones al Runtime. Añade fases/operaciones en la simulación, no un mapa paralelo en bridge/UI. Métricas no medidas = null. |
| **Cloth / shirt physics** | `flexcomp` MJCF, cloth params, mesh later | Keep cloth stable in **your** model. When ready for Control 3D, either merge into the scene that [`viewport_mujoco.py`](src/sim/src/xfold/bridge/viewport_mujoco.py) loads (`MODEL_PATH`) **or** point `MODEL_PATH` at your XML. Do **not** put cloth verts in the journal. |
| **Shared plant stub** | [`src/sim/models/cell.xml`](src/sim/models/cell.xml) | Small shared file. Keep `camera name="overview"` and prefer additive bodies. If you replace `shirt_proxy`, update viewport pose map or stop using the proxy. Note merges in `TRACKING.md`. |

**Never:** redesign REST/SSE, put FSM in MJCF, block `mj_step` on HTTP, or invent a second browser transport.

Full teammate checklist: [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md) §4 and §4b.

## Product

Automate the human load/pack station around industrial shirt folding:

`bin → hot-air/platen press → FlipFold → output box`

Do **not** origami-fold cloth with fingers. Machines do geometry; the arm handles variability (pick, place, pack) with a pizza-peel + suction tool.

## Hard rules

1. Stack: **MuJoCo 3 + mink + Menagerie (UR5e) + Python FSM**. No ROS, no Isaac, no RL until a scripted end-to-end cycle works.
2. Cloth: MuJoCo `flexcomp` (start as **grid**, not mesh). Prefer stability over looks. If cloth explodes: coarser grid, `internal="false"`, lower Young, higher damping — do **not** add the arm.
3. XML = plant. Python = controller. Do not put the FSM in MJCF.
4. Stay inside your track's directories unless integrating (see `PLAN.md`).
5. Prefer small, runnable increments that open in `mujoco.viewer`.
6. Log metrics to CSV as soon as a loop exists (`xfold/metrics.py` → `data/`).
7. Sim↔dashboard bus: **journal + REST/SSE** only — see integration contract above.

## Repo layout

```
docs/
  INTEGRATION_CONTRACT.md   # binding sim↔UI contract (agents start here)
  BRIDGE.md                 # routes, events, invariants
src/sim/src/xfold/bridge/   # journal + runtime + HTTP + Line/Press/Mock drivers
src/dashboard/src/lib/      # bridge-client + fixtures fallback
packages/protocol/          # shared wire types
models/                     # MJCF assets
robots/                     # Menagerie overlays / UR5e attach
scripts/
  check-bridge-contract.sh
data/
```

## Done means

- Block criteria in `SOLUTION.md` §9 / `TRACKING.md`.
- Demo target: one unattended, repeatable full cycle.
- Stretch only after block 6: size variants / T-mesh.

## Observability verification

- `pixi run -e mujoco python -B scripts/test-sim-observability.py` — runtime/observer regression tests.
- `pixi run -e mujoco python -B scripts/test-fold-recipes.py` — QC fold-recipe choice and kinematic pack size for every SKU.
- `XFOLD_TEST_PHYSICS=1 pixi run -e mujoco python -B scripts/test-sim-observability.py` — isolated full headless cycle (no live server commands or trajectory overwrite).
- `node scripts/test-dashboard-observability.mjs` — replay, labels, console history, SSE cursor and snapshot coalescing.
- `bash scripts/check-bridge-contract.sh` — event/command names only; not semantic correctness.
- `./node_modules/.bin/tsc --noEmit --incremental false -p src/dashboard/tsconfig.json` and `npm run lint --workspace @xfold/dashboard`.

## When stuck

Document the obstacle in `TRACKING.md` (Eje A). Prefer the nuclear fallback in `SOLUTION.md` §10 (scripted mocap suction + machines, no arm) over a broken Panda.
