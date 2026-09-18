# AGENTS.md — contexto para Cursor

You are helping the XFOLD HackSpain '26 team. Read `SOLUTION.md` before inventing architecture.

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

## Repo layout

```
models/           # MJCF assets
robots/           # Menagerie overlays / UR5e attach
xfold/
  scene.py
  shirt.py
  perceive.py
  metrics.py
  control/
    fsm.py
    ik.py
    machines.py
scripts/
  demo.py
  eval.py
data/
```

## Done means

- Block criteria in `SOLUTION.md` §9 / `TRACKING.md`.
- Demo target: one unattended, repeatable full cycle.
- Stretch only after block 6: size variants / T-mesh.

## When stuck

Document the obstacle in `TRACKING.md` (Eje A). Prefer the nuclear fallback in `SOLUTION.md` §10 (scripted mocap suction + machines, no arm) over a broken Panda.
