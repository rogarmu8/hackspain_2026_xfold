# AGENTS.md — contexto para Cursor

You are helping the XFOLD HackSpain '26 team. Read `SOLUTION.md` before inventing architecture.

## Integration (sim ↔ dashboard) — mandatory

**Binding contract:** [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md)  
**Transport/detail:** [`docs/BRIDGE.md`](docs/BRIDGE.md)  
**Types:** `packages/protocol` ↔ `src/sim/src/xfold/bridge/schema.py` (`bash scripts/check-bridge-contract.sh`)

Before wiring MuJoCo or changing live data: follow the contract checklist (Driver → Runtime → HTTP → UI). Do not scrape sim stdout from Next, and do not add WebSocket/gRPC to the browser without updating those docs + `TRACKING.md`.

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
src/sim/src/xfold/bridge/   # journal + runtime + HTTP + MockDriver
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

## When stuck

Document the obstacle in `TRACKING.md` (Eje A). Prefer the nuclear fallback in `SOLUTION.md` §10 (scripted mocap suction + machines, no arm) over a broken Panda.
