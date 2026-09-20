"""Dual-arm align station: two robot arms square a skewed garment's heading.

The infeed used to be two conveyors running at different speeds, which yawed
the product by dragging one side faster than the other. It is one plain belt
now. Two pedestal arms stand either side of it (align_rig.xml), and they do
the correcting: each drops its suction wrist onto its own half of the
garment, the pair lifts the sheet clear of the belt, swings it round about
its centre until the collar leads downstream (+X), walks it back to the lane
centre, and lays it down.

What the pair carries is the sheet exactly as the operator dropped it: the
lift keeps every vertex's height relative to the others, so the garment goes
to the press in the right *position*, still creased. Flattening is the
press's job, not this station's.

The arms are 2-link on a yaw turret and poses are scripted, same as the QC
reject arm: ``two_link_ik`` gives shoulder, elbow and wrist, and the mocap
bodies are written straight to those. Nothing here is a torque-controlled
robot; it is a kinematic stand-in with an honest reach envelope, and
``AlignStation.reach`` is what checks it.
"""

from __future__ import annotations

import math

import numpy as np

from .shirt import SHIRT_RADIUS, shirt_rest_local
from .sim_loop import smoothstep

SURFACE_Z = 0.562
SPAWN_X = -1.55
# Shoulders: on the pedestals' caps, either side of the belt rails.
SHOULDER_Y = 0.80
SHOULDER_Z = 0.80
ARM_L1 = 0.62
ARM_L2 = 0.68
# Wrist joint to the cups' lips: the IK solves for the wrist, the cup hangs
# below it.
ARM_WRIST = 0.10
# Where a cup sits on the garment, as a fraction of its half width: far
# enough out to have leverage on the heading, inside the sleeve tips so it
# grips body cloth rather than a hem.
GRIP_SPAN = 0.78
# Cup heights: touching the sheet, and carrying it clear of the belt.
GRIP_Z = SURFACE_Z + 0.012
CARRY_Z = SURFACE_Z + 0.16
# Parked, the wrists sit over their own pedestals, out of the belt.
PARK = 0.62  # |y| of the parked cups
PARK_Z = SURFACE_Z + 0.30
# A turn longer than this is done in two bites, so the cups never travel a
# reflex arc across the belt.
MAX_BITE = math.radians(115.0)
# Heading closer to downstream than this needs no second bite.
HEADING_OK = math.radians(3.0)


def _wrap(angle: float) -> float:
    return float((angle + math.pi) % (2.0 * math.pi) - math.pi)


def _heading(pos: np.ndarray, rest: np.ndarray | None = None) -> float:
    """Live heading: 0 when the neck/collar side leads downstream (+X).

    Uses rest-mesh bands (collar vs hem), not a rigid-fit yaw. A tank or
    pinafore is close to square, so SVD often locks onto the wrong axis.
    """
    if rest is None:
        rest = shirt_rest_local()
    axis = rest[:, 0]
    hi = float(np.quantile(axis, 0.88))
    lo = float(np.quantile(axis, 0.12))
    collar = pos[axis >= hi, :2].mean(axis=0)
    hem = pos[axis <= lo, :2].mean(axis=0)
    vec = collar - hem
    if float(np.linalg.norm(vec)) < 1e-6:
        return 0.0
    return _wrap(math.atan2(float(vec[1]), float(vec[0])))


def _yaw_of(pos: np.ndarray) -> float:
    """Back-compat alias: collar-downstream heading in radians."""
    return _heading(pos)


def _polar(yaw: float, elev: float) -> np.ndarray:
    return np.array(
        [math.cos(yaw) * math.cos(elev), math.sin(yaw) * math.cos(elev), math.sin(elev)]
    )


def two_link_ik(target, shoulder, l1: float, l2: float, *, elbow_up: bool = True):
    """Shoulder yaw, elbow and wrist for a 2-link arm reaching ``target``.

    ``target`` is the wrist joint, not the tool. A target out of the annulus
    is clamped onto it, so a pose is always returned and the arm simply falls
    short — which is what ``reach`` reports on rather than an exception in
    the middle of a cycle.
    """
    shoulder = np.asarray(shoulder, dtype=float)
    delta = np.asarray(target, dtype=float) - shoulder
    yaw = math.atan2(delta[1], delta[0])
    span = math.hypot(delta[0], delta[1])
    height = float(delta[2])
    dist = math.hypot(span, height)
    lo, hi = abs(l1 - l2) + 0.03, l1 + l2 - 0.03
    if dist < 1e-6:
        dist = lo
    scale = min(max(dist, lo), hi) / dist
    span, height = span * scale, height * scale
    dist = math.hypot(span, height)
    cos_elbow = (l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist)
    beta = math.acos(float(np.clip(cos_elbow, -1.0, 1.0)))
    gamma = math.atan2(height, span)
    elbow = shoulder + l1 * _polar(yaw, gamma + (beta if elbow_up else -beta))
    wrist = shoulder + np.array([span * math.cos(yaw), span * math.sin(yaw), height])
    return shoulder, elbow, wrist, yaw


def _quat_z_to(direction: np.ndarray) -> np.ndarray:
    """Unit quaternion that rotates local +Z onto ``direction``."""
    vec = np.asarray(direction, dtype=float)
    norm = float(np.linalg.norm(vec))
    if norm < 1e-9:
        return np.array([1.0, 0.0, 0.0, 0.0])
    vec = vec / norm
    cos = float(vec[2])
    if cos > 0.999999:
        return np.array([1.0, 0.0, 0.0, 0.0])
    if cos < -0.999999:
        return np.array([0.0, 1.0, 0.0, 0.0])
    axis = np.cross(np.array([0.0, 0.0, 1.0]), vec)
    quat = np.array([1.0 + cos, axis[0], axis[1], axis[2]])
    return quat / np.linalg.norm(quat)


class _Arm:
    """One pedestal arm: four mocap bodies posed from a cup position."""

    def __init__(self, model, data, side: str, sign: float) -> None:
        self.data = data
        self.sign = float(sign)
        self.shoulder = np.array([SPAWN_X, sign * SHOULDER_Y, SHOULDER_Z])
        self._yaw = int(model.body(f"align_{side}_yaw").mocapid[0])
        self._upper = int(model.body(f"align_{side}_upper").mocapid[0])
        self._fore = int(model.body(f"align_{side}_fore").mocapid[0])
        self._cup = int(model.body(f"align_{side}_cup").mocapid[0])
        self.home = np.array([SPAWN_X, sign * PARK, PARK_Z])

    def reach(self, cup) -> float:
        """How far the wrist target is from the shoulder, in metres."""
        wrist = np.asarray(cup, dtype=float) + np.array([0.0, 0.0, ARM_WRIST])
        return float(np.linalg.norm(wrist - self.shoulder))

    def cup(self) -> np.ndarray:
        return np.array(self.data.mocap_pos[self._cup], dtype=float)

    def pose(self, cup) -> None:
        cup = np.asarray(cup, dtype=float)
        wrist_target = cup + np.array([0.0, 0.0, ARM_WRIST])
        # Elbow away from the belt, so the links fold outboard and neither
        # arm leans over the garment it is not holding.
        shoulder, elbow, wrist, yaw = two_link_ik(
            wrist_target, self.shoulder, ARM_L1, ARM_L2
        )
        half = 0.5 * yaw
        data = self.data
        data.mocap_pos[self._yaw] = shoulder
        data.mocap_quat[self._yaw] = (math.cos(half), 0.0, 0.0, math.sin(half))
        data.mocap_pos[self._upper] = shoulder
        data.mocap_quat[self._upper] = _quat_z_to(elbow - shoulder)
        data.mocap_pos[self._fore] = elbow
        data.mocap_quat[self._fore] = _quat_z_to(wrist - elbow)
        data.mocap_pos[self._cup] = cup
        data.mocap_quat[self._cup] = (1.0, 0.0, 0.0, 0.0)


class AlignStation:
    """Two arms that pick a skewed garment up, turn it and put it back down.

    The garment is carried rigidly between the cups, so ``_world`` is the
    whole sheet's world positions and ``apply`` writes them every step — the
    same contract the belt-turner had, which is what lets ``xfold.line`` keep
    treating this as "the infeed holds the cloth".
    """

    def __init__(self, model, data, *, qadr, rest, dadr) -> None:
        self.model = model
        self.data = data
        self._qadr = qadr
        self._rest = rest
        self._dadr = dadr
        self._xyz = np.arange(3)
        self._rest_local = shirt_rest_local()
        self.arms = (
            _Arm(model, data, "l", 1.0),
            _Arm(model, data, "r", -1.0),
        )
        # The sheet in the pair's frame while it is held, its pose, and the
        # cup offsets from the centre in that same frame.
        self._local_xy: np.ndarray | None = None
        self._local_z: np.ndarray | None = None
        self._grip_local: np.ndarray | None = None
        self._world: np.ndarray | None = None
        self._prev: np.ndarray | None = None
        self._yaw = 0.0
        self._lift = 0.0
        self._center = np.array([SPAWN_X, 0.0])
        self.holding = False
        self.reset()

    # --- state ---------------------------------------------------------

    def reset(self) -> None:
        self._local_xy = None
        self._local_z = None
        self._grip_local = None
        self._world = None
        self._prev = None
        self._yaw = 0.0
        self._lift = 0.0
        self._center = np.array([SPAWN_X, 0.0])
        self.holding = False
        for arm in self.arms:
            arm.pose(arm.home)

    def park(self) -> None:
        self.reset()

    def release(self) -> None:
        self._world = None
        self._local_xy = None
        self._local_z = None
        self._grip_local = None
        self._prev = None
        self.holding = False
        self.data.qvel[self._dadr[:, None] + self._xyz] = 0.0

    def apply(self) -> None:
        """Write whatever pose the station is holding onto the cloth."""
        dt = max(float(self.model.opt.timestep), 1e-6)
        if self._world is not None:
            world = self._world
        elif self._local_xy is not None:
            world = self._posed_world()
        else:
            return
        vel = None if self._prev is None else (world - self._prev) / dt
        self.data.qpos[self._qadr[:, None] + self._xyz] = world - self._rest
        if vel is None:
            self.data.qvel[self._dadr[:, None] + self._xyz] = 0.0
        else:
            self.data.qvel[self._dadr[:, None] + self._xyz] = vel
        self._prev = np.asarray(world, dtype=float).copy()

    # --- the cycle -----------------------------------------------------

    def cycle(self, line, targets: np.ndarray | None = None):
        """Pick, turn to collar-downstream, set down. Creases are kept."""
        del targets
        pos = np.asarray(line.positions(), dtype=float)
        yaw0 = _heading(pos, self._rest_local)
        center0 = pos[:, :2].mean(axis=0)
        self._local_xy = pos[:, :2] - center0
        self._local_z = pos[:, 2].copy()
        self._world = None
        self._prev = pos.copy()
        self._grip_local = self._pick_grips(pos, center0)
        self._set_pose(0.0, center0, 0.0)

        line._enter(
            "ORIENT",
            f"arms take the garment {GRIP_SPAN:.2f} of its width apart, "
            f"{-math.degrees(yaw0):+.0f} deg to turn",
            measurements={"headingRad": float(yaw0)},
        )
        yield from self._reach_to_grips(line, 0.55)
        yield from self._hold(line, 0.20)
        self.holding = True

        line._enter("ORIENT", "both wrists on, the pair lifts the garment off the belt")
        yield from self._raise(line, CARRY_Z - GRIP_Z, 0.45)

        goal = np.array([SPAWN_X, 0.0])
        # One bite per MAX_BITE of turn: a half-turn in a single sweep would
        # walk a cup right across the belt and through the other arm.
        turn = -yaw0
        bites = max(1, int(math.ceil(abs(turn) / MAX_BITE)))
        for index in range(bites):
            span = turn / bites
            to = self._center + (goal - self._center) / (bites - index)
            line._enter(
                "ORIENT",
                f"arms swing the garment {math.degrees(span):+.0f} deg"
                + (f" (bite {index + 1} of {bites})" if bites > 1 else ""),
            )
            yield from self._tween(
                line, self._yaw, self._yaw + span, self._center, to, 0.75 + 0.5 * abs(span)
            )

        leftover = _heading(self._posed_world(), self._rest_local)
        if abs(leftover) > HEADING_OK:
            line._enter(
                "ORIENT",
                f"arms trim the last {-math.degrees(leftover):+.0f} deg",
                measurements={"headingRad": float(leftover)},
            )
            yield from self._tween(
                line, self._yaw, self._yaw - leftover, self._center, goal, 0.40
            )

        line._enter("ORIENT", "arms lay it back down, square on the belt")
        yield from self._raise(line, GRIP_Z - CARRY_Z, 0.45)
        yield from self._hold(line, 0.15)
        self.holding = False
        # Hand the sheet back as plain world positions: from here the belt
        # drives it, not the arms.
        self._world = self._posed_world()
        self._local_xy = None
        self._local_z = None
        self._grip_local = None
        line._enter("ORIENT", "wrists off, arms clear the belt")
        yield from self._retract(line, 0.55)

    # --- motion --------------------------------------------------------

    def _pick_grips(self, pos: np.ndarray, center) -> np.ndarray:
        """Cup offsets from the garment's centre, in the sheet's own frame.

        One per arm, on the transverse axis (shoulder to shoulder across the
        garment) so the pair has leverage on the heading. Each arm gets the
        side that is nearer to it once the garment is square, which is also
        the side it is nearer to now — the turn never swaps them.
        """
        rest = self._rest_local
        rel = pos[:, :2] - np.asarray(center, dtype=float)
        # The sheet's transverse axis in the world: rest y maps onto it.
        across = rest[:, 1]
        hi = float(np.quantile(across, 0.90))
        lo = float(np.quantile(across, 0.10))
        left = rel[across >= hi].mean(axis=0)
        right = rel[across <= lo].mean(axis=0)
        if left[1] < right[1]:
            left, right = right, left
        return np.array([left * GRIP_SPAN, right * GRIP_SPAN])

    def _grip_world(self) -> np.ndarray:
        """Where the two cups are, for this pose."""
        cos, sin = math.cos(self._yaw), math.sin(self._yaw)
        out = np.empty((2, 3))
        for index, offset in enumerate(self._grip_local):
            out[index, 0] = offset[0] * cos - offset[1] * sin + self._center[0]
            out[index, 1] = offset[0] * sin + offset[1] * cos + self._center[1]
            out[index, 2] = GRIP_Z + self._lift
        return out

    def _posed_world(self) -> np.ndarray:
        cos, sin = math.cos(self._yaw), math.sin(self._yaw)
        rel = self._local_xy
        world = np.empty((len(rel), 3))
        world[:, 0] = rel[:, 0] * cos - rel[:, 1] * sin + self._center[0]
        world[:, 1] = rel[:, 0] * sin + rel[:, 1] * cos + self._center[1]
        if self._local_z is not None:
            world[:, 2] = self._local_z + self._lift
        else:
            world[:, 2] = SURFACE_Z + SHIRT_RADIUS + self._lift
        return world

    def _set_pose(self, yaw: float, center, lift: float) -> None:
        self._yaw = float(yaw)
        self._center = np.asarray(center, dtype=float).copy()
        self._lift = float(lift)
        if self._grip_local is not None:
            for arm, cup in zip(self.arms, self._grip_world()):
                arm.pose(cup)

    def reach(self) -> float:
        """Worst of the two arms' current stretch, in metres. For tests."""
        if self._grip_local is None:
            return 0.0
        return max(arm.reach(cup) for arm, cup in zip(self.arms, self._grip_world()))

    def _reach_to_grips(self, line, seconds: float):
        """Both wrists from park down onto their grip points, over the top."""
        targets = self._grip_world()
        starts = [arm.cup() for arm in self.arms]
        over = [np.array([t[0], t[1], PARK_Z]) for t in targets]
        for blend in line._tween(0.55 * seconds):
            for arm, start, above in zip(self.arms, starts, over):
                arm.pose(start + (above - start) * blend)
            yield
        for blend in line._tween(0.45 * seconds):
            for arm, above, target in zip(self.arms, over, targets):
                arm.pose(above + (target - above) * blend)
            yield

    def _retract(self, line, seconds: float):
        starts = [arm.cup() for arm in self.arms]
        over = [np.array([s[0], s[1], PARK_Z]) for s in starts]
        for blend in line._tween(0.45 * seconds):
            for arm, start, above in zip(self.arms, starts, over):
                arm.pose(start + (above - start) * blend)
            yield
        for blend in line._tween(0.55 * seconds):
            for arm, above in zip(self.arms, over):
                arm.pose(above + (arm.home - above) * blend)
            yield

    def _raise(self, line, by: float, seconds: float):
        lift0 = self._lift
        for blend in line._tween(seconds):
            self._set_pose(self._yaw, self._center, lift0 + by * blend)
            yield

    def _tween(self, line, yaw0, yaw1, c0, c1, seconds: float):
        """Swing the pair from one pose to the next; the cups follow the sheet."""
        c0 = np.asarray(c0, dtype=float)
        c1 = np.asarray(c1, dtype=float)
        for blend in line._tween(seconds):
            self._set_pose(yaw0 + blend * (yaw1 - yaw0), c0 + blend * (c1 - c0), self._lift)
            yield
        self._set_pose(yaw1, c1, self._lift)

    def _hold(self, line, seconds: float):
        for _ in range(line._steps(seconds)):
            yield
