"""Scripted Japanese / ninja fold on the shirt flex (no arms yet).

SOLUTION.md §5.3, sequential fallback (one gripper at a time):

  1. Flip the left third over the left crease onto the centre.
  2. Pause.
  3. Flip the right third over the right crease.
  4. Pause.
  5. Fold the hem up toward the collar.
  6. Ease the springs off so the packet is not yanked when we let go.

A rigid 180° target plus a hard force cutoff is what made the shirt
explode at the end: edge equalities were miles from rest, then we zeroed
the springs in one step. Softer springs, only the moving panel, a drape
(not a through-the-table invert), and a fade-out keep the solver happy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xfold.ninja import landmarks

HOLD = 0.9
FLIP = 2.8
HEM = 2.6
RELEASE = 1.8
# Stop short of π so the panel drapes onto the sheet instead of inverting
# through it (that stretch is what blew the equalities).
FOLD_ANGLE = 0.88 * np.pi
LIFT = 0.05
ANCHOR_HALF = 0.04
FOLD_HZ = 7.0
FOLD_LIMIT = 18.0  # × vertex weight
VEL_CAP = 2.5
BUTTON_BODY = "ninja_button"


def _ease(u: float) -> float:
    u = float(np.clip(u, 0.0, 1.0))
    return u * u * (3.0 - 2.0 * u)


def _rotate_y(points: np.ndarray, hinge_x: float, hinge_z: float, theta: float) -> np.ndarray:
    """Rotate about +Y (hem → collar). +θ lifts a panel with x < hinge."""
    out = points.copy()
    dx = points[:, 0] - hinge_x
    dz = points[:, 2] - hinge_z
    c, s = np.cos(theta), np.sin(theta)
    out[:, 0] = hinge_x + dx * c + dz * s
    out[:, 2] = hinge_z - dx * s + dz * c
    return out


def _rotate_x(points: np.ndarray, hinge_y: float, hinge_z: float, theta: float) -> np.ndarray:
    """Rotate about +X. +θ lifts a panel with y < hinge (hem toward collar)."""
    out = points.copy()
    dy = points[:, 1] - hinge_y
    dz = points[:, 2] - hinge_z
    c, s = np.cos(theta), np.sin(theta)
    out[:, 1] = hinge_y + dy * c + dz * s
    out[:, 2] = hinge_z - dy * s + dz * c
    return out


@dataclass
class _Phase:
    name: str
    duration: float
    left: float
    right: float
    hem: float
    fade: bool = False


_PHASES = (
    _Phase("left third → centre", FLIP, 1.0, 0.0, 0.0),
    _Phase("pause", HOLD, 1.0, 0.0, 0.0),
    _Phase("right third → centre", FLIP, 1.0, 1.0, 0.0),
    _Phase("pause", HOLD, 1.0, 1.0, 0.0),
    _Phase("hem → collar", HEM, 1.0, 1.0, 1.0),
    _Phase("settle", HOLD, 1.0, 1.0, 1.0),
    _Phase("release", RELEASE, 1.0, 1.0, 1.0, fade=True),
)


class NinjaFoldDemo:
    """Drive the three ninja creases. start() / stop() / apply(dt)."""

    def __init__(self, model, data):
        self._model = model
        self._data = data
        self._vert_body = np.asarray(model.flex_vertbodyid, dtype=np.int64)
        self._lm = landmarks(model)
        self._rest = self._rest_xy()
        self._masks = self._panels(self._rest)
        self._p0: np.ndarray | None = None
        self._hinge_z = 0.008
        self._left_c = float(self._masks["left_c"])
        self._right_c = float(self._masks["right_c"])
        self._hem_c = float(self._masks["hem_c"])
        self._t = 0.0
        self._phase = -1
        self._phase_t = 0.0
        self.hands: list[np.ndarray] = []
        self.status = "idle"

    @property
    def active(self) -> bool:
        return self._phase >= 0

    def _rest_xy(self) -> np.ndarray:
        xpos0 = getattr(self._model, "flexvert_xpos0", None)
        if xpos0 is not None and np.size(xpos0) >= 3:
            return np.asarray(xpos0, dtype=np.float64).reshape(-1, 3)[:, :2]
        from xfold.ninja import rest_xy

        return rest_xy(self._model)

    @staticmethod
    def _panels(xy: np.ndarray) -> dict[str, np.ndarray]:
        x, y = xy[:, 0], xy[:, 1]
        x1, x2 = float(x.min()), float(x.max())
        y1, y2 = float(y.min()), float(y.max())
        w = x2 - x1
        left_c = x1 + w / 3.0
        right_c = x2 - w / 3.0
        hem_c = y1 + 0.45 * (y2 - y1)
        return {
            "left": x < left_c,
            "right": x > right_c,
            "hem": y < hem_c,
            "left_c": left_c,
            "right_c": right_c,
            "hem_c": hem_c,
            "anchor_l": np.abs(x - left_c) <= ANCHOR_HALF,
            "anchor_r": np.abs(x - right_c) <= ANCHOR_HALF,
            "anchor_h": np.abs(y - hem_c) <= ANCHOR_HALF,
        }

    def start(self) -> str:
        pos = np.asarray(self._data.flexvert_xpos, dtype=np.float64).reshape(-1, 3)
        self._p0 = pos.copy()
        m = self._masks
        self._left_c = (
            float(np.percentile(pos[m["left"], 0], 90)) if m["left"].any() else float(m["left_c"])
        )
        self._right_c = (
            float(np.percentile(pos[m["right"], 0], 10)) if m["right"].any() else float(m["right_c"])
        )
        self._hem_c = (
            float(np.percentile(pos[m["hem"], 1], 90)) if m["hem"].any() else float(m["hem_c"])
        )
        self._hinge_z = float(np.median(pos[:, 2]))
        self._t = 0.0
        self._phase = 0
        self._phase_t = 0.0
        self.status = _PHASES[0].name
        return f"ninja fold: {_PHASES[0].name}"

    def stop(self) -> None:
        if self._vert_body.size:
            self._data.xfrc_applied[self._vert_body, :3] = 0.0
        self._damp_velocities(0.0)
        self._phase = -1
        self._p0 = None
        self.hands = []
        self.status = "idle"

    def apply(self, dt: float) -> None:
        if not self.active or self._p0 is None:
            return

        phase = _PHASES[self._phase]
        self._phase_t += dt
        self._t += dt
        u = _ease(self._phase_t / phase.duration)
        prev = _PHASES[self._phase - 1] if self._phase else _Phase("", 0, 0, 0, 0)
        left_a = prev.left + u * (phase.left - prev.left)
        right_a = prev.right + u * (phase.right - prev.right)
        hem_a = prev.hem + u * (phase.hem - prev.hem)
        gain = 1.0 - u if phase.fade else 1.0

        target = self._posed(left_a, right_a, hem_a)
        self._pull(target, gain)
        self._cap_velocity()
        self._update_hands(target)

        if self._phase_t >= phase.duration:
            self._phase += 1
            self._phase_t = 0.0
            if self._phase >= len(_PHASES):
                print("ninja fold: done", flush=True)
                self.stop()
                return
            self.status = _PHASES[self._phase].name
            print(f"ninja fold: {self.status}", flush=True)

    def _posed(self, left_a: float, right_a: float, hem_a: float) -> np.ndarray:
        assert self._p0 is not None
        p = self._p0.copy()
        m = self._masks
        z = self._hinge_z
        if left_a > 0:
            th = left_a * FOLD_ANGLE
            folded = _rotate_y(p, self._left_c, z, th)
            folded[m["left"], 2] += LIFT * np.sin(th)
            p[m["left"]] = folded[m["left"]]
        if right_a > 0:
            th = -right_a * FOLD_ANGLE
            folded = _rotate_y(p, self._right_c, z, th)
            folded[m["right"], 2] += LIFT * np.sin(abs(th))
            p[m["right"]] = folded[m["right"]]
        if hem_a > 0:
            th = hem_a * FOLD_ANGLE
            folded = _rotate_x(p, self._hem_c, z, th)
            folded[m["hem"], 2] += LIFT * np.sin(th)
            p[m["hem"]] = folded[m["hem"]]
        p[:, 2] = np.maximum(p[:, 2], z)
        return p

    def _pull(self, target: np.ndarray, gain: float) -> None:
        import mujoco

        if gain <= 1e-3:
            self._data.xfrc_applied[self._vert_body, :3] = 0.0
            return

        model, data = self._model, self._data
        omega = 2.0 * np.pi * FOLD_HZ
        pulled = self._pulled_mask()
        vel = np.empty(6)
        data.xfrc_applied[self._vert_body, :3] = 0.0
        for i in np.flatnonzero(pulled):
            body = int(self._vert_body[i])
            mass = float(model.body_mass[body])
            pos = np.asarray(data.xpos[body])
            mujoco.mj_objectVelocity(
                model, data, mujoco.mjtObj.mjOBJ_BODY, body, vel, 0
            )
            error = target[i] - pos
            force = mass * (omega**2) * error - 2.0 * mass * omega * vel[3:6]
            force *= gain
            limit = FOLD_LIMIT * mass * 9.81
            nrm = np.linalg.norm(force)
            if nrm > limit:
                force *= limit / nrm
            data.xfrc_applied[body, :3] = force

    def _pulled_mask(self) -> np.ndarray:
        """Moving panel plus a thin crease strip. Leave the rest alone."""
        phase = _PHASES[self._phase]
        m = self._masks
        pull = np.zeros(len(self._vert_body), dtype=bool)
        if phase.left > 0:
            pull |= m["left"] | m["anchor_l"]
        if phase.right > 0:
            pull |= m["right"] | m["anchor_r"]
        if phase.hem > 0:
            pull |= m["hem"] | m["anchor_h"]
        return pull

    def _cap_velocity(self) -> None:
        qvel = self._data.qvel
        peak = float(np.max(np.abs(qvel))) if qvel.size else 0.0
        if peak > VEL_CAP:
            qvel *= VEL_CAP / peak

    def _damp_velocities(self, scale: float) -> None:
        if self._data.qvel.size:
            self._data.qvel[:] *= scale

    def _update_hands(self, target: np.ndarray) -> None:
        lm = self._lm
        phase = _PHASES[self._phase]
        if phase.fade:
            self.hands = []
            return
        if phase.hem > 0 and phase.right >= 1.0:
            ids = (lm.hem_centre, lm.collar)
        elif phase.right > 0:
            ids = (lm.right_mid, lm.right_hem)
        else:
            ids = (lm.left_mid, lm.left_hem)
        self.hands = [target[i].copy() for i in ids]


def button_body_id(model) -> int:
    import mujoco

    return int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, BUTTON_BODY))
