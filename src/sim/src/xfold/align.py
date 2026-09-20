"""Infeed align: both arms turn and place on a leading–opposite diagonal.

The turn is always the short way (closest side to collar-downstream). The
pair is the diagonal that stays split across the belt for that yaw, so the
far arm (+Y) and the aisle arm (−Y) never swap sides and the links do not
cross. A slide still puts one cup on the corner closest to the glide and
the other on the opposite corner, assigned the same way: far cup to the
left arm, aisle cup to the right. Creases stay; flattening is the press's
job. The sheet is not lifted.

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
# Cup sits on cloth, not hovering. The sheet never leaves this height.
GRIP_Z = SURFACE_Z + 0.012
# Parked, the wrists sit over their own pedestals, out of the belt.
PARK = 0.62  # |y| of the parked cups
PARK_Z = SURFACE_Z + 0.30
# Overview / aisle camera is on −Y; far pedestal is +Y (left), aisle is −Y.
# A turn longer than this is done in two bites so the cups stay on the deck.
MAX_BITE = math.radians(115.0)
# Heading closer to downstream than this needs no trim.
HEADING_OK = math.radians(3.0)
GOAL = np.array([SPAWN_X, 0.0])
# Rest-frame diagonals: a leading corner always takes the opposite one.
_OPPOSITE = {
    "collar-left": "hem-right",
    "hem-right": "collar-left",
    "collar-right": "hem-left",
    "hem-left": "collar-right",
}
_PAIRS = (
    ("collar-left", "hem-right"),
    ("collar-right", "hem-left"),
)
# Stop this many radians before the two cups would meet on the belt spine.
_SWAP_MARGIN = math.radians(10.0)


def _wrap(angle: float) -> float:
    return float((angle + math.pi) % (2.0 * math.pi) - math.pi)


def _heading_glide(heading: float, turn: float) -> np.ndarray:
    """World-XY direction the collar travels for a remaining yaw ``turn``.

    Aisle view: +X is right (downstream), +Y is top (far). CCW sends the
    collar toward top-right; CW toward bottom-right.
    """
    tangent_ccw = np.array([-math.sin(heading), math.cos(heading)])
    if abs(turn) < 1e-9:
        return np.array([1.0, 0.0])
    return tangent_ccw * (1.0 if turn > 0.0 else -1.0)


def _quadrant_name(direction) -> str:
    """Aisle-view name of a glide: top/bottom × left/right."""
    vec = np.asarray(direction, dtype=float)
    ns = "top" if vec[1] >= 0.0 else "bottom"
    ew = "right" if vec[0] >= 0.0 else "left"
    return f"{ns}-{ew}"


def _shortest_delta(yaw0: float, yaw1: float) -> float:
    """Signed angle in (−π, π] from ``yaw0`` to ``yaw1``."""
    return _wrap(yaw1 - yaw0)


def _rotate_xy(rest, heading: float) -> np.ndarray:
    """Rest-frame XY after a heading about +Z (collar-downstream = 0)."""
    rest = np.asarray(rest, dtype=float)
    cos, sin = math.cos(heading), math.sin(heading)
    return np.array(
        [rest[0] * cos - rest[1] * sin, rest[0] * sin + rest[1] * cos]
    )


def _y_swap_clearance(rest_a, rest_b, heading: float, turn: float) -> float:
    """Radians we can yaw with ``sign(turn)`` before the two points swap Y."""
    if abs(turn) < 1e-9:
        return 0.0
    rest_a = np.asarray(rest_a, dtype=float)
    rest_b = np.asarray(rest_b, dtype=float)
    ya = float(_rotate_xy(rest_a, heading)[1])
    yb = float(_rotate_xy(rest_b, heading)[1])
    if abs(ya - yb) < 0.04:
        return 0.0
    dx = float(rest_a[0] - rest_b[0])
    dy = float(rest_a[1] - rest_b[1])
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return abs(turn)
    # world_y(a) − world_y(b) = dx sin ψ + dy cos ψ = 0
    base = math.atan2(-dy, dx)
    sign = 1.0 if turn > 0.0 else -1.0
    best = None
    for k in (-2, -1, 0, 1, 2):
        delta = _wrap(base + k * math.pi - heading)
        if delta * sign <= 1e-4:
            continue
        dist = abs(delta)
        if best is None or dist < best:
            best = dist
    return float(best if best is not None else math.pi)


def _best_rotate_pair(
    corners: dict, heading: float, turn: float
) -> tuple[tuple[str, str], float]:
    """Diagonal that stays split across the belt longest for this turn."""
    best_pair = _PAIRS[0]
    best_clr = -1.0
    for pair in _PAIRS:
        clr = _y_swap_clearance(corners[pair[0]], corners[pair[1]], heading, turn)
        if clr > best_clr:
            best_clr = clr
            best_pair = pair
    return best_pair, best_clr


def _far_and_aisle(corners: dict, pair: tuple[str, str], heading: float) -> tuple[str, str]:
    """Far (+Y) corner first, aisle (−Y) second, at this heading."""
    ranked = sorted(
        pair, key=lambda name: float(_rotate_xy(corners[name], heading)[1]), reverse=True
    )
    return ranked[0], ranked[1]


def _orbit(shoulder, start, end, blend: float, *, side: float = 0.0) -> np.ndarray:
    """Cup pose along a yaw about ``shoulder``.

    A straight lerp between the cups walks one wrist through the other arm.
    Default is the short arc; if ``side`` is set, prefer the arc whose
    midpoint stays on that half of the belt (far +, aisle −).
    """
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    origin = np.asarray(shoulder[:2], dtype=float)
    rs = start[:2] - origin
    re = end[:2] - origin
    r0 = float(math.hypot(float(rs[0]), float(rs[1])))
    r1 = float(math.hypot(float(re[0]), float(re[1])))
    if r0 < 1e-4 or r1 < 1e-4:
        return start + (end - start) * blend
    a0 = math.atan2(float(rs[1]), float(rs[0]))
    short = _shortest_delta(a0, math.atan2(float(re[1]), float(re[0])))
    delta = short
    if abs(side) > 1e-6 and abs(short) > 1e-4:
        long = short - 2.0 * math.pi if short > 0.0 else short + 2.0 * math.pi
        r_mid = 0.5 * (r0 + r1)

        def _mid_y(span: float) -> float:
            ang = a0 + 0.5 * span
            return origin[1] + r_mid * math.sin(ang)

        if _mid_y(short) * side < -1e-3 and _mid_y(long) * side >= -1e-3:
            delta = long
    a = a0 + delta * blend
    r = r0 + (r1 - r0) * blend
    z = float(start[2] + (end[2] - start[2]) * blend)
    return np.array([origin[0] + r * math.cos(a), origin[1] + r * math.sin(a), z])


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
        # Elbow away from the belt, so the links fold outboard.
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
    """Both arms turn and relocate; the pair follows the glide direction.

    The garment is posed rigidly in the belt plane, so ``_world`` is the
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
        self.left = _Arm(model, data, "l", 1.0)
        self.right = _Arm(model, data, "r", -1.0)
        # (arm, captured-frame cup offset) while a wrist is on the sheet.
        self._grips: list[tuple[_Arm, np.ndarray]] = []
        self._local_xy: np.ndarray | None = None
        self._local_z: np.ndarray | None = None
        self._world: np.ndarray | None = None
        self._prev: np.ndarray | None = None
        self._yaw = 0.0
        self._lift = 0.0
        self._center = np.array([SPAWN_X, 0.0])
        self._capture_yaw = 0.0
        self._pair_ids: frozenset[str] | None = None
        self._pair_label = ""
        self.holding = False
        self.reset()

    # --- state ---------------------------------------------------------

    def reset(self) -> None:
        self._local_xy = None
        self._local_z = None
        self._grips = []
        self._world = None
        self._prev = None
        self._yaw = 0.0
        self._lift = 0.0
        self._center = np.array([SPAWN_X, 0.0])
        self._capture_yaw = 0.0
        self._pair_ids = None
        self._pair_label = ""
        self.holding = False
        self.left.pose(self.left.home)
        self.right.pose(self.right.home)

    def park(self) -> None:
        self.reset()

    def release(self) -> None:
        self._world = None
        self._local_xy = None
        self._local_z = None
        self._grips = []
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
        """Both arms take a leading–opposite diagonal, turn, then slide. No lift."""
        del targets
        pos = np.asarray(line.positions(), dtype=float)
        yaw0 = _heading(pos, self._rest_local)
        center0 = pos[:, :2].mean(axis=0)
        self._local_xy = pos[:, :2] - center0
        self._local_z = pos[:, 2].copy()
        self._world = None
        self._prev = pos.copy()
        self._capture_yaw = float(yaw0)
        self._pair_ids = None
        self._set_pose(0.0, center0, 0.0)
        turn = _shortest_delta(0.0, -yaw0)

        bites = max(1, int(math.ceil(abs(turn) / MAX_BITE))) if abs(turn) > 1e-4 else 0
        if bites:
            yield from self._hold_for_direction(line, _heading_glide(yaw0, turn))
            line._enter(
                "ORIENT",
                f"glides towards {_quadrant_name(_heading_glide(yaw0, turn))}, "
                f"{math.degrees(turn):+.0f} deg on the belt",
                measurements={"headingRad": float(yaw0)},
            )
            for index in range(bites):
                leftover = _heading(self._posed_world(), self._rest_local)
                remaining = _shortest_delta(0.0, -leftover)
                if index > 0:
                    yield from self._hold_for_direction(
                        line, _heading_glide(leftover, remaining)
                    )
                span = turn / bites
                line._enter(
                    "ORIENT",
                    f"glides on the {self._pair_label} {math.degrees(span):+.0f} deg"
                    + (f" (bite {index + 1} of {bites})" if bites > 1 else "")
                    + ", garment stays on the belt",
                )
                yield from self._tween(
                    line,
                    self._yaw,
                    self._yaw + span,
                    self._center,
                    self._center,
                    0.70 + 0.45 * abs(span),
                )

        leftover = _heading(self._posed_world(), self._rest_local)
        if abs(leftover) > HEADING_OK:
            trim = _shortest_delta(0.0, -leftover)
            yield from self._hold_for_direction(line, _heading_glide(leftover, trim))
            line._enter(
                "ORIENT",
                f"trims the last {math.degrees(trim):+.0f} deg on the {self._pair_label}",
                measurements={"headingRad": float(leftover)},
            )
            yield from self._tween(
                line, self._yaw, self._yaw + trim, self._center, self._center, 0.35
            )

        goal = GOAL.astype(float)
        leftover = _heading(self._posed_world(), self._rest_local)
        trim = _shortest_delta(0.0, -leftover)
        slide = goal - self._center
        if float(np.linalg.norm(slide)) > 0.008:
            direction = slide
        elif abs(trim) > HEADING_OK:
            direction = _heading_glide(leftover, trim)
        else:
            direction = None
        if direction is not None:
            yield from self._hold_for_direction(line, direction)
            line._enter(
                "ORIENT",
                f"slides onto the lane towards {_quadrant_name(direction)}"
                + (
                    f", {math.degrees(trim):+.0f} deg leftover"
                    if abs(trim) > HEADING_OK
                    else ""
                ),
            )
            yield from self._tween(
                line, self._yaw, self._yaw + trim, self._center, goal, 0.70
            )

        leftover = _heading(self._posed_world(), self._rest_local)
        line._enter(
            "ORIENT",
            f"square on the belt ({math.degrees(leftover):+.0f} deg), wrinkles kept",
            measurements={"headingRad": float(leftover)},
        )
        yield from self._dwell(line, 0.12)
        self.holding = False
        self._world = self._posed_world()
        self._local_xy = None
        self._local_z = None
        self._grips = []
        self._pair_ids = None
        line._enter("ORIENT", "wrists off, arms clear the belt")
        yield from self._glide_home(line, 0.50)

    # --- motion --------------------------------------------------------

    def _sheet_corners(self) -> list[tuple[str, np.ndarray]]:
        """Named cup points in the sheet's own frame, inset onto the panel."""
        rest = self._rest_local
        cx = float(np.quantile(rest[:, 0], 0.86))
        hx = float(np.quantile(rest[:, 0], 0.14))
        ly = float(np.quantile(rest[:, 1], 0.86))
        ry = float(np.quantile(rest[:, 1], 0.14))
        inset = 0.90
        return [
            ("collar-left", np.array([cx, ly]) * inset),
            ("hem-left", np.array([hx, ly]) * inset),
            ("collar-right", np.array([cx, ry]) * inset),
            ("hem-right", np.array([hx, ry]) * inset),
        ]

    def _capture_offset(self, rest_xy, yaw0: float) -> np.ndarray:
        """Rest-frame cup → offset in the captured sheet frame (``_local_xy``)."""
        rest_xy = np.asarray(rest_xy, dtype=float)
        cos, sin = math.cos(yaw0), math.sin(yaw0)
        return np.array(
            [
                rest_xy[0] * cos - rest_xy[1] * sin,
                rest_xy[0] * sin + rest_xy[1] * cos,
            ]
        )

    def _grips_for_direction(
        self, direction
    ) -> tuple[str, list[tuple[_Arm, np.ndarray]], frozenset[str]]:
        """Cup on the corner closest to ``direction``, other cup on the opposite."""
        vec = np.asarray(direction, dtype=float)
        norm = float(np.linalg.norm(vec))
        vec = vec / norm if norm > 1e-9 else np.array([1.0, 0.0])
        names = dict(self._sheet_corners())
        scored: list[tuple[float, float, str]] = []
        for name, rest in names.items():
            offset = self._capture_offset(rest, self._capture_yaw)
            rel = self._cup_at(offset)[:2] - self._center
            scored.append((float(np.dot(rel, vec)), float(rel[0]), name))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        leading = scored[0][2]
        opposite = _OPPOSITE[leading]
        pair = {leading, opposite}
        left_name = next(name for name in pair if names[name][1] > 0)
        right_name = next(name for name in pair if names[name][1] <= 0)
        grips = [
            (self.left, self._capture_offset(names[left_name], self._capture_yaw)),
            (self.right, self._capture_offset(names[right_name], self._capture_yaw)),
        ]
        return f"{leading} and {opposite}", grips, frozenset(pair)

    def _hold_for_direction(self, line, direction):
        """Put the cups on the leading–opposite pair for this glide, if needed."""
        label, grips, ids = self._grips_for_direction(direction)
        self._pair_label = label
        if ids == self._pair_ids and self.holding:
            return
        self.holding = False
        self._grips = grips
        self._pair_ids = ids
        line._enter(
            "ORIENT",
            f"both arms take the {label}, towards {_quadrant_name(direction)}",
        )
        yield from self._glide_grips(line, 0.50)
        yield from self._dwell(line, 0.12)
        self.holding = True

    def _cup_at(self, offset) -> np.ndarray:
        """Where a cup sits for this pose."""
        offset = np.asarray(offset, dtype=float)
        cos, sin = math.cos(self._yaw), math.sin(self._yaw)
        return np.array(
            [
                offset[0] * cos - offset[1] * sin + self._center[0],
                offset[0] * sin + offset[1] * cos + self._center[1],
                GRIP_Z + self._lift,
            ]
        )

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
        for arm, offset in self._grips:
            arm.pose(self._cup_at(offset))

    def reach(self) -> float:
        """Worst active stretch, in metres. For tests."""
        if not self._grips:
            return 0.0
        return max(arm.reach(self._cup_at(offset)) for arm, offset in self._grips)

    def _glide_grips(self, line, seconds: float):
        """Swing every active cup onto its current sheet point — descending, no hop."""
        starts = [arm.cup() for arm, _ in self._grips]
        ends = [self._cup_at(offset) for _, offset in self._grips]
        for blend in line._tween(seconds):
            for (arm, _), start, end in zip(self._grips, starts, ends):
                arm.pose(_orbit(arm.shoulder, start, end, blend))
            yield

    def _glide_home(self, line, seconds: float):
        moves = ((self.left, self.left.home), (self.right, self.right.home))
        starts = [arm.cup() for arm, _ in moves]
        for blend in line._tween(seconds):
            for (arm, home), start in zip(moves, starts):
                arm.pose(_orbit(arm.shoulder, start, home, blend))
            yield

    def _tween(self, line, yaw0, yaw1, c0, c1, seconds: float):
        """Slide the sheet in the belt plane; cups ride the held points."""
        c0 = np.asarray(c0, dtype=float)
        c1 = np.asarray(c1, dtype=float)
        delta = _shortest_delta(yaw0, yaw1)
        for blend in line._tween(seconds):
            self._set_pose(yaw0 + blend * delta, c0 + blend * (c1 - c0), 0.0)
            yield
        self._set_pose(yaw0 + delta, c1, 0.0)

    def _dwell(self, line, seconds: float):
        for _ in range(line._steps(seconds)):
            yield
