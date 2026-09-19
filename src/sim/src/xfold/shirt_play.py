"""Interactive shirt-only playground — drag the cloth and watch the physics."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

from xfold.garments import add_garment_arguments, garment_from_args
from xfold.shirt import (
    PLAYGROUND_HI_XML,
    PLAYGROUND_PONCHO_XML,
    PLAYGROUND_XML,
    load_mjcf,
    load_mujoco_plugins,
    select_garment,
    shirt_config,
)
from xfold.claws import ShirtClaws
from xfold.ninja_fold import NinjaFoldDemo, button_body_id
from xfold.self_collide import ClothLayers
from xfold.shirt_grab import (
    KEY_DOWN,
    KEY_E,
    KEY_G,
    KEY_LEFT,
    KEY_N,
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
XFOLD shirt playground — adult T-shirt (cloth physics)
--------------------------------------------------------
Trackpad friendly — no right-click needed.

  N            NINJA FOLD demo (or double-click the orange button)
               two claws: left crease → right crease → hem to collar
  G            grab / release one claw
               (the vertex you double-clicked, else the highest one)
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


def _draw_markers(viewer, grab, demo) -> None:
    """Grab target, ninja-fold hands, and a pressed-state on the 3D button."""
    import mujoco

    scene = viewer.user_scn
    if scene is None:
        return
    scene.ngeom = 0
    mat = np.eye(3).flatten()

    def _sphere(pos, radius, rgba) -> None:
        i = scene.ngeom
        if i >= scene.maxgeom:
            return
        mujoco.mjv_initGeom(
            scene.geoms[i],
            type=mujoco.mjtGeom.mjGEOM_SPHERE,
            size=np.array([radius, 0.0, 0.0]),
            pos=pos,
            mat=mat,
            rgba=np.asarray(rgba, dtype=np.float64),
        )
        scene.ngeom = i + 1

    if grab.active:
        _sphere(grab.target, 0.012, (1.0, 0.75, 0.1, 0.55))
    for hand in demo.hands:
        _sphere(hand, 0.014, (0.95, 0.35, 0.12, 0.45))
    if len(demo.hands) == 2:
        i = scene.ngeom
        if i < scene.maxgeom:
            mujoco.mjv_initGeom(
                scene.geoms[i],
                type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                size=np.zeros(3),
                pos=np.zeros(3),
                mat=mat,
                rgba=np.array([0.95, 0.35, 0.12, 0.55], dtype=np.float64),
            )
            mujoco.mjv_connector(
                scene.geoms[i],
                mujoco.mjtGeom.mjGEOM_CAPSULE,
                0.006,
                demo.hands[0],
                demo.hands[1],
            )
            scene.ngeom = i + 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hi",
        action="store_true",
        help="High-detail mesh (stills). Much slower than the default.",
    )
    parser.add_argument(
        "--poncho",
        action="store_true",
        help="Use bend-elasticity playground (experimental)",
    )
    add_garment_arguments(parser)
    args = parser.parse_args(argv)

    chosen = garment_from_args(args, interactive=True, current=shirt_config().garment)
    if chosen:
        args.garment = chosen.key

    try:
        import mujoco
        import mujoco.viewer
    except ImportError:
        raise SystemExit(
            "MuJoCo is not installed.\n"
            "From the repo root run:  moon run install-mujoco"
        )

    forwarded = [
        f
        for f, on in (("--hi", args.hi), ("--poncho", args.poncho))
        if on
    ]
    if args.garment:
        forwarded.extend(["--garment", args.garment])
    _reexec_mjpython_on_macos(forwarded)
    load_mujoco_plugins()
    if args.garment:
        select_garment(args.garment)

    if args.poncho:
        scene = PLAYGROUND_PONCHO_XML
    elif args.hi:
        scene = PLAYGROUND_HI_XML
    else:
        scene = PLAYGROUND_XML
    if not scene.is_file():
        raise SystemExit(f"Missing scene: {scene}")

    model, data = load_mjcf(scene)
    cfg = shirt_config()
    print(
        f"shirt.toml  garment={cfg.garment}  mass={cfg.mass} kg  young={cfg.young:g}  "
        f"edge_eq  bend  dt={cfg.timestep}  ({cfg.path})",
        flush=True,
    )
    claws = ShirtClaws(model, data)
    grab = ClothGrab(model, data, claws)
    demo = NinjaFoldDemo(model, data, claws)
    layers = ClothLayers(model, data)
    btn_id = button_body_id(model)
    btn_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "ninja_button")
    paused = False
    handle = {}

    def _start_fold() -> None:
        grab.release()
        print(demo.start(), flush=True)
        if btn_geom >= 0:
            model.geom_rgba[btn_geom] = (0.25, 0.72, 0.32, 1.0)

    def _stop_fold() -> None:
        demo.stop()
        if btn_geom >= 0:
            model.geom_rgba[btn_geom] = (0.92, 0.58, 0.12, 1.0)

    def on_key(key: int) -> None:
        nonlocal paused
        viewer = handle.get("viewer")
        if key == KEY_SPACE:
            paused = not paused
            print("paused" if paused else "running", flush=True)
            return
        if key == KEY_R:
            grab.release()
            _stop_fold()
            mujoco.mj_resetData(model, data)
            claws.hide()
            print("reset", flush=True)
            return
        if key == KEY_N:
            if demo.active:
                _stop_fold()
                print("ninja fold: cancelled", flush=True)
            else:
                _start_fold()
            return
        if demo.active:
            return
        if key == KEY_G:
            selected = int(viewer.perturb.select) if viewer is not None else 0
            if selected == btn_id and btn_id >= 0:
                _start_fold()
                return
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
        # Cap catch-up at 1× — a 4× debt spiral freezes the viewer.
        frame_dt = 1.0 / 60.0
        max_steps_per_frame = max(1, int(round(frame_dt / model.opt.timestep)))
        sim_clock = time.perf_counter()

        while viewer.is_running():
            frame_start = time.perf_counter()

            if paused:
                mujoco.mj_forward(model, data)
                sim_clock = frame_start
            else:
                steps = 0
                while sim_clock < frame_start and steps < max_steps_per_frame:
                    demo.apply(model.opt.timestep)
                    if not demo.active:
                        grab.apply(model.opt.timestep)
                    mujoco.mj_step(model, data)
                    layers.separate()
                    sim_clock += model.opt.timestep
                    steps += 1
                if steps == max_steps_per_frame:
                    # Can't keep up; drop the debt instead of spiralling.
                    sim_clock = frame_start

            # Claws are mocap connects, not xfrc. sync() still zeroes
            # xfrc_applied; that is fine.
            viewer.sync()
            if (
                not demo.active
                and btn_id >= 0
                and int(viewer.perturb.select) == btn_id
            ):
                _start_fold()
                viewer.perturb.select = 0
            if not demo.active and btn_geom >= 0:
                model.geom_rgba[btn_geom] = (0.92, 0.58, 0.12, 1.0)
            _draw_markers(viewer, grab, demo)

            leftover = frame_dt - (time.perf_counter() - frame_start)
            if leftover > 0:
                time.sleep(leftover)


if __name__ == "__main__":
    main()
