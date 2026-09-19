"""Load the press with a shirt, check the placement, then press it.

One cycle: the arm takes a shirt out of the crate the way a person would - two
fingers on the neckband - and lays it on the heated bed. OpenCV then measures
where the garment actually landed. If it is off centre or crooked the hand does
not pick it up again; it presses its fingertips on whichever corner is furthest
from where it belongs and drags that corner into place, then looks again. Only
once the camera signs off does the arm leave the press and the platen come down.
The bed then tilts and the shirt slides out.

With a window:  moon run sim:run
Headless:       pixi run -e mujoco python -m xfold.load_press --headless --cycles 1
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import scene, tug, vision
from .arm import Arm
from .platform import reexec_under_mjpython
from .press_cycle import PressCycle
from .scene import HAND_OPEN, HAND_SHUT
from .sim_loop import Loop

# Heights for the pinch point, all in metres.
CARRY_Z = 0.85
LOOK_Z = 1.12
# Pinch offset so the wrist camera, not the fingers, sits over the bed centre.
LOOK_OFFSET = np.array([-0.06, 0.0])
HOVER_ABOVE_GRASP = 0.18
LAY_CLEARANCE = 0.002  # how hard the shirt is set down before the jaws open

MAX_PICK_TRIES = 3

# A tug: fingertips pressed this far into the garment, dragged, then lifted.
TUG_PRESS = 0.003
TUG_HOVER = 0.09

MAX_CORRECTIONS = 6

# Stand-in for the crate camera that will estimate the pose of the next shirt.
PICK_POSITION_NOISE = 0.008
PICK_YAW_NOISE = math.radians(4.0)

# How far inside the crate walls the jaws are allowed to close, in metres.
# Reaching past a wall either clips the wall or pinches the shirt against it.
BIN_PICK_MARGIN = np.array([0.20, 0.26])


@dataclass
class Runtime:
    cell: scene.Cell
    data: object
    loop: Loop
    arm: Arm
    press: PressCycle
    camera: vision.PlacementCamera
    rng: np.random.Generator
    viewer: object | None
    frames: Path | None


@dataclass
class CycleResult:
    placed: bool
    corrections: int
    pressed: bool


def build_runtime(seed: int, headless: bool, frames: str = "") -> Runtime:
    import mujoco

    cell = scene.build()
    data = mujoco.MjData(cell.model)

    viewer = None
    if not headless:
        import mujoco.viewer

        viewer = mujoco.viewer.launch_passive(cell.model, data)
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
        viewer.cam.fixedcamid = cell.model.camera("cell_cam").id

    frame_dir = None
    if frames:
        frame_dir = Path(frames)
        frame_dir.mkdir(parents=True, exist_ok=True)

    return Runtime(
        cell=cell,
        data=data,
        loop=Loop(cell.model, data, viewer=viewer, realtime=not headless),
        arm=Arm(cell, data),
        press=PressCycle(cell.model, data),
        camera=vision.PlacementCamera(
            cell.model,
            plane_z=cell.bed_surface_z + cell.shirt_half_thickness,
            target_center=cell.bed_center,
            target_yaw=cell.press_yaw,
            roi_half=(0.33, 0.27),
            shape_gate=False,
        ),
        rng=np.random.default_rng(seed),
        viewer=viewer,
        frames=frame_dir,
    )


def run_cycle(run: Runtime, cycle: int) -> CycleResult:
    """Pick, place, verify, tug straight, press, dump."""
    cell, loop, arm = run.cell, run.loop, run.arm

    scene.spawn_shirt_in_bin(cell, run.data, run.rng)
    run.press.park()

    # Home over the crate first: the tossed-in shirt needs to settle before the
    # crate camera reads it, or the jaws close where the shirt no longer is.
    arm.park([*cell.bin_center, CARRY_Z], 0.0, grip=HAND_OPEN)
    if not loop.hold(1.0):
        return CycleResult(False, 0, False)
    arm.sync()

    for attempt in range(1, MAX_PICK_TRIES + 1):
        band, band_yaw = _crate_estimate(run)
        _log(cycle, "PICK", f"crate reports the neckband at {band[0]:+.3f} "
                            f"{band[1]:+.3f} m, {math.degrees(band_yaw):+.1f} deg")
        if not _pinch(arm, loop, cell, band, band_yaw):
            return CycleResult(False, 0, False)
        if arm.holding:
            break
        _log(cycle, "PICK", f"jaws closed on air, try {attempt} of {MAX_PICK_TRIES}")
        if attempt == MAX_PICK_TRIES or not arm.open_hand(loop):
            return CycleResult(False, 0, False)
    else:
        return CycleResult(False, 0, False)

    # The cloth hangs from the pinched neck, so the hand lays over the bed
    # centre and the garment drapes onto the plate. A rigid-shirt collar
    # offset would drop the pile off the dump edge.
    lay_yaw = cell.press_yaw
    lay_band = cell.bed_center
    _log(cycle, "CARRY", "in through the press opening")
    if not arm.follow_waypoints(
        loop, _approach_path(cell, lay_band, CARRY_Z), lay_yaw, 3.8, settle=0.5
    ):
        return CycleResult(False, 0, False)

    _log(cycle, "LAY", "shirt down on the heated bed")
    if not _lay(arm, loop, cell, lay_band, lay_yaw):
        return CycleResult(False, 0, False)

    placement = _check(run, cycle, 0)
    corrections = 0
    while not placement.ok and corrections < MAX_CORRECTIONS:
        if not placement.found:
            _log(cycle, "CHECK", "nothing on the bed, giving up on this shirt")
            return CycleResult(False, corrections, False)

        pull = tug.choose(
            cell.shirt_torso_half,
            placement.center,
            placement.yaw,
            cell.bed_center,
            cell.arm_base,
            target_yaw=cell.press_yaw,
        )
        if pull is None:
            _log(cycle, "TUG", "no reachable corner left to pull")
            return CycleResult(False, corrections, False)

        corrections += 1
        _log(cycle, "TUG", f"try {corrections}: pull the {pull.describe()}")
        if not _tug(arm, loop, cell, pull):
            return CycleResult(False, corrections, False)
        placement = _check(run, cycle, corrections)

    if not placement.ok:
        _log(cycle, "CHECK", "still out of tolerance, not pressing")
        return CycleResult(False, corrections, False)

    _log(cycle, "CLEAR", "placement accepted, arm leaves the press")
    if not arm.follow_waypoints(
        loop, [_aisle_point(CARRY_Z), [*cell.bin_center, CARRY_Z]], 0.0, 2.6, settle=0.3
    ):
        return CycleResult(True, corrections, False)

    _log(cycle, "PRESS", "platen down, vapour on")
    if not run.press.press(loop):
        return CycleResult(True, corrections, False)

    _log(cycle, "DUMP", "bed tilts, shirt slides out")
    if not run.press.dump(loop):
        return CycleResult(True, corrections, True)
    return CycleResult(True, corrections, True)


def _aisle_point(height: float) -> np.ndarray:
    """A hold in front of the crate, clear of the press frame and hinges."""
    return np.array([-0.58, -0.22, height])


def _approach_path(cell, lay_band, height: float) -> list[np.ndarray]:
    """Crate aisle → C-frame mouth → collar pose. Stays on the open -x side."""
    finish = np.array([float(lay_band[0]), float(lay_band[1]), height])
    return [_aisle_point(height), np.array([-0.28, -0.16, height]), finish]


def _crate_estimate(run: Runtime):
    """Where an upstream crate camera would say the neckband is.

    Ground truth plus noise, standing in for a camera over the crate. Nothing
    downstream sees the true pose: the hand grabs what the camera reports and
    the press camera judges the result.
    """
    cell = run.cell
    collar = scene.shirt_collar(cell, run.data)
    _, yaw = scene.shirt_pose(cell, run.data)
    band = collar[:2] + run.rng.normal(0.0, PICK_POSITION_NOISE, 2)
    return (
        np.array([band[0], band[1], float(collar[2])]),
        float(yaw + run.rng.normal(0.0, PICK_YAW_NOISE)),
    )


def _pinch(arm: Arm, loop, cell, band, yaw: float) -> bool:
    """Close the fingers on the neckband and lift the garment clear."""
    band = np.asarray(band, dtype=float).copy()
    band[:2] = np.clip(
        band[:2], cell.bin_center - BIN_PICK_MARGIN, cell.bin_center + BIN_PICK_MARGIN
    )
    return (
        arm.move(loop, [band[0], band[1], band[2] + HOVER_ABOVE_GRASP], yaw, 1.4)
        and arm.move(loop, band, yaw, 1.6, settle=0.5)
        and arm.close_hand(loop)
        and arm.move(loop, [band[0], band[1], CARRY_Z], yaw, 2.0, settle=0.6)
    )


def _look_pose(cell) -> np.ndarray:
    return np.array([cell.bed_center[0] + LOOK_OFFSET[0], cell.bed_center[1] + LOOK_OFFSET[1], LOOK_Z])


def _look(arm: Arm, loop, cell) -> bool:
    """Hold the wrist camera over the bed so it can judge the shirt."""
    return arm.move(loop, _look_pose(cell), cell.press_yaw, 1.6, settle=0.5)


def _lay(arm: Arm, loop, cell, band_xy, yaw: float) -> bool:
    """Set the shirt on the bed, let go, and lift to the look pose.

    The hand leaves straight up and only then sideways: sliding away at garment
    height grazes the shirt and shoves it off target by centimetres. It also
    shuts the fingers on the way out, ready to tug a corner.
    """
    band_z = cell.shirt_rest_z + cell.shirt_band_local[2]
    return (
        arm.move(loop, [*band_xy, band_z + LAY_CLEARANCE], yaw, 1.8, settle=0.6)
        and arm.open_hand(loop)
        and arm.move(loop, [*band_xy, CARRY_Z], yaw, 1.4)
        and arm.grip(loop, HAND_SHUT, 0.5, settle=0.0)
        and _look(arm, loop, cell)
    )


def _tug(arm: Arm, loop, cell, pull: tug.Tug) -> bool:
    """Press the shut fingertips on a corner, drag it, and stand off again.

    The jaws are held across the direction of travel, so the two pads sweep the
    corner like a squeegee instead of letting it spin between them.
    """
    hover_z = cell.bed_surface_z + TUG_HOVER
    press_z = cell.shirt_top_z + cell.finger_reach - TUG_PRESS
    yaw = pull.heading + math.pi / 2.0
    arm.set_grip(HAND_SHUT)
    return (
        arm.follow_waypoints(
            loop, [_aisle_point(hover_z), [*pull.start, hover_z]], yaw, 2.2
        )
        and arm.move(loop, [*pull.start, press_z], yaw, 0.9, settle=0.3)
        and arm.move(loop, [*pull.finish, press_z], yaw, 1.5, settle=0.4)
        and arm.move(loop, [*pull.finish, hover_z], yaw, 0.9)
        and _look(arm, loop, cell)
    )


def _check(run: Runtime, cycle: int, attempt: int) -> vision.Placement:
    rgb = run.camera.render(run.data)
    placement = run.camera.inspect(run.data, rgb)
    verdict = "accept" if placement.ok else "reject"
    _log(cycle, "CHECK", f"{placement.describe()}  -> {verdict}")
    if run.frames is not None:
        import cv2

        path = run.frames / f"cycle{cycle:02d}_check{attempt}.png"
        cv2.imwrite(path.as_posix(), run.camera.annotate(run.data, rgb, placement))
    return placement


def _rotate(offset, angle: float) -> np.ndarray:
    cos, sin = math.cos(angle), math.sin(angle)
    offset = np.asarray(offset, dtype=float)
    return np.array([cos * offset[0] - sin * offset[1], sin * offset[0] + cos * offset[1]])


def _log(cycle: int, state: str, message: str = "") -> None:
    print(f"[cycle {cycle}] {state:<6} {message}".rstrip(), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="XFOLD press loading cell")
    parser.add_argument(
        "--cycles", type=int, default=0, help="0 keeps going until the window closes"
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--headless", action="store_true", help="no window, runs as fast as it can"
    )
    parser.add_argument(
        "--frames", default="", help="directory for annotated inspection frames"
    )
    args = parser.parse_args()

    try:
        import mujoco  # noqa: F401
    except ImportError:
        raise SystemExit(
            "MuJoCo is not installed.\nFrom the repo root run:  moon run install-mujoco"
        )
    if not args.headless:
        reexec_under_mjpython("xfold.load_press")

    run = build_runtime(args.seed, args.headless, args.frames)
    print(f"XFOLD press loading cell  {scene.CELL_PATH}", flush=True)
    print(
        "UR5e with a Robotiq 2F-85 hand; placement checked from the wrist camera within "
        f"{run.camera.position_tolerance * 1000:.0f} mm and "
        f"{math.degrees(run.camera.yaw_tolerance):.0f} deg, corrected by corner tugs.",
        flush=True,
    )

    cycle = 0
    try:
        while run.loop.running:
            cycle += 1
            result = run_cycle(run, cycle)
            if not run.loop.running:
                _log(cycle, "STOP", "window closed mid-cycle")
                break
            _log(
                cycle,
                "DONE",
                f"placed={result.placed} tugs={result.corrections} "
                f"pressed={result.pressed}",
            )
            if args.cycles and cycle >= args.cycles:
                break
    finally:
        run.camera.close()
        if run.viewer is not None:
            run.viewer.close()


if __name__ == "__main__":
    main()
