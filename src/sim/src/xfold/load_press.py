"""Load the press with a shirt, check the placement, then press it.

One cycle, the way two people spread a sheet. Every grasp is made on cloth
lying still on a surface, never on a swinging one:

1. The picker pinches the sleeve on top of the crate pack, draws the shirt
   out over the crate's low lip, drags it onto the plate and lets go.
2. The helper picks up that sleeve where it now lies and tows it toward its
   own side, which pulls the rest of the shirt out of the crate.
3. The picker picks the other sleeve off the plate.
4. Both hands lift to sleeve-to-sleeve width in front of the press. The
   sleeves run straight along the top edge; the torso hangs like a curtain.
5. The hands carry the curtain in under the platen and drag it back across
   the plate. Friction on the trailing torso pulls every fold straight, so
   the shirt lies as a flat T: collar at the back, hem on the dump edge.

The platen leaves too little height to lower the full curtain straight down,
which is why the lay is a drag and not a drop. Fingertips always stay above
whatever the cloth rests on: shut fingers driven into steel by stiff position
servos is what made the old set-down blow up.

OpenCV then checks the result; leftover error is walked out with corner
tugs. Both arms clear, the platen comes down, and the bed dumps.

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
from .arm import Arm, move_together
from .platform import reexec_under_mjpython
from .press_cycle import PressCycle
from .scene import HAND_OPEN
from .shirt import shirt_vertex_positions
from .sim_loop import Loop

# The flat T on the plate: collar toward the back (+y), hem on the dump edge,
# left sleeve on the picker's side (-x).
LAY_YAW = 0.5 * math.pi

# Grasp points on the rest mesh (collar = +x, left sleeve = +y): each sleeve
# one vertex in from the cuff and one below the shoulder line, which keeps
# the crate pick clear of the front wall. The pinch patch still takes the
# shoulder line with it.
SLEEVE_LOCAL = np.array([0.224, 0.364])

# Heights for the pinch point, all in metres.
CARRY_Z = 0.85
LOOK_Z = 1.12
# Out of the crate over its low lip and low onto the plate; lifted straight
# out, the shirt hooks on a crate wall. Low enough to pass under the platen.
# The last point is where the sleeve is set down: mid-plate, where both arms
# reach down to the bed without their links meeting.
DRAW_OUT = (np.array([-0.30, -0.12, 0.80]), np.array([0.02, -0.15, 0.72]))
# The helper tows its sleeve here, so the 0.85 m of shirt behind it comes
# clear of the crate and the other sleeve lands on the plate.
TOW_XY = np.array([0.30, -0.15])
# Both sleeves held here: in front of the bed lip and clear of the platen.
CURTAIN_Y = -0.56
CURTAIN_Z = 1.10
CURTAIN_SETTLE = 1.2
# First point under the platen. The wrist stack is ~0.3 m tall, so the
# pinch stays under ~1.0 m anywhere over the bed.
ENTER_Y = -0.05
ENTER_Z = 0.76
# Fingertips this far above the laid cloth during the drag. Never zero.
DRAG_CLEARANCE = 0.02
# Fingertips this far above a vertex when pinching cloth off a surface.
PICK_CLEARANCE = 0.004
LIFT_OFF = 0.12

# Pinch offset so the wrist camera, not the fingers, sits over the bed centre.
LOOK_OFFSET = np.array([-0.06, 0.0])
HOVER_ABOVE_GRASP = 0.18
# Fingertips stop this far above the crate floor when reaching into the pile.
FLOOR_CLEARANCE = 0.006

MAX_PICK_TRIES = 3

# A tug: pinch a corner with the fingertips this far above the cloth, drag.
TUG_CLEARANCE = 0.004
TUG_HOVER = 0.09

MAX_CORRECTIONS = 6

# Stand-in for the crate camera that finds the sleeve corner on the pile.
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
            target_yaw=LAY_YAW,
            roi_half=(0.41, 0.37),
            shape_gate=False,
        ),
        rng=np.random.default_rng(seed),
        viewer=viewer,
        frames=frame_dir,
    )


def run_cycle(run: Runtime, cycle: int) -> CycleResult:
    """Pick, draw out, take both sleeves, spread, drag-lay, check, press, dump."""
    cell, loop, arm, helper = run.cell, run.loop, run.arm, run.helper
    top_id, under_id = _sleeve_ids(cell)
    left_xy, right_xy = _lay_target(cell, under_id), _lay_target(cell, top_id)

    scene.spawn_shirt_in_bin(cell, run.data, run.rng)
    run.press.park()

    # Home over the crate first: the tossed-in shirt needs to settle before the
    # crate camera reads it, or the jaws close where the shirt no longer is.
    arm.park([*cell.bin_center, CARRY_Z], 0.0, grip=HAND_OPEN)
    helper.park(_helper_park(), math.pi, grip=HAND_OPEN)
    if not loop.hold(1.0):
        return CycleResult(False, 0, False)
    arm.sync()
    helper.sync()

    for attempt in range(1, MAX_PICK_TRIES + 1):
        grasp, yaw = _crate_estimate(run, top_id)
        _log(cycle, "PICK", f"top sleeve at {grasp[0]:+.3f} {grasp[1]:+.3f} m")
        if not _pinch(arm, loop, cell, grasp, yaw, top_id):
            return CycleResult(False, 0, False)
        if arm.cloth.active:
            break
        _log(cycle, "PICK", f"missed the sleeve, try {attempt} of {MAX_PICK_TRIES}")
        if attempt == MAX_PICK_TRIES or not arm.open_hand(loop):
            return CycleResult(False, 0, False)
    else:
        return CycleResult(False, 0, False)

    _log(cycle, "DRAW", "draw the shirt over the lip and across the plate")
    if not _draw_out(arm, loop, cell):
        return CycleResult(False, 0, False)

    _log(cycle, "HAND", "helper picks that sleeve up and tows the shirt out")
    if not _pick_lying(helper, loop, cell, top_id, math.pi, hold=(arm,)):
        _log(cycle, "HAND", "helper missed the sleeve")
        return CycleResult(False, 0, False)
    tow = [*TOW_XY, _pinch_z_over(cell, cell.shirt_rest_z, helper) + 0.03]
    if not helper.move(loop, tow, math.pi, 2.0, settle=0.3, hold=(arm,)):
        return CycleResult(False, 0, False)

    _log(cycle, "FETCH", "picker picks the other sleeve off the plate")
    if not _pick_lying(arm, loop, cell, under_id, 0.0, hold=(helper,)):
        _log(cycle, "FETCH", "picker missed the sleeve")
        return CycleResult(False, 0, False)

    _log(cycle, "SPREAD", "open the shirt to sleeve width, torso hangs")
    if not _spread(arm, helper, loop, left_xy, right_xy):
        return CycleResult(False, 0, False)

    _log(cycle, "LAY", "carry under the platen and drag the shirt flat")
    if not _drag_lay(arm, helper, loop, cell, left_xy, right_xy):
        return CycleResult(False, 0, False)

    if not _release(arm, helper, loop):
        return CycleResult(False, 0, False)
    if not helper.follow_waypoints(loop, [_helper_park()], math.pi, 2.0, settle=0.2):
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
            target_yaw=LAY_YAW,
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


def _helper_park() -> np.ndarray:
    """Out to the side of the press, clear of the picker. Parked right over
    its own pedestal the helper is near-singular and folds into the plate."""
    return np.array([0.80, -0.30, 0.95])


def _sleeve_ids(cell) -> tuple[int, int]:
    """Rest-mesh indices of the sleeve on top of the crate pack (the right
    one, see ``scene.spawn_shirt_in_bin``), then the other."""
    local = cell.shirt_rest_local[:, :2]
    ids = []
    for side in (-1.0, 1.0):
        point = SLEEVE_LOCAL * np.array([1.0, side])
        ids.append(int(np.argmin(np.linalg.norm(local - point, axis=1))))
    return ids[0], ids[1]


def _lay_target(cell, vertex: int) -> np.ndarray:
    """World xy where a rest-mesh vertex belongs once the T lies on the plate."""
    return cell.bed_center + _rotate(cell.shirt_rest_local[vertex, :2], LAY_YAW)


def _crate_estimate(run: Runtime, vertex: int):
    """Where the crate camera sees the sleeve corner, with its usual error."""
    cell = run.cell
    live = shirt_vertex_positions(cell.model, run.data)
    _, yaw = scene.shirt_pose(cell, run.data)
    grasp = live[vertex].copy()
    grasp[:2] += run.rng.normal(0.0, PICK_POSITION_NOISE, 2)
    return grasp, float(yaw + run.rng.normal(0.0, PICK_YAW_NOISE))


def _pinch(arm: Arm, loop, cell, grasp, yaw: float, vertex: int) -> bool:
    """Close the fingers on the sleeve corner and lift the garment clear."""
    grasp = np.asarray(grasp, dtype=float).copy()
    grasp[:2] = np.clip(
        grasp[:2], cell.bin_center - BIN_PICK_MARGIN, cell.bin_center + BIN_PICK_MARGIN
    )
    grasp[2] = max(grasp[2], cell.bin_surface_z + arm.kit.finger_reach + FLOOR_CLEARANCE)
    return (
        arm.move(loop, [grasp[0], grasp[1], grasp[2] + HOVER_ABOVE_GRASP], yaw, 1.4)
        and arm.move(loop, grasp, yaw, 1.6, settle=0.5)
        and arm.close_hand(loop, anchor=vertex)
        and arm.move(loop, [grasp[0], grasp[1], CARRY_Z], yaw, 2.0, settle=0.6)
    )


def _look_pose(cell) -> np.ndarray:
    return np.array([cell.bed_center[0] + LOOK_OFFSET[0], cell.bed_center[1] + LOOK_OFFSET[1], LOOK_Z])


def _look(arm: Arm, loop, cell) -> bool:
    """Hold the wrist camera over the bed so it can judge the shirt."""
    return arm.move(loop, _look_pose(cell), LAY_YAW, 1.6, settle=0.5)


def _draw_out(arm: Arm, loop, cell) -> bool:
    """Drag the shirt out of the crate onto the plate, set the sleeve down,
    and back off to the aisle so the helper has the plate to itself."""
    end = DRAW_OUT[-1]
    down = [end[0], end[1], _pinch_z_over(cell, cell.shirt_rest_z, arm)]
    return (
        arm.follow_waypoints(loop, list(DRAW_OUT), 0.0, 2.8, settle=0.2)
        and arm.move(loop, down, 0.0, 0.8, settle=0.3)
        and arm.open_hand(loop)
        and arm.follow_waypoints(
            loop, [[end[0], end[1], CARRY_Z], _aisle_point(CARRY_Z)], 0.0, 2.0, settle=0.1
        )
    )


def _pick_lying(arm: Arm, loop, cell, vertex: int, yaw: float, hold=()) -> bool:
    """Pinch one corner of cloth lying on a surface and lift it a little.

    The corner has not moved since it was put down, so one look is enough.
    The fingertips stop just above it, never on the steel or wood beneath.
    """
    corner = shirt_vertex_positions(arm.cell.model, loop.data)[vertex]
    grasp = np.array([corner[0], corner[1], _pinch_z_over(cell, corner, arm)])
    above = grasp + np.array([0.0, 0.0, HOVER_ABOVE_GRASP])
    if not (
        arm.follow_waypoints(loop, [above], yaw, 1.8, settle=0.1, hold=hold)
        and arm.move(loop, grasp, yaw, 1.0, settle=0.3, hold=hold)
        and arm.close_hand(loop, hold=hold, anchor=vertex)
    ):
        return False
    if not arm.cloth.active:
        return False
    lifted = grasp + np.array([0.0, 0.0, 0.08])
    return arm.move(loop, lifted, yaw, 0.8, settle=0.1, hold=hold)


def _pinch_z_over(cell, cloth, arm: Arm) -> float:
    """Pinch height that leaves the shut fingertips just above a cloth vertex.

    ``cloth`` is a vertex position or just its height. Over the plate the
    height is floored at the resting cloth: the flex sinks a few millimetres
    into the heater, and following it down would drive the fingers into it.
    """
    cloth = np.atleast_1d(np.asarray(cloth, dtype=float))
    z = float(cloth[-1])
    if cloth.size == 3 and np.all(np.abs(cloth[:2] - cell.bed_center) <= cell.bed_half):
        z = max(z, cell.shirt_rest_z)
    return z + arm.kit.finger_reach + PICK_CLEARANCE


def _spread(picker: Arm, helper: Arm, loop, left_xy, right_xy) -> bool:
    """Lift both sleeves to their width on the plate, in front of the press."""
    return move_together(
        loop,
        picker, [left_xy[0], CURTAIN_Y, CURTAIN_Z], 0.5 * math.pi,
        helper, [right_xy[0], CURTAIN_Y, CURTAIN_Z], -0.5 * math.pi,
        2.6,
        settle=CURTAIN_SETTLE,
    )


def _drag_lay(picker: Arm, helper: Arm, loop, cell, left_xy, right_xy) -> bool:
    """Bring the curtain in under the platen, then drag it back to the T pose.

    Jaws close along y so that, opening at the end, they do not swing out
    over the side rails.
    """
    drag_z = cell.shirt_top_z + picker.kit.finger_reach + DRAG_CLEARANCE
    yaw_l, yaw_r = 0.5 * math.pi, -0.5 * math.pi
    return move_together(
        loop,
        picker, [left_xy[0], ENTER_Y, ENTER_Z], yaw_l,
        helper, [right_xy[0], ENTER_Y, ENTER_Z], yaw_r,
        2.4,
        settle=0.2,
    ) and move_together(
        loop,
        picker, [*left_xy, drag_z], yaw_l,
        helper, [*right_xy, drag_z], yaw_r,
        3.6,
        settle=0.6,
    )


def _release(picker: Arm, helper: Arm, loop) -> bool:
    """Let go with both hands, then lift straight up off the cloth."""
    if not picker.open_hand(loop, hold=(helper,)) or not helper.open_hand(loop, hold=(picker,)):
        return False
    up = np.array([0.0, 0.0, LIFT_OFF])
    return move_together(
        loop,
        picker, picker.target_pos + up, picker.target_yaw,
        helper, helper.target_pos + up, helper.target_yaw,
        1.0,
        settle=0.2,
    )


def _tug(arm: Arm, loop, cell, pull: tug.Tug) -> bool:
    """Pinch the fabric at a corner, drag it to where it belongs, let go.

    The pinch point stays high enough that the shut fingertips clear the
    plate; the held patch is lifted a couple of centimetres and slides.
    """
    hover_z = cell.bed_surface_z + TUG_HOVER
    pinch_z = cell.shirt_top_z + cell.finger_reach + TUG_CLEARANCE
    yaw = pull.heading + math.pi / 2.0
    if not (
        arm.follow_waypoints(loop, [_aisle_point(hover_z), [*pull.start, hover_z]], yaw, 2.2)
        and arm.move(loop, [*pull.start, pinch_z], yaw, 0.9, settle=0.3)
    ):
        return False
    live = shirt_vertex_positions(cell.model, loop.data)
    corner = int(np.argmin(np.linalg.norm(live[:, :2] - pull.start, axis=1)))
    return (
        arm.close_hand(loop, anchor=corner)
        and arm.move(loop, [*pull.finish, pinch_z], yaw, 1.5, settle=0.4)
        and arm.open_hand(loop)
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
        "Two UR5e + 2F-85: draw out, take both sleeves, spread, drag-lay. Wrist camera within "
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
