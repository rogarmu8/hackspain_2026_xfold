"""Headless smoke: flex shirt drops onto the press and stays stable ~10 s."""

from __future__ import annotations

import sys

import numpy as np

from xfold.shirt import (
    aabb_overlaps_press,
    flatness,
    load_cell_model,
    shirt_vertex_positions,
)

SIM_TIME_S = 10.0
MAX_SPEED = 2.0  # m/s — anything higher after settle means explosion


def main() -> None:
    try:
        import mujoco
    except ImportError:
        raise SystemExit(
            "MuJoCo is not installed in this env.\n"
            "From the repo root run:  moon run install-mujoco"
        )

    model, data = load_cell_model()
    if model.nflexvert == 0:
        raise SystemExit("FAIL: no flex vertices — shirt.xml missing from cell?")

    steps = int(SIM_TIME_S / model.opt.timestep)
    print(
        f"# shirt smoke  nflexvert={model.nflexvert}  "
        f"dt={model.opt.timestep}  steps={steps}",
        flush=True,
    )

    for i in range(steps):
        mujoco.mj_step(model, data)
        if not np.isfinite(data.flexvert_xpos).all():
            raise SystemExit(f"FAIL: non-finite flexvert_xpos at step {i}")
        if data.qvel.size and not np.isfinite(data.qvel).all():
            raise SystemExit(f"FAIL: non-finite qvel at step {i}")

    pos = shirt_vertex_positions(model, data)
    speed = float(np.abs(data.qvel).max()) if data.qvel.size else 0.0
    flat = flatness(model, data)
    on_press = aabb_overlaps_press(model, data)

    print(
        f"flatness={flat:.6f}  max|qvel|={speed:.4f}  "
        f"z=[{pos[:, 2].min():.3f},{pos[:, 2].max():.3f}]  "
        f"on_press={on_press}",
        flush=True,
    )

    if speed > MAX_SPEED:
        raise SystemExit(f"FAIL: max|qvel|={speed:.3f} > {MAX_SPEED} (diverged)")
    if not on_press:
        raise SystemExit("FAIL: shirt AABB does not overlap press bed")

    print("OK: shirt stable for 10 s", flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — surface as smoke failure
        print(f"FAIL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
