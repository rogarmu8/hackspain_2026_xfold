# AGENTS.md — context for Cursor

You are helping the XFOLD HackSpain '26 team. Read `SOLUTION.md` before inventing architecture. The running simulation is authoritative for the current process: `xfold.line.LINE_PHASES` + `Line.on_event`. Older design prose and legacy fixtures must not override its phases or measurements.

## Language

Operator-facing copy is **English**: dashboard UI, HTTP/validation errors, and console logs the operator sees (`Line`, `LineDriver`, `runtime.emit_log`). Do not add Spanish strings there. Internal comments and docs may stay mixed.

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
| **Press / line** | `xfold/line.py`, `line.xml`, `shirt.*` | **Source of truth:** `xfold.line.LINE_PHASES` + `Line.on_event`. [`line_driver.py`](src/sim/src/xfold/bridge/line_driver.py) only forwards observations into Runtime. Add phases/operations in the simulation, not a parallel map in the bridge/UI. Unmeasured metrics = null. |
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
- `XFOLD_TEST_PHYSICS=1 pixi run -e mujoco python -B scripts/test-sim-observability.py` — isolated full headless cycle (no live server commands or trajectory overwrite).
- `node scripts/test-dashboard-observability.mjs` — replay, labels, console history, SSE cursor and snapshot coalescing.
- `bash scripts/check-bridge-contract.sh` — event/command names only; not semantic correctness.
- `./node_modules/.bin/tsc --noEmit --incremental false -p src/dashboard/tsconfig.json` and `npm run lint --workspace @xfold/dashboard`.

## Experimental cloth contact in the main line

- Default remains `legacy`. Main viewer: `moon run sim:run -- --cloth-contact partitioned -g tee --cycles 1`. Bridge + dashboard: `XFOLD_CLOTH_CONTACT=partitioned moon run pack`. Set `legacy` or omit the variable to revert. Restart the bridge to change this session-level preset; there is no new REST command or launch-form field.
- `SimSession` preserves the selected contact mode across garment rebuilds. `run.config.inputs` / `run_started.inputs` expose `clothContactMode`, configured `clothContactPatchTriangles`, `clothLayerProjection`, and `clothScriptedMotion`. Actual vertex/patch counts are logged per compiled garment, not stored as stale startup counts for every SKU.
- Collision bit 8 is reserved for line cloth patches; bit 4 remains the bag hull. Patches share original shirt bodies and have no elastic/edge damping of their own. Steam damping, position control, measurements and camera tracking must use `shirt_flex_id`, `shirt_vertex_slice`, `shirt_vertex_bodies` / `shirt_vertex_positions`, not all flex vertices. Experimental mode never instantiates `ClothLayers`.
- This is contact integration only: the existing conveyor, press morph, flap carrying and bag attachment remain script-assisted. It does not introduce the lab's physical folder or a hollow/sewn garment. Numerical warnings/non-finite state fail experimental runs; explicit experimental compile failures do not select the old arm plant as a silent physical fallback.
- Full regression: `XFOLD_TEST_PHYSICS=1 XFOLD_TEST_RENDER=1 pixi run -e mujoco python -B scripts/test-sim-observability.py`. It covers both contact modes, seeded spawn, complete cycles, reset, pause/resume/cancel, garment rebuilds and live/replay JPEG rendering. Tests load scene XML through `MjVfs` and mock recorder IO rather than overwriting live generated includes or trajectories.
- Completed sequences are not valid folds: initial partitioned runs measured roughly 131 mm pack height for tee and 577 mm for a skewed jersey. Scripted trajectories can oppose native contact forces; mode remains opt-in. Compaction and a physical replacement for the controller remain separate work.

## Isolated cloth physics lab

- Requires MuJoCo **3.13+**. `xfold.cloth_lab` loads `models/cloth_lab.xml` in memory; it does not change `Line`, the bridge, or generated live garment includes. No new dependencies.
- Tests: `pixi run -e mujoco python -B scripts/test-cloth-lab.py`. Multilayer physical regression: `XFOLD_TEST_MULTILAYER=1 pixi run -e mujoco python -B scripts/test-cloth-lab.py` (reproduces the unpartitioned failure, then checks two partitioned cases).
- Headless comparison: `pixi run -e mujoco python -B -m xfold.cloth_lab --scenario layers --duration 2 --compare` (four contact modes × two integrators).
- Multilayer viewer: `moon run sim:cloth-lab -- --scenario layers --contact partitioned --viewer --edge-timeconst 0.005 --timestep 0.002 --duration 2`.
- Physical T-shirt flap viewer: `moon run sim:cloth-lab -- --scenario flap --mesh tee --contact partitioned --viewer --edge-timeconst 0.005 --timestep 0.001`.
- Three-panel trial: `moon run sim:cloth-lab -- --scenario fold --mesh tee --contact partitioned --viewer --edge-timeconst 0.005 --contact-timeconst 0.002 --timestep 0.001`. Default duration is 18.5 simulated seconds, also through `LabConfig(scenario='fold')`; other scenarios remain at 5.5 s. Explicit `--duration` can stop at an intermediate stage.
- `fold` has three hinges (8 Nm actuator limits) and three physical lift axes (40 N, 80 mm travel). It closes left/right/hem sequentially, raises each panel before return, keeps that clearance while opening, then lowers the open panel. Collisions remain enabled. Machine dimensions are fitted to the selected mesh's rest bounds: this is a separate fixture per mesh, not proof of one fixed machine handling all garments.
- Fold controls: `--fold-angle` is radians (default 2.95, maximum pi); `--fold-clearance-scale` scales closing-axis lifts and `--fold-return-clearance` adds withdrawal lift (default 0.025 m). Requested lifts exceeding travel are rejected. The stronger contact setting above reduced the initial thin-panel penetration problem; it is not a calibrated material preset.
- Fold output includes `left`, `right`, `hem` checkpoints after return/settle, panel poses/torques, per-region crossing fractions and packet footprint coverage. `folder_schedule_completed` only means the timed program ended. `folder_footprint_target_met` checks 95% of vertices within the target XY rectangle with a 2-radius tolerance; `folder_height_target_met` checks vertex Z span against 14 collision radii (42 mm by default). These are diagnostic thresholds, not a physical-success certificate.
- Use `--mesh tee` for the existing shirt silhouette; the default is a 0.48 m square grid. `layers` requires a grid and initializes a connected sheet in a pre-folded pose, with measured initial strain; it does not demonstrate how the folds were obtained.
- Contact variants: `proxy` = vertex spheres against machines, no self-contact; `hybrid` = those spheres plus native flex self-contact; `native` = native flex contacts only; `partitioned` = sphere support plus native collision-only flex patches sharing the original cloth bodies. `--patch-triangles 8` is the default patch size. Each face belongs to exactly one collision patch; the original flex retains all elasticity/equalities and rendering, with its collisions disabled. No additional masses, joints, seams or positional corrections are added. None uses `ClothLayers` or cloth state projection after initialization. The flap uses a torque-limited position actuator and keeps its collisions active on return.
- Partitioned contact preserves the per-pair engine limit, but distributes contacts among patch pairs. `peak_self_contacts` is the aggregate; `peak_self_contact_pair_contacts` and `self_contact_cap_reached` detect per-pair saturation. Larger patches can still saturate. Only the expected compiler warning about collision-only `shirt_contact_*` flexes lacking their own elasticity/equalities is filtered; all numerical warnings still fail the experiment. Geometry metrics use the original cloth only, not duplicated collider vertices.
- Material variants: `--material edge|vert|elastic`; integrators: `--integrator Euler|discrete`; solvers: `--solver CG|Newton`. `--compare` varies contact and integrator only. `--edge-timeconst` controls equality compliance, not Young's modulus. MuJoCo 3.13 rejects elastic flexes under `implicitfast`; do not use older implicit-integration recipes.
- Results: fresh directories under `data/cloth-lab/`, with `samples.csv` and `summary.json` (config, versions, hashes, initial/final samples). Existing output directories are never overwritten. Physics-only timing excludes diagnostics/rendering; experiment timing includes diagnostics and viewer pacing but excludes construction.
- MuJoCo fatal step errors (including exhausted solver memory) produce a failed result with the error and contact count; invalid state is not sampled again. On failure, `final` is the last valid sampled measurement, not a recovered final state.
- `numerically_valid` is only a run/warning check, not physical success. Triangle intersection counts are sampled, exclude shared-vertex and degenerate triangles, and are not continuous collision detection. Retained-contact penetration cannot reveal contacts discarded by the engine. Materials are uncalibrated and `physical_success` stays null.
- M4 findings: unpartitioned native self-contact still intersects in three layers and the 384-vertex T-shirt. With eight-triangle collision patches, the tested two/three-layer trials and one T-shirt flap trial had zero sampled intersections at 20 ms intervals. Three-layer checks covered seeds 42/43 at 1/2 ms and seed 42 at 0.5 ms; the T-shirt check used seed 42 at 1 ms. No continuous non-penetration or sim-to-real guarantee. The shirt still has transient stretch and is slower than real time. Keep this as an experimental track, not a replacement for the working demo. See `TRACKING.md`.

- Three-panel findings: reference T-shirt trial at 2.95 rad, seed 42, 1 ms, contact time constant 2 ms, edge time constant 5 ms had zero sampled intersections (50 ms samples), 98.4% final footprint coverage, but 112 mm height: **compact folding is not validated**. Closing at pi reduced coverage to 93.2% without fixing height. The 169-vertex grid lost the hem fold. Enabling native triangle-machine contact in a prototype did not fix the sequence; reducing only self friction to 0.2 exhausted the solver arena (35,335 contacts) and was not adopted. Do not integrate this trial into `Line` as a successful cycle.

## When stuck

Document the obstacle in `TRACKING.md` (Eje A). Prefer the nuclear fallback in `SOLUTION.md` §10 (scripted mocap suction + machines, no arm) over a broken Panda.
