"""Keyboard-driven cloth grab for the shirt playground.

MuJoCo's built-in mouse perturbation needs Ctrl + right-drag, which is
painful on a laptop trackpad (macOS also maps Ctrl+click to right-click,
so the two gestures fight each other). This welds one flex vertex to a
mocap claw; the claw glides at a velocity you steer with single key taps.

The viewer only delivers key-down events — no repeats, no key-up — so
"hold a key to move" is not available; taps change velocity instead.
"""

from __future__ import annotations

import numpy as np

from xfold.claws import ShirtClaws

# GLFW key codes (the viewer passes these through untranslated).
KEY_SPACE = 32
KEY_E = 69
KEY_G = 71
KEY_N = 78
KEY_Q = 81
KEY_R = 82
KEY_X = 88
KEY_RIGHT = 262
KEY_LEFT = 263
KEY_DOWN = 264
KEY_UP = 265

SPEED_STEP = 0.06  # m/s added per tap
MAX_SPEED = 0.6  # m/s


class ClothGrab:
    """Pinch one flex vertex and steer that claw with the keyboard."""

    def __init__(self, model, data, claws: ShirtClaws | None = None):
        self._model = model
        self._data = data
        self._vert_body = np.asarray(model.flex_vertbodyid, dtype=np.int64)
        self._claws = claws if claws is not None else ShirtClaws(model, data)
        self._body: int | None = None
        self._target = np.zeros(3)
        self._velocity = np.zeros(3)

    @property
    def claws(self) -> ShirtClaws:
        return self._claws

    @property
    def active(self) -> bool:
        return self._body is not None

    @property
    def target(self) -> np.ndarray:
        return self._target

    @property
    def speed(self) -> float:
        return float(np.linalg.norm(self._velocity))

    def _vertex_positions(self) -> np.ndarray:
        return np.asarray(self._data.flexvert_xpos).reshape(-1, 3)

    def _pick_center(self, selected_body: int) -> int:
        """Vertex index to pinch: the double-clicked one, else the highest."""
        if selected_body > 0:
            match = np.flatnonzero(self._vert_body == selected_body)
            if match.size:
                return int(match[0])
        return int(np.argmax(self._vertex_positions()[:, 2]))

    def toggle(self, selected_body: int = 0) -> str:
        if self.active:
            self.release()
            return "released"
        pos = self._vertex_positions()
        center = self._pick_center(selected_body)
        self._body = int(self._vert_body[center])
        self._target = pos[center].copy()
        self._velocity[:] = 0.0
        self._claws.attach(0, self._body, self._target)
        return f"grabbed 1 claw at {np.round(self._target, 3)}"

    def release(self) -> None:
        self._claws.release(0)
        self._body = None
        self._velocity[:] = 0.0

    def nudge(self, direction: np.ndarray) -> None:
        self._velocity += SPEED_STEP * direction
        speed = np.linalg.norm(self._velocity)
        if speed > MAX_SPEED:
            self._velocity *= MAX_SPEED / speed

    def stop(self) -> None:
        self._velocity[:] = 0.0

    def apply(self, dt: float) -> None:
        """Advance the mocap claw; connect keeps the vertex on it."""
        if self._body is None:
            return
        self._target += self._velocity * dt
        self._claws.move(0, self._target, self._velocity)


def camera_axes(azimuth_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Horizontal (right, forward) unit vectors for the viewer camera."""
    azimuth = np.deg2rad(azimuth_deg)
    right = np.array([-np.sin(azimuth), np.cos(azimuth), 0.0])
    forward = np.array([-np.cos(azimuth), -np.sin(azimuth), 0.0])
    return right, forward
