"""Rotating infeed conveyor that turns a skewed shirt collar-downstream.

The steel drum is deco. Cloth on it is driven no-slip. After the heading
is undone, the sheet is laid onto the square T so the result is actually
square, then leftover sideways speed is cleared so it runs straight.
"""

from __future__ import annotations

import math

import numpy as np

from .shirt import SHIRT_RADIUS, shirt_rest_local, shirt_rigid_pose
from .sim_loop import smoothstep

SURFACE_Z = 0.562
TABLE_XY = np.array([-1.55, 0.0])
TABLE_Z0 = 0.500
SPAWN_X = -1.55


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
    """Turns the infeed disk. Cloth on it rides with no slip."""

    def __init__(self, model, data, *, qadr, rest, dadr) -> None:
        self.model = model
        self.data = data
        self._qadr = qadr
        self._rest = rest
        self._dadr = dadr
        self._table_mocap = int(model.body("orient_table").mocapid[0])
        self._xyz = np.arange(3)
        self._local_xy: np.ndarray | None = None
        self._local_z: np.ndarray | None = None
        self._world: np.ndarray | None = None
        self._yaw = 0.0
        self._center = TABLE_XY.copy()
        self._prev: np.ndarray | None = None
        self.reset()

    def reset(self) -> None:
        self._local_xy = None
        self._local_z = None
        self._world = None
        self._prev = None
        self._set_pose(0.0, TABLE_XY.copy())

    def park(self) -> None:
        self.reset()

    def apply(self) -> None:
        """Spin the disk; if a shirt is riding, carry it with no slip."""
        self._write_table()
        if self._world is not None:
            world = self._world
        elif self._local_xy is not None:
            world = self._posed_world()
        else:
            return
        vel = None
        if self._prev is not None:
            dt = max(float(self.model.opt.timestep), 1e-6)
            vel = (world - self._prev) / dt
        self.data.qpos[self._qadr[:, None] + self._xyz] = world - self._rest
        if vel is None:
            self.data.qvel[self._dadr[:, None] + self._xyz] = 0.0
        else:
            self.data.qvel[self._dadr[:, None] + self._xyz] = vel
        self._prev = np.asarray(world, dtype=float).copy()

    def cycle(self, line, targets: np.ndarray):
        """Rotate the live shirt, then lay it on the square infeed pose."""
        pos = np.asarray(line.positions(), dtype=float)
        yaw0 = _yaw_of(pos)
        center0 = pos[:, :2].mean(axis=0)
        self._local_xy = pos[:, :2] - center0
        self._local_z = pos[:, 2].copy()
        self._world = None
        self._prev = pos.copy()
        self._set_pose(0.0, center0)
        goal_xy = np.array([SPAWN_X, 0.0])
        seconds = 0.85 + 1.7 * abs(yaw0) / math.pi
        line._enter(
            "SPREAD",
            f"rotating conveyor turns {-math.degrees(yaw0):+.0f} deg",
        )
        yield from self._tween(line, 0.0, -yaw0, center0, goal_xy, seconds)
        start = self._posed_world()
        self._local_xy = None
        self._local_z = None
        square = np.asarray(targets, dtype=float).copy()
        square[:, 2] = SURFACE_Z + SHIRT_RADIUS
        line._enter("SPREAD", "conveyor settles the shirt square")
        steps = max(1, line._steps(0.45))
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            self._world = start + blend * (square - start)
            yield
        self._world = square.copy()
        yield from self._hold(line, 0.3)
        self._world = None
        self._prev = None
        self.data.qvel[self._dadr[:, None] + self._xyz] = 0.0
        yield from self._hold(line, 0.2)

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
        self._write_table()

    def _write_table(self) -> None:
        half = 0.5 * self._yaw
        self.data.mocap_pos[self._table_mocap] = (TABLE_XY[0], TABLE_XY[1], TABLE_Z0)
        self.data.mocap_quat[self._table_mocap] = (
            math.cos(half),
            0.0,
            0.0,
            math.sin(half),
        )

    def _tween(self, line, yaw0, yaw1, c0, c1, seconds: float):
        steps = max(1, line._steps(seconds))
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            self._set_pose(yaw0 + blend * (yaw1 - yaw0), c0 + blend * (c1 - c0))
            yield
        self._set_pose(yaw1, c1)

    def _hold(self, line, seconds: float):
        for _ in range(line._steps(seconds)):
            yield
