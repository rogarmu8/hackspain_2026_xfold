"""Dual conveyor product turner: two belts yaw a skewed shirt.

The shirt straddles a left (+Y) and right (−Y) lane. Both run at the same
speed while it rides forward. To correct heading, one lane speeds up and
the other slows; the speed difference pivots the sheet about +Z. Once the
collar leads downstream the lanes resync and the linear belt takes over.

Belts are not moving bodies. Cloth is carried no-slip, same as belt 1.
Slats on each lane scroll at that lane's speed so the differential is
visible.
"""

from __future__ import annotations

import math

import numpy as np

from .shirt import SHIRT_RADIUS, shirt_rest_local, shirt_rigid_pose
from .sim_loop import smoothstep

SURFACE_Z = 0.562
SPAWN_X = -1.55
# Lane centre-to-centre in Y. v_left − v_right = ω * TRACK.
TRACK = 0.50
TURNER_X0 = -2.10
TURNER_SPAN = 1.10  # x = -2.10 .. -1.00


def _wrap(angle: float) -> float:
    return float((angle + math.pi) % (2.0 * math.pi) - math.pi)


def _yaw_of(pos: np.ndarray) -> float:
    """Heading of the live T: 0 when the collar leads downstream (+X)."""
    rest = shirt_rest_local()
    _, yaw = shirt_rigid_pose(pos, rest)
    collar = int(np.argmax(rest[:, 0]))
    hem = int(np.argmin(rest[:, 0]))
    vec = pos[collar, :2] - pos[hem, :2]
    hem_yaw = math.atan2(float(vec[1]), float(vec[0]))
    if abs(_wrap(yaw - hem_yaw)) > abs(_wrap(yaw + math.pi - hem_yaw)):
        yaw = yaw + math.pi
    return _wrap(yaw)


class SpreadStation:
    """Two independent infeed belts. Differential speed yaws the shirt."""

    def __init__(self, model, data, *, qadr, rest, dadr) -> None:
        self.model = model
        self.data = data
        self._qadr = qadr
        self._rest = rest
        self._dadr = dadr
        self._xyz = np.arange(3)
        self._slats_l = np.array(
            [
                model.geom(i).id
                for i in range(model.ngeom)
                if model.geom(i).name.startswith("orient_slat_l_")
            ]
        )
        self._slats_r = np.array(
            [
                model.geom(i).id
                for i in range(model.ngeom)
                if model.geom(i).name.startswith("orient_slat_r_")
            ]
        )
        self._slat_l0 = model.geom_pos[self._slats_l, 0].copy()
        self._slat_r0 = model.geom_pos[self._slats_r, 0].copy()
        self._local_xy: np.ndarray | None = None
        self._world: np.ndarray | None = None
        self._prev: np.ndarray | None = None
        self._yaw = 0.0
        self._center = np.array([SPAWN_X, 0.0])
        self.v_left = 0.0
        self.v_right = 0.0
        self._travel_l = 0.0
        self._travel_r = 0.0
        self.reset()

    def reset(self) -> None:
        self._local_xy = None
        self._world = None
        self._prev = None
        self._yaw = 0.0
        self._center = np.array([SPAWN_X, 0.0])
        self.v_left = 0.0
        self.v_right = 0.0
        self._travel_l = 0.0
        self._travel_r = 0.0
        self._write_slats()

    def park(self) -> None:
        self.reset()

    def apply(self) -> None:
        """Scroll both lanes; if a shirt is riding, carry it with no slip."""
        dt = max(float(self.model.opt.timestep), 1e-6)
        self._travel_l += self.v_left * dt
        self._travel_r += self.v_right * dt
        self._write_slats()
        if self._world is not None:
            world = self._world
        elif self._local_xy is not None:
            world = self._posed_world()
        else:
            return
        vel = None
        if self._prev is not None:
            vel = (world - self._prev) / dt
        self.data.qpos[self._qadr[:, None] + self._xyz] = world - self._rest
        if vel is None:
            self.data.qvel[self._dadr[:, None] + self._xyz] = 0.0
        else:
            self.data.qvel[self._dadr[:, None] + self._xyz] = vel
        self._prev = np.asarray(world, dtype=float).copy()

    def cycle(self, line, targets: np.ndarray):
        """Yaw with a belt-speed split, resync, then lay the square T."""
        pos = np.asarray(line.positions(), dtype=float)
        yaw0 = _yaw_of(pos)
        center0 = pos[:, :2].mean(axis=0)
        self._local_xy = pos[:, :2] - center0
        self._world = None
        self._prev = pos.copy()
        self._set_pose(0.0, center0)
        goal_xy = np.array([SPAWN_X, 0.0])
        turn = 0.90 + 1.6 * abs(yaw0) / math.pi
        faster = "left" if yaw0 > 0.0 else "right"
        line._enter(
            "ORIENT",
            f"dual belts: {faster} lane leads, "
            f"turns {-math.degrees(yaw0):+.0f} deg",
        )
        yield from self._tween(line, 0.0, -yaw0, center0, goal_xy, turn)
        line._enter("ORIENT", "dual belts resync, shirt runs straight")
        yield from self._resync(line, 0.40)
        start = self._posed_world()
        self._local_xy = None
        square = np.asarray(targets, dtype=float).copy()
        square[:, 2] = SURFACE_Z + SHIRT_RADIUS
        line._enter("ORIENT", "turner settles the shirt square")
        steps = max(1, line._steps(0.40))
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            self._world = start + blend * (square - start)
            self.v_left = self.v_right = 0.0
            yield
        self._world = square.copy()
        yield from self._hold(line, 0.25)

    def release(self) -> None:
        self._world = None
        self._local_xy = None
        self._prev = None
        self.v_left = self.v_right = 0.0
        self.data.qvel[self._dadr[:, None] + self._xyz] = 0.0

    def _posed_world(self) -> np.ndarray:
        cos, sin = math.cos(self._yaw), math.sin(self._yaw)
        rel = self._local_xy
        world = np.empty((len(rel), 3))
        world[:, 0] = rel[:, 0] * cos - rel[:, 1] * sin + self._center[0]
        world[:, 1] = rel[:, 0] * sin + rel[:, 1] * cos + self._center[1]
        world[:, 2] = SURFACE_Z + SHIRT_RADIUS
        return world

    def _set_pose(self, yaw: float, center: np.ndarray) -> None:
        self._yaw = float(yaw)
        self._center = np.asarray(center, dtype=float).copy()

    def _tween(self, line, yaw0, yaw1, c0, c1, seconds: float):
        """Yaw and walk the centre; belt speeds follow ω and v_forward."""
        steps = max(1, line._steps(seconds))
        dt = line.dt
        prev_yaw, prev_c = yaw0, np.asarray(c0, dtype=float)
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            yaw = yaw0 + blend * (yaw1 - yaw0)
            center = c0 + blend * (c1 - c0)
            omega = (yaw - prev_yaw) / dt
            v_fwd = float(center[0] - prev_c[0]) / dt
            # ωẑ × (TRACK/2 ŷ) = −ω (TRACK/2) x̂ on the left lane.
            self.v_left = v_fwd - omega * (0.5 * TRACK)
            self.v_right = v_fwd + omega * (0.5 * TRACK)
            self._set_pose(yaw, center)
            prev_yaw, prev_c = yaw, np.asarray(center, dtype=float)
            yield
        self.v_left = self.v_right = 0.0
        self._set_pose(yaw1, c1)

    def _resync(self, line, seconds: float):
        """Both lanes at the same speed, no more yaw."""
        steps = max(1, line._steps(seconds))
        for index in range(steps):
            blend = 1.0 - smoothstep((index + 1) / steps)
            self.v_left = self.v_right = 0.12 * blend
            yield
        self.v_left = self.v_right = 0.0

    def _hold(self, line, seconds: float):
        self.v_left = self.v_right = 0.0
        for _ in range(line._steps(seconds)):
            yield

    def _write_slats(self) -> None:
        if self._slats_l.size:
            self.model.geom_pos[self._slats_l, 0] = (
                TURNER_X0 + (self._slat_l0 - TURNER_X0 + self._travel_l) % TURNER_SPAN
            )
        if self._slats_r.size:
            self.model.geom_pos[self._slats_r, 0] = (
                TURNER_X0 + (self._slat_r0 - TURNER_X0 + self._travel_r) % TURNER_SPAN
            )
