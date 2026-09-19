"""Interactive shirt-only playground — drag the cloth and watch the physics."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

from xfold.shirt import (
    PLAYGROUND_HI_XML,
    PLAYGROUND_PONCHO_XML,
    PLAYGROUND_XML,
    load_mujoco_plugins,
)
from xfold.shirt_grab import (
    KEY_DOWN,
    KEY_E,
    KEY_G,
    KEY_LEFT,
    KEY_Q,
    KEY_R,
    KEY_RIGHT,
    KEY_SPACE,
    KEY_UP,
    KEY_X,
    ClothGrab,
    camera_axes,
)

CONTROLS = """
XFOLD shirt playground — CLOTH3D T-shirt (cloth physics)
--------------------------------------------------------
Trackpad friendly — no right-click needed.

  G            grab / release the shirt
               (grabs the vertex you double-clicked, else the highest one)
  arrows       steer the grab across the floor, relative to the camera
  E / Q        lift / lower the grab
  X            stop moving
  R            reset the shirt
  Space        pause

  Orbit camera   left-drag        Pan   Shift + left-drag
  Zoom           scroll           Select a vertex   double-click

Each arrow tap adds speed (the viewer gives us no key-repeat), so tap a few
times to pull faster and tap X to stop.
"""


def _reexec_mjpython_on_macos(extra_args: list[str]) -> None:
    if sys.platform != "darwin":
        return
    try:
        from mujoco import viewer as mujoco_viewer

        if isinstance(
            getattr(mujoco_viewer, "_MJPYTHON", None),
            getattr(mujoco_viewer, "_MjPythonBase", type),
        ):
            return
    except ImportError:
        return

    mjpython = Path(sys.executable).resolve().parent / "mjpython"
    if not mjpython.is_file():
        raise SystemExit(
            "On macOS the viewer must run under mjpython.\n"
            "From the repo root:  moon run install-mujoco && moon run sim:shirt-play"
        )
    os.execv(
        os.fsdecode(mjpython),
        [os.fsdecode(mjpython), "-m", "xfold.shirt_play", *extra_args],
    )


def _configure_viewer(viewer, model) -> None:
    """Free camera + visible flex verts so double-click selection works."""
    import mujoco

    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    viewer.cam.lookat[:] = model.stat.center
    viewer.cam.distance = float(model.stat.extent) * 1.6
    viewer.cam.azimuth = 135
    viewer.cam.elevation = -25

    # Flex picking needs at least one flex visualisation flag enabled.
    viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_FLEXVERT] = 1
    viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_FLEXEDGE] = 1
    viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_FLEXSKIN] = 1
    viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_PERTFORCE] = 1


def _draw_grab_marker(viewer, grab) -> None:
    """Show where the grab target is, so the pull is not invisible."""
    import mujoco

    scene = viewer.user_scn
    if scene is None:
        return
    scene.ngeom = 0
    if not grab.active:
        return
    mujoco.mjv_initGeom(
        scene.geoms[0],
        type=mujoco.mjtGeom.mjGEOM_SPHERE,
        size=np.array([0.018, 0.0, 0.0]),
        pos=grab.target,
        mat=np.eye(3).flatten(),
        rgba=np.array([1.0, 0.75, 0.1, 0.9]),
    )
    scene.ngeom = 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hi",
        action="store_true",
        help="High-detail mesh (580 verts): nicer folds, ~3x slower",
    )
    parser.add_argument(
        "--poncho",
        action="store_true",
        help="Use bend-elasticity playground (experimental)",
    )
    args = parser.parse_args(argv)

    try:
        import mujoco
        import mujoco.viewer
    except ImportError:
        raise SystemExit(
            "MuJoCo is not installed.\n"
            "From the repo root run:  moon run install-mujoco"
        )

    forwarded = [f for f, on in (("--hi", args.hi), ("--poncho", args.poncho)) if on]
    _reexec_mjpython_on_macos(forwarded)
    load_mujoco_plugins()

    if args.poncho:
        scene = PLAYGROUND_PONCHO_XML
    elif args.hi:
        scene = PLAYGROUND_HI_XML
    else:
        scene = PLAYGROUND_XML
    if not scene.is_file():
        raise SystemExit(f"Missing scene: {scene}")

    model = mujoco.MjModel.from_xml_path(scene.as_posix())
    data = mujoco.MjData(model)
    grab = ClothGrab(model, data)
    paused = False
    handle = {}

    def on_key(key: int) -> None:
        nonlocal paused
        viewer = handle.get("viewer")
        if key == KEY_SPACE:
            paused = not paused
            print("paused" if paused else "running", flush=True)
            return
        if key == KEY_R:
            grab.release()
            mujoco.mj_resetData(model, data)
            print("reset", flush=True)
            return
        if key == KEY_G:
            selected = int(viewer.perturb.select) if viewer is not None else 0
            print(grab.toggle(selected), flush=True)
            return
        if key == KEY_X:
            grab.stop()
            return
        if not grab.active:
            return

        azimuth = viewer.cam.azimuth if viewer is not None else 135.0
        right, forward = camera_axes(azimuth)
        up = np.array([0.0, 0.0, 1.0])
        direction = {
            KEY_RIGHT: right,
            KEY_LEFT: -right,
            KEY_UP: forward,
            KEY_DOWN: -forward,
            KEY_E: up,
            KEY_Q: -up,
        }.get(key)
        if direction is not None:
            grab.nudge(direction)

    print(CONTROLS, flush=True)
    print(f"Loaded {scene}  nflexvert={model.nflexvert}", flush=True)

    with mujoco.viewer.launch_passive(model, data, key_callback=on_key) as viewer:
        handle["viewer"] = viewer
        with viewer.lock():
            _configure_viewer(viewer, model)

        # Physics and rendering run at different rates. Syncing once per step
        # rendered at 500 Hz and then slept away the rest of the budget, so the
        # shirt fell at a fraction of real time and read as heavy and gooey.
        frame_dt = 1.0 / 60.0
        max_steps_per_frame = int(frame_dt / model.opt.timestep) * 4
        sim_clock = time.perf_counter()

        while viewer.is_running():
            frame_start = time.perf_counter()

            if paused:
                mujoco.mj_forward(model, data)
                sim_clock = frame_start
            else:
                steps = 0
                while sim_clock < frame_start and steps < max_steps_per_frame:
                    grab.apply(model.opt.timestep)
                    mujoco.mj_step(model, data)
                    sim_clock += model.opt.timestep
                    steps += 1
                if steps == max_steps_per_frame:
                    # Can't keep up; drop the debt instead of spiralling.
                    sim_clock = frame_start

            # sync() zeroes xfrc_applied and folds in mouse input, so the grab
            # force is written by grab.apply() on the next step, never before.
            viewer.sync()
            _draw_grab_marker(viewer, grab)

            leftover = frame_dt - (time.perf_counter() - frame_start)
            if leftover > 0:
                time.sleep(leftover)


if __name__ == "__main__":
    main()
