"""Keyboard-driven cloth grab for the shirt playground.

MuJoCo's built-in mouse perturbation needs Ctrl + right-drag, which is
painful on a laptop trackpad (macOS also maps Ctrl+click to right-click,
so the two gestures fight each other). This drives a pinch patch of flex
vertices from the keyboard instead: the grabbed vertices are pulled toward
a target point by a critically damped spring, and the target glides at a
velocity you steer with single key taps.

The viewer only delivers key-down events — no repeats, no key-up — so
"hold a key to move" is not available; taps change velocity instead.
"""

from __future__ import annotations

import numpy as np

# GLFW key codes (the viewer passes these through untranslated).
KEY_SPACE = 32
KEY_E = 69
KEY_G = 71
KEY_Q = 81
KEY_R = 82
KEY_X = 88
KEY_RIGHT = 262
KEY_LEFT = 263
KEY_DOWN = 264
KEY_UP = 265

# Tuned on a lift-then-yank test: the pinch has to haul the whole 0.22 kg
# shirt, so a weak limit makes the grab lag ~20 cm behind the target.
GRAB_RADIUS = 0.05  # m — size of the pinch patch
SPEED_STEP = 0.06  # m/s added per tap
MAX_SPEED = 0.6  # m/s
SPRING_HZ = 20.0  # pinch stiffness, as a natural frequency
FORCE_LIMIT = 200.0  # x vertex weight, keeps a stuck pinch from exploding


class ClothGrab:
    """Pinch a patch of flex vertices and steer it with the keyboard."""

    def __init__(self, model, data):
        self._model = model
        self._data = data
        self._vert_body = np.asarray(model.flex_vertbodyid, dtype=np.int64)
        self._bodies: np.ndarray | None = None
        self._offsets: np.ndarray | None = None
        self._target = np.zeros(3)
        self._velocity = np.zeros(3)

    @property
    def active(self) -> bool:
        return self._bodies is not None

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
        near = np.flatnonzero(
            np.linalg.norm(pos - pos[center], axis=1) <= GRAB_RADIUS
        )
        self._bodies = self._vert_body[near]
        self._offsets = pos[near] - pos[center]
        self._target = pos[center].copy()
        self._velocity[:] = 0.0
        return f"grabbed {len(near)} verts at {np.round(self._target, 3)}"

    def release(self) -> None:
        if self._bodies is not None:
            self._data.xfrc_applied[self._bodies, :3] = 0.0
        self._bodies = None
        self._offsets = None
        self._velocity[:] = 0.0

    def nudge(self, direction: np.ndarray) -> None:
        self._velocity += SPEED_STEP * direction
        speed = np.linalg.norm(self._velocity)
        if speed > MAX_SPEED:
            self._velocity *= MAX_SPEED / speed

    def stop(self) -> None:
        self._velocity[:] = 0.0

    def apply(self, dt: float) -> None:
        """Advance the target and write pinch forces into xfrc_applied.

        Must run after viewer.sync(), which zeroes xfrc_applied.
        """
        if self._bodies is None or self._offsets is None:
            return
        import mujoco

        self._target += self._velocity * dt

        omega = 2.0 * np.pi * SPRING_HZ
        vel = np.empty(6)
        for body, offset in zip(self._bodies, self._offsets):
            mass = float(self._model.body_mass[body])
            pos = np.asarray(self._data.xpos[body])
            mujoco.mj_objectVelocity(
                self._model, self._data, mujoco.mjtObj.mjOBJ_BODY, int(body), vel, 0
            )
            error = (self._target + offset) - pos
            force = mass * (omega**2) * error - 2.0 * mass * omega * vel[3:6]
            limit = FORCE_LIMIT * mass * 9.81
            magnitude = np.linalg.norm(force)
            if magnitude > limit:
                force *= limit / magnitude
            self._data.xfrc_applied[body, :3] = force


def camera_axes(azimuth_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Horizontal (right, forward) unit vectors for the viewer camera."""
    azimuth = np.deg2rad(azimuth_deg)
    right = np.array([-np.sin(azimuth), np.cos(azimuth), 0.0])
    forward = np.array([-np.cos(azimuth), -np.sin(azimuth), 0.0])
    return right, forward
