"""Vapour under the platen, and the flex hose that feeds it.

Puffs and hose segments are visual-only geoms. Positions, sizes and alpha are
rewritten each frame: the hose is a sagging curve from the supply barb on the
beam down to the head, and the vapour seeps out, billows, and fades.
"""

from __future__ import annotations

import math

import numpy as np

ALPHA = 0.44
PLATEN_HALF_X = 0.34
PLATEN_HALF_Y = 0.37

HOSE_RADIUS = 0.016
HOSE_RIB = 0.021
PLATEN_Z0 = 1.34
HOSE_INLET_LOCAL = np.array([-0.14, 0.16, 0.088])
HOSE_BARB = np.array([-0.24, 0.16, 1.40])
STROKE_SPAN = 0.755


def _bezier(p0, p1, p2, p3, count: int) -> np.ndarray:
    t = np.linspace(0.0, 1.0, count)
    omt = 1.0 - t
    return (
        (omt**3)[:, None] * p0
        + (3.0 * omt**2 * t)[:, None] * p1
        + (3.0 * omt * t**2)[:, None] * p2
        + (t**3)[:, None] * p3
    )


class SteamField:
    def __init__(self, model) -> None:
        import mujoco

        self.model = model
        self._mujoco = mujoco
        self.ids = [
            i
            for i in range(model.ngeom)
            if model.geom(i).name.startswith("steam_")
            and model.geom(i).name.split("_")[-1].isdigit()
        ]
        self.origins = model.geom_pos[self.ids].copy()
        self.sizes = model.geom_size[self.ids].copy()
        self.hose_ids = [
            i
            for i in range(model.ngeom)
            if model.geom(i).name.startswith("hose_")
            and model.geom(i).name.split("_")[-1].isdigit()
        ]
        self.stroke_adr = int(np.atleast_1d(model.joint("press_stroke").qposadr)[0])

    def reset(self) -> None:
        for index, geom_id in enumerate(self.ids):
            self.model.geom_pos[geom_id] = self.origins[index]
            self.model.geom_size[geom_id] = self.sizes[index]
            self.model.geom_rgba[geom_id, 3] = 0.0

    def follow(self, data) -> None:
        """Drape the hose from the boiler to the current head height."""
        if not self.hose_ids:
            return
        stroke = float(data.qpos[self.stroke_adr])
        slack = 1.0 - min(1.0, abs(stroke) / STROKE_SPAN)
        start = HOSE_BARB.astype(float)
        finish = np.array(
            [
                HOSE_INLET_LOCAL[0],
                HOSE_INLET_LOCAL[1],
                PLATEN_Z0 + stroke + HOSE_INLET_LOCAL[2],
            ]
        )
        # Two authored loops, blended by stroke. Endpoints alone are only
        # centimetres apart when the head is up, so the slack has to live in
        # the control points or the hose bunches on the beam. The loop swings
        # forward of the ram barrel (y >= 0.10 keeps it off the cylinder).
        open_a = np.array([-0.02, 0.26, 1.18])
        open_b = np.array([0.04, 0.10, 1.08])
        shut_a = np.array([-0.16, 0.22, 1.16])
        shut_b = np.array([-0.10, 0.14, 0.80])
        control_a = shut_a + slack * (open_a - shut_a)
        control_b = shut_b + slack * (open_b - shut_b)
        points = _bezier(start, control_a, control_b, finish, len(self.hose_ids) + 1)
        quat = np.zeros(4)
        for index, geom_id in enumerate(self.hose_ids):
            a, b = points[index], points[index + 1]
            delta = b - a
            length = float(np.linalg.norm(delta))
            if length < 1e-4:
                continue
            self.model.geom_pos[geom_id] = 0.5 * (a + b)
            self.model.geom_size[geom_id] = (
                HOSE_RIB if index % 2 else HOSE_RADIUS,
                0.5 * length,
                self.model.geom_size[geom_id, 2],
            )
            self._mujoco.mju_quatZ2Vec(quat, delta)
            self.model.geom_quat[geom_id] = quat

    def pulse(self, loop, seconds: float) -> bool:
        """Emit puffs that seep out, billow, and fade."""
        steps = loop.steps_for(seconds)
        for step_index in range(steps):
            self.follow(loop.data)
            self.puff(step_index * loop.model.opt.timestep, seconds)
            if not loop.step():
                self.reset()
                return False
        self.reset()
        return loop.running

    def puff(self, elapsed: float, seconds: float) -> None:
        """One frame of a pulse ``seconds`` long, ``elapsed`` into it."""
        attack = min(1.0, elapsed / 0.45)
        release = min(1.0, max(0.0, (seconds - elapsed) / 1.1))
        self._update(elapsed, attack * release)

    def _update(self, elapsed: float, envelope: float) -> None:
        for index, geom_id in enumerate(self.ids):
            period = 1.55 + 0.12 * (index % 5)
            phase = (elapsed / period + index * 0.137) % 1.0
            x, y, z = (float(value) for value in self.origins[index])

            swirl = elapsed * 1.8 + index * 0.7
            seep = min(1.0, phase / 0.28)
            billow = max(0.0, phase - 0.22)
            x += math.copysign((0.05 * seep + 0.10 * billow), x or 1.0)
            y += math.copysign((0.05 * seep + 0.11 * billow), y or 1.0)
            x += 0.016 * math.sin(swirl) * phase
            y += 0.016 * math.cos(swirl * 1.2) * phase
            z += 0.010 * seep + 0.04 * billow + 0.05 * billow * billow

            base = self.sizes[index]
            self.model.geom_pos[geom_id] = (x, y, z)
            self.model.geom_size[geom_id] = (
                base[0] * (0.9 + 1.7 * phase),
                base[1] * (0.9 + 1.8 * phase),
                base[2] * (0.85 + 1.1 * phase),
            )
            life = math.sin(math.pi * phase) ** 1.05
            haze = 0.7 + 0.3 * math.sin(elapsed * 2.4 + index)
            self.model.geom_rgba[geom_id, :3] = (0.93, 0.95, 0.98)
            self.model.geom_rgba[geom_id, 3] = ALPHA * envelope * life * haze
