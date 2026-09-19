"""Load the press with a shirt, check the placement, then press it.

One cycle: pick the pile, hang it, let the helper take the opposite corner,
set the held cloth down on the press, then slide both hands to the flat-T
pose on the plate. OpenCV checks the result; leftover error is walked out
with corner tugs. Then both arms clear, the platen comes down, and the bed
dumps.

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
from .arm import Arm, hold_together, move_together
from .platform import reexec_under_mjpython
from .press_cycle import PressCycle
from .scene import HAND_OPEN, HAND_SHUT
from .shirt import shirt_vertex_positions
from .sim_loop import Loop

# Heights for the pinch point, all in metres.
CARRY_Z = 0.85
HANG_Z = 1.02
STRETCH_Z = 0.94
LOOK_Z = 1.12
HANG_SETTLE = 1.2
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

# Helper must stay this far from the picker's pinch so it takes a real corner.
HELPER_REACH = 0.82
FREE_CORNER_MARGIN = 0.18
# Pinch-to-pinch floor: two 2F-85s occupy this much when both look down.
HAND_CLEAR = 0.28
# Extra outward twist so the gripper bodies open a V instead of kissing.
HAND_SPLAY = math.radians(25.0)


@dataclass
class Runtime:
    cell: scene.Cell
    data: object
    loop: Loop
    arm: Arm
    helper: Arm
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
        arm=Arm(cell, data, cell.picker),
        helper=Arm(cell, data, cell.helper),
        press=PressCycle(cell.model, data),
        camera=vision.PlacementCamera(
            cell.model,
            plane_z=cell.bed_surface_z + cell.shirt_half_thickness,
            target_center=cell.bed_center,
            target_yaw=cell.press_yaw,
            roi_half=(0.41, 0.37),
            shape_gate=False,
        ),
        rng=np.random.default_rng(seed),
        viewer=viewer,
        frames=frame_dir,
    )


def run_cycle(run: Runtime, cycle: int) -> CycleResult:
    """Hang, take the opposite corner, set down, slide into place, press, dump."""
    cell, loop, arm, helper = run.cell, run.loop, run.arm, run.helper
    picker_xy, helper_xy = _lay_corners(cell)

    scene.spawn_shirt_in_bin(cell, run.data, run.rng)
    run.press.park()

    # Home over the crate first: the tossed-in shirt needs to settle before the
    # crate camera reads it, or the jaws close where the shirt no longer is.
    arm.park([*cell.bin_center, CARRY_Z], 0.0, grip=HAND_OPEN)
    helper.park(_helper_aisle(CARRY_Z), math.pi, grip=HAND_OPEN)
    if not loop.hold(1.0):
        return CycleResult(False, 0, False)
    arm.sync()
    helper.sync()

    for attempt in range(1, MAX_PICK_TRIES + 1):
        band, band_yaw = _crate_estimate(run)
        _log(cycle, "PICK", f"top of the pile at {band[0]:+.3f} "
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

    _log(cycle, "HANG", "lift high and wait so gravity opens the cloth")
    if not arm.follow_waypoints(
        loop, [_aisle_point(HANG_Z), _present_point(HANG_Z)], 0.0, 3.4, settle=0.3
    ):
        return CycleResult(False, 0, False)
    if not hold_together(loop, arm, seconds=HANG_SETTLE):
        return CycleResult(False, 0, False)

    _log(cycle, "HAND", "helper takes the opposite corner in the air")
    if not _take_hanging_corner(helper, arm, loop, cell):
        return CycleResult(False, 0, False)

    _log(cycle, "LAY", "set the held shirt down on the press")
    if not _set_down_on_press(arm, helper, loop, cell):
        return CycleResult(False, 0, False)

    _log(cycle, "PLACE", "slide both corners into the flat-T pose")
    if not _slide_into_place(arm, helper, loop, cell, picker_xy, helper_xy):
        return CycleResult(False, 0, False)

    if not arm.open_hand(loop, hold=(helper,)) or not helper.open_hand(loop, hold=(arm,)):
        return CycleResult(False, 0, False)
    if not helper.follow_waypoints(
        loop, [_helper_aisle(CARRY_Z)], math.pi, 2.0, settle=0.2
    ):
        return CycleResult(False, 0, False)
    if not _look(arm, loop, cell):
        return CycleResult(False, 0, False)

    placement = _check(run, cycle, 0)
    corrections = 0
    target = cell.bed_center
    while not placement.ok and corrections < MAX_CORRECTIONS:
        if not placement.found:
            _log(cycle, "CHECK", "nothing on the bed, giving up on this shirt")
            return CycleResult(False, corrections, False)

        pull = tug.choose(
            cell.shirt_torso_half,
            placement.center,
            placement.yaw,
            target,
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

    _log(cycle, "CLEAR", "placement accepted, arms leave the press")
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


def _helper_aisle(height: float) -> np.ndarray:
    """Park on the far side of the dump edge, clear of the picker."""
    return np.array([0.50, -0.20, height])


def _present_point(height: float) -> np.ndarray:
    """Over the dump edge, high enough that the cloth hangs clear of the plate."""
    return np.array([-0.08, -0.16, height])


def _shoulder_ids(cell) -> tuple[int, int]:
    """Rest-mesh indices of the left and right collar/shoulder corners."""
    local = cell.shirt_rest_local
    collar = np.flatnonzero((local[:, 0] > 0.12) & (np.abs(local[:, 1]) < 0.32))
    if collar.size < 2:
        return 0, 0
    return (
        int(collar[np.argmax(local[collar, 1])]),
        int(collar[np.argmin(local[collar, 1])]),
    )


def _shoulder_locals(cell) -> tuple[np.ndarray, np.ndarray]:
    """Left and right shoulder xy in the shirt frame (collar = +X, left = +Y)."""
    local = cell.shirt_rest_local
    left_id, right_id = _shoulder_ids(cell)
    return local[left_id, :2].copy(), local[right_id, :2].copy()


def _lay_corners(cell) -> tuple[np.ndarray, np.ndarray]:
    """World xy for the two shoulders, collar on the dump edge, hem toward the back.

    Picker stands on world -x and holds the right shoulder; helper on +x holds
    the left. After the press yaw that is a flat T on the plate.
    """
    left, right = _shoulder_locals(cell)
    yaw = cell.press_yaw
    picker = cell.bed_center + _rotate(right, yaw)
    helper = cell.bed_center + _rotate(left, yaw)
    return picker, helper


def _crate_estimate(run: Runtime):
    """Grab whatever is on top of the pile. Gravity sorts the corners later."""
    cell = run.cell
    live = shirt_vertex_positions(cell.model, run.data)
    pick = live[int(np.argmax(live[:, 2]))]
    _, yaw = scene.shirt_pose(cell, run.data)
    band = pick[:2] + run.rng.normal(0.0, PICK_POSITION_NOISE, 2)
    return (
        np.array([band[0], band[1], float(pick[2])]),
        float(yaw + run.rng.normal(0.0, PICK_YAW_NOISE)),
    )


def _pinch(arm: Arm, loop, cell, band, yaw: float) -> bool:
    """Close the fingers on the top of the pile and lift the garment clear."""
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


def _take_hanging_corner(helper: Arm, picker: Arm, loop, cell) -> bool:
    """Pinch the far, low corner of the hanging cloth — the opposite corner."""
    grasp = _hanging_corner(cell, loop.data, picker, helper)
    if grasp is None:
        return False
    grasp = _clear_of_partner(picker.pinch_position(), grasp, helper.kit.base)
    picker_yaw, helper_yaw = _pair_yaws(picker.pinch_position(), grasp)
    hover = _helper_approach(grasp, helper)
    hold = (picker,)
    if not picker.move(
        loop, picker.target_pos, picker_yaw, 0.6, settle=0.1, hold=()
    ):
        return False
    if not helper.follow_waypoints(
        loop, [_helper_aisle(CARRY_Z), hover], helper_yaw, 2.6, hold=hold
    ):
        return False
    refresh = _hanging_corner(cell, loop.data, picker, helper)
    if refresh is not None:
        grasp = _clear_of_partner(picker.pinch_position(), refresh, helper.kit.base)
        picker_yaw, helper_yaw = _pair_yaws(picker.pinch_position(), grasp)
    return helper.move(
        loop, grasp, helper_yaw, 1.2, settle=0.4, hold=hold
    ) and helper.close_hand(loop, hold=hold)


def _hanging_corner(cell, data, picker: Arm, helper: Arm) -> np.ndarray | None:
    """After a hang, the opposite corner is the farthest, lowest reachable vertex."""
    del cell
    verts = shirt_vertex_positions(picker.cell.model, data)
    pin = picker.pinch_position()
    away = np.linalg.norm(verts - pin, axis=1)
    reach = np.linalg.norm(verts[:, :2] - helper.kit.base, axis=1)
    free = (away >= FREE_CORNER_MARGIN) & (reach <= HELPER_REACH)
    if not np.any(free):
        free = reach <= HELPER_REACH
    if not np.any(free):
        return None
    score = away + 0.8 * (pin[2] - verts[:, 2])
    score = np.where(free, score, -np.inf)
    return verts[int(np.argmax(score))].copy()


def _pair_yaws(picker_xyz, helper_xyz) -> tuple[float, float]:
    """Jaws look down; gripper bodies splay outward so the wrists do not kiss."""
    heading = math.atan2(
        float(helper_xyz[1] - picker_xyz[1]), float(helper_xyz[0] - picker_xyz[0])
    )
    return heading + 0.5 * math.pi + HAND_SPLAY, heading - 0.5 * math.pi - HAND_SPLAY


def _clear_of_partner(picker_xyz, grasp, helper_base) -> np.ndarray:
    """Push the helper pinch out if the hanging corner is still under the picker."""
    picker_xy = np.asarray(picker_xyz[:2], dtype=float)
    point = np.asarray(grasp, dtype=float).copy()
    delta = point[:2] - picker_xy
    dist = float(np.linalg.norm(delta))
    if dist < 1e-4:
        delta = np.asarray(helper_base, dtype=float) - picker_xy
        dist = float(np.linalg.norm(delta))
    if dist < 1e-4:
        return point
    if dist < HAND_CLEAR:
        point[:2] = picker_xy + (delta / dist) * HAND_CLEAR
    return point


def _helper_approach(grasp, helper: Arm) -> np.ndarray:
    """Hover on the helper's side of the corner, not through the picker."""
    grasp = np.asarray(grasp, dtype=float)
    toward = helper.kit.base - grasp[:2]
    norm = float(np.linalg.norm(toward))
    hover = grasp.copy()
    if norm > 1e-4:
        hover[:2] = grasp[:2] + toward / norm * 0.10
    hover[2] = max(float(grasp[2]) + HOVER_ABOVE_GRASP, STRETCH_Z)
    return hover


def _separate_xy(left, right, gap: float) -> tuple[np.ndarray, np.ndarray]:
    """Keep the two pinches at least ``gap`` apart so the hands do not stack."""
    left = np.asarray(left, dtype=float).copy()
    right = np.asarray(right, dtype=float).copy()
    delta = right - left
    dist = float(np.linalg.norm(delta))
    if dist >= gap:
        return left, right
    if dist < 1e-4:
        delta = np.array([gap, 0.0])
        dist = gap
    extra = 0.5 * (gap - dist) * (delta / dist)
    return left - extra, right + extra


def _onto_bed(left, right, cell) -> tuple[np.ndarray, np.ndarray]:
    """Shift a held pair onto the plate if it is still hanging in the aisle."""
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    mid = 0.5 * (left + right)
    half = cell.bed_half
    if abs(float(mid[0])) <= float(half[0]) and abs(float(mid[1])) <= float(half[1]):
        return left, right
    shift = cell.bed_center - mid
    return left + shift, right + shift


def _set_down_on_press(picker: Arm, helper: Arm, loop, cell) -> bool:
    """Put the held cloth on the plate, still holding both corners."""
    left, right = _onto_bed(
        *_separate_xy(picker.pinch_position()[:2], helper.pinch_position()[:2], HAND_CLEAR),
        cell,
    )
    hover_z = STRETCH_Z
    lay_z = cell.shirt_rest_z + LAY_CLEARANCE
    yaws = _pair_yaws(left, right)
    return move_together(
        loop, picker, [*left, hover_z], yaws[0], helper, [*right, hover_z], yaws[1], 2.2, settle=0.3
    ) and move_together(
        loop, picker, [*left, lay_z], yaws[0], helper, [*right, lay_z], yaws[1], 1.8, settle=0.5
    )


def _slide_into_place(picker: Arm, helper: Arm, loop, cell, picker_xy, helper_xy) -> bool:
    """Drag the two held corners across the plate into the flat-T pose."""
    drag_z = cell.shirt_top_z + cell.finger_reach - TUG_PRESS
    yaws = _pair_yaws(picker_xy, helper_xy)
    return move_together(
        loop,
        picker,
        [*picker_xy, drag_z],
        yaws[0],
        helper,
        [*helper_xy, drag_z],
        yaws[1],
        3.2,
        settle=0.6,
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
        "Two UR5e + 2F-85: hang, grab, set down, slide into place. Wrist camera within "
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
