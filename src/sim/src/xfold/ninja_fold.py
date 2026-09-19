"""Japanese / ninja fold driven by two claws — not a whole-panel force.

Real two-hand method (SOLUTION.md §5.3):

  1. Pinch the *left panel* (mid + hem), flip it over the left crease.
  2. Pause.
  3. Mirror for the right panel.
  4. Pinch two hem points, flip them over the mid-line toward the collar.
  5. Ease off.

The claws ride an isometry of the panel (a 180° hinge). Dragging two
crease vertices with springs is what turned the T into a spike. The
moving half is kinematically rotated onto that hinge; mocap claws are
the visible pinch.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import mujoco

from xfold.claws import ShirtClaws, pin_bodies
from xfold.ninja import landmarks
from xfold.self_collide import THICKNESS

HOLD = 1.2
FLIP = 4.0
HEM = 3.6
RELEASE = 0.4
FOLD_ANGLE = np.pi
# Extra clearance at mid-flip so the panel does not scrape the sheet.
CLEAR = 0.03
# Vertical pitch between stacked thirds. Matches ClothLayers' 2×thickness
# gap so the second sleeve lands *on* the first instead of through it.
PITCH = 2.0 * THICKNESS
FOLD_ITERS = 80
# After the claws let go the packet still holds crease spring. Bleed
# that velocity so the shirt does not crawl around on its own.
COAST = 1.6
COAST_DAMP = 0.88
BUTTON_BODY = "ninja_button"


def _ease(u: float) -> float:
    u = float(np.clip(u, 0.0, 1.0))
    return u * u * (3.0 - 2.0 * u)


def _rotate_y(points: np.ndarray, hinge_x: float, hinge_z: float, theta: float) -> np.ndarray:
    out = points.copy()
    dx = points[:, 0] - hinge_x
    dz = points[:, 2] - hinge_z
    c, s = np.cos(theta), np.sin(theta)
    out[:, 0] = hinge_x + dx * c + dz * s
    out[:, 2] = hinge_z - dx * s + dz * c
    return out


def _rotate_x(points: np.ndarray, hinge_y: float, hinge_z: float, theta: float) -> np.ndarray:
    out = points.copy()
    dy = points[:, 1] - hinge_y
    dz = points[:, 2] - hinge_z
    c, s = np.cos(theta), np.sin(theta)
    out[:, 1] = hinge_y + dy * c + dz * s
    out[:, 2] = hinge_z - dy * s + dz * c
    return out


@dataclass(frozen=True)
class _Phase:
    name: str
    duration: float
    claws: tuple[str, str]
    hinge: str  # "left" | "right" | "hem"
    sign: float
    amount: float
    layers: int = 1
    fade: bool = False


# Two claws on the moving panel, hinge on the crease they flip over.
_PHASES = (
    _Phase("left third → centre", FLIP, ("left_panel_mid", "left_panel_hem"), "left", 1.0, 1.0, 1),
    _Phase("pause", HOLD, ("left_panel_mid", "left_panel_hem"), "left", 1.0, 1.0, 1),
    _Phase("right third → centre", FLIP, ("right_panel_mid", "right_panel_hem"), "right", -1.0, 1.0, 2),
    _Phase("pause", HOLD, ("right_panel_mid", "right_panel_hem"), "right", -1.0, 1.0, 2),
    _Phase("hem → collar", HEM, ("hem_centre", "hem_second"), "hem", 1.0, 1.0, 3),
    _Phase("settle", HOLD, ("hem_centre", "hem_second"), "hem", 1.0, 1.0, 3),
    _Phase("release", RELEASE, ("hem_centre", "hem_second"), "hem", 1.0, 1.0, 3, fade=True),
)


class NinjaFoldDemo:
    """Two-claw ninja fold. start() / stop() / apply(dt)."""

    def __init__(self, model, data, claws: ShirtClaws | None = None):
        self._model = model
        self._data = data
        self._vert_body = np.asarray(model.flex_vertbodyid, dtype=np.int64)
        self._claws = claws if claws is not None else ShirtClaws(model, data)
        self._lm = landmarks(model)
        self._ids = self._claw_ids()
        self._p0: np.ndarray | None = None
        self._p_phase: np.ndarray | None = None
        self._amount = 0.0
        self._z0 = 0.008
        self._hinges = {"left": 0.0, "right": 0.0, "hem": 0.0}
        self._rest_hinges = {"left": 0.0, "right": 0.0, "hem": 0.0}
        self._t = 0.0
        self._phase = -1
        self._phase_t = 0.0
        self._opt_iters = int(model.opt.iterations)
        self._coast = 0.0
        self.hands: list[np.ndarray] = []
        self.status = "idle"

    def _claw_ids(self) -> dict[str, int]:
        lm = self._lm
        from xfold.ninja import rest_xyz

        xy = rest_xyz(self._model)[:, :2]
        hem2 = int(np.argmin(np.sum((xy - (xy[lm.hem_centre] + np.array([0.05, 0.0]))) ** 2, axis=1)))
        return {
            "left_panel_mid": lm.left_panel_mid,
            "left_panel_hem": lm.left_panel_hem,
            "right_panel_mid": lm.right_panel_mid,
            "right_panel_hem": lm.right_panel_hem,
            "hem_centre": lm.hem_centre,
            "hem_second": hem2,
        }

    @property
    def active(self) -> bool:
        return self._phase >= 0

    def start(self) -> str:
        pos = np.asarray(self._data.flexvert_xpos, dtype=np.float64).reshape(-1, 3)
        self._p0 = pos.copy()
        self._p_phase = pos.copy()
        ids = self._ids
        self._rest_hinges = {
            "left": float(pos[self._lm.left_mid, 0]),
            "right": float(pos[self._lm.right_mid, 0]),
            "hem": 0.5
            * (
                float(pos[ids["hem_centre"], 1])
                + float(pos[self._lm.collar, 1])
            ),
        }
        self._hinges = dict(self._rest_hinges)
        self._z0 = float(np.median(pos[:, 2]))
        self._t = 0.0
        self._phase = 0
        self._phase_t = 0.0
        self._amount = 0.0
        self._opt_iters = int(self._model.opt.iterations)
        self._model.opt.iterations = max(self._opt_iters, FOLD_ITERS)
        self.status = _PHASES[0].name
        return f"ninja fold: {_PHASES[0].name}  claws={_PHASES[0].claws}"

    def stop(self) -> None:
        self._claws.release()
        if self._data.qvel.size:
            self._data.qvel[:] *= 0.0
        self._model.opt.iterations = self._opt_iters
        self._phase = -1
        self._p0 = None
        self._p_phase = None
        self._coast = COAST
        self.hands = []
        self.status = "idle"

    def apply(self, dt: float) -> None:
        if self._coast > 0.0 and not self.active:
            if self._data.qvel.size:
                self._data.qvel[:] *= COAST_DAMP
            self._coast = max(0.0, self._coast - dt)
            return
        if not self.active or self._p_phase is None:
            return

        phase = _PHASES[self._phase]
        self._phase_t += dt
        self._t += dt
        if self._phase_t <= dt + 1e-12:
            hinge_changed = (
                self._phase == 0
                or _PHASES[self._phase - 1].hinge != phase.hinge
            )
            if hinge_changed:
                pos = np.asarray(self._data.flexvert_xpos, dtype=np.float64).reshape(-1, 3)
                self._p_phase = pos.copy()
                self._hinges = dict(self._rest_hinges)
                self._z0 = float(np.median(pos[:, 2]))
                self._amount = 0.0
        u = _ease(self._phase_t / phase.duration)
        prev_amt = _PHASES[self._phase - 1].amount if self._phase else 0.0
        if self._phase and _PHASES[self._phase - 1].hinge == phase.hinge:
            amount = prev_amt + u * (phase.amount - prev_amt)
        else:
            amount = u * phase.amount if phase.amount and not phase.fade else phase.amount

        claw_idx = [self._ids[name] for name in phase.claws]
        targets = self._claw_targets(claw_idx, phase.hinge, phase.sign, amount, phase.layers)
        d_amount = (amount - self._amount) / dt if dt > 1e-9 else 0.0
        self._amount = amount
        if phase.fade:
            self._claws.release()
            self.hands = []
            self._drive_panel(phase.hinge, phase.sign, 1.0, 0.0, phase.layers)
        else:
            self._drive_panel(phase.hinge, phase.sign, amount, d_amount, phase.layers)
            self._hold_stationary(phase.hinge)
            mujoco.mj_forward(self._model, self._data)
            bodies = [int(self._vert_body[i]) for i in claw_idx]
            self._claws.attach_pair(bodies, targets)
            self.hands = [t.copy() for t in targets]

        if self._phase_t >= phase.duration:
            self._phase += 1
            self._phase_t = 0.0
            if self._phase >= len(_PHASES):
                print("ninja fold: done", flush=True)
                self.stop()
                return
            nxt = _PHASES[self._phase]
            self.status = nxt.name
            span = np.asarray(self._data.flexvert_xpos).reshape(-1, 3)
            span = span.max(axis=0) - span.min(axis=0)
            print(
                f"ninja fold: {nxt.name}  claws={nxt.claws}  "
                f"span={span[0]:.2f}x{span[1]:.2f}",
                flush=True,
            )

    def _lift(self, folded: np.ndarray, amount: float, layers: int, th: float) -> np.ndarray:
        """Arc over the packet. Add a stack offset — do not clamp, so a
        double layer (first sleeve sitting on the second) stays a stack
        when it flips."""
        arc = CLEAR + 0.6 * PITCH * max(int(layers) - 1, 0)
        folded = folded.copy()
        folded[:, 2] += arc * np.sin(abs(th))
        folded[:, 2] += PITCH * float(layers) * amount
        folded[:, 2] = np.maximum(folded[:, 2], self._z0)
        return folded

    def _moving_mask(self, hinge: str) -> np.ndarray:
        """Verts currently on the moving side of the crease.

        After the left fold the first sleeve lies on the right third.
        Masking in the *current* pose (not rest) picks that overlay up
        with the second sleeve instead of driving through it.
        """
        assert self._p_phase is not None
        p = self._p_phase
        if hinge == "hem":
            return p[:, 1] < self._hinges["hem"] - 0.008
        if hinge == "left":
            return p[:, 0] < self._hinges["left"] - 0.008
        return p[:, 0] > self._hinges["right"] + 0.008

    def _claw_targets(
        self, claw_idx: list[int], hinge: str, sign: float, amount: float, layers: int
    ) -> list[np.ndarray]:
        assert self._p_phase is not None
        pts = self._p_phase[np.asarray(claw_idx)].copy()
        z = self._z0
        th = amount * sign * FOLD_ANGLE
        if hinge == "hem":
            folded = _rotate_x(pts, self._hinges["hem"], z, abs(th))
        else:
            folded = _rotate_y(pts, self._hinges[hinge], z, th)
        folded = self._lift(folded, amount, layers, th)
        return [folded[i] for i in range(len(claw_idx))]

    def _drive_panel(
        self, hinge: str, sign: float, amount: float, d_amount: float, layers: int
    ) -> None:
        """Snap the moving half of the sheet onto the hinge isometry."""
        assert self._p_phase is not None
        p = self._p_phase
        z = self._z0
        th = amount * sign * FOLD_ANGLE
        omega = d_amount * sign * FOLD_ANGLE
        if hinge == "hem":
            folded = _rotate_x(p, self._hinges["hem"], z, abs(th))
            omega_abs = abs(omega)
        elif hinge == "left":
            folded = _rotate_y(p, self._hinges["left"], z, th)
            omega_abs = omega
        else:
            folded = _rotate_y(p, self._hinges["right"], z, th)
            omega_abs = omega
        folded = self._lift(folded, amount, layers, th)
        ids = np.flatnonzero(self._moving_mask(hinge))
        if ids.size == 0:
            return
        dest = folded[ids]
        if hinge == "hem":
            rx = dest[:, 1] - self._hinges["hem"]
            rz = dest[:, 2] - z
            vel = np.zeros_like(dest)
            vel[:, 1] = omega_abs * rz
            vel[:, 2] = -omega_abs * rx
        else:
            rx = dest[:, 0] - self._hinges[hinge]
            rz = dest[:, 2] - z
            vel = np.zeros_like(dest)
            vel[:, 0] = omega_abs * rz
            vel[:, 2] = -omega_abs * rx
        pin_bodies(self._model, self._data, self._vert_body[ids], dest, vel)

    def _hold_stationary(self, hinge: str) -> None:
        """Pin everything not flipping so the packet cannot fall through."""
        assert self._p_phase is not None
        ids = np.flatnonzero(~self._moving_mask(hinge))
        if ids.size == 0:
            return
        dest = self._p_phase[ids]
        pin_bodies(self._model, self._data, self._vert_body[ids], dest, np.zeros_like(dest))


def button_body_id(model) -> int:
    import mujoco

    return int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, BUTTON_BODY))
