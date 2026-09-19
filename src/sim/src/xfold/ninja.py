"""Ninja / Japanese fold landmarks on the shirt flex.

Crease geometry from SOLUTION.md §5.3, measured on the rest-frame T:

  left third  →  centre   (crease at x = −body/6)
  right third →  centre   (crease at x = +body/6)
  hem         →  collar   (packet ≈ 0.20 × 0.28 m)

Pinch interior vertices, not the raw edge — cloth dribbles off an edge grasp.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xfold.generate_shirt_mesh import BODY_L, BODY_W, LEFT_CREASE_X, RIGHT_CREASE_X
from xfold.shirt import shirt_vertex_positions

# Retail packet after the three creases (SOLUTION.md §1 / §8).
PACKET_W = 0.20
PACKET_L = 0.28


@dataclass(frozen=True)
class NinjaLandmarks:
    """Flex vertex indices for the dual-arm (or sequential) ninja fold."""

    left_mid: int
    left_hem: int
    left_shoulder: int
    right_mid: int
    right_hem: int
    right_shoulder: int
    hem_centre: int
    collar: int


def _nearest(rest: np.ndarray, target: np.ndarray) -> int:
    return int(np.argmin(np.sum((rest - target) ** 2, axis=1)))


def rest_xy(model) -> np.ndarray:
    """Shirt vertices in the flex rest pose, shape (nvert, 2)."""
    # flexvert_xpos0 is compiled from the OBJ; fall back to a reset pose.
    xpos0 = getattr(model, "flexvert_xpos0", None)
    if xpos0 is not None and np.size(xpos0) >= 3:
        return np.asarray(xpos0, dtype=np.float64).reshape(-1, 3)[:, :2]
    import mujoco

    from xfold.shirt import load_mujoco_plugins

    load_mujoco_plugins()
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    return shirt_vertex_positions(model, data)[:, :2]


def landmarks(model) -> NinjaLandmarks:
    """Pick the eight grasp / crease vertices on the rest T."""
    xy = rest_xy(model)
    y_hem = float(xy[:, 1].min()) + 0.04
    y_mid = 0.0
    y_shoulder = float(xy[:, 1].max()) - 0.06
    y_collar = float(xy[:, 1].max()) - 0.02
    return NinjaLandmarks(
        left_mid=_nearest(xy, np.array([LEFT_CREASE_X, y_mid])),
        left_hem=_nearest(xy, np.array([LEFT_CREASE_X, y_hem])),
        left_shoulder=_nearest(xy, np.array([LEFT_CREASE_X, y_shoulder])),
        right_mid=_nearest(xy, np.array([RIGHT_CREASE_X, y_mid])),
        right_hem=_nearest(xy, np.array([RIGHT_CREASE_X, y_hem])),
        right_shoulder=_nearest(xy, np.array([RIGHT_CREASE_X, y_shoulder])),
        hem_centre=_nearest(xy, np.array([0.0, y_hem])),
        collar=_nearest(xy, np.array([0.0, y_collar])),
    )


def fold_error(model, data) -> float:
    """|final AABB − 0.20 × 0.28 m| in metres (SOLUTION.md §8)."""
    pos = shirt_vertex_positions(model, data)
    span = pos.max(axis=0) - pos.min(axis=0)
    return float(np.hypot(span[0] - PACKET_W, span[1] - PACKET_L))


def shirt_thirds() -> tuple[float, float, float]:
    """(body width, third width, body length) in metres."""
    return BODY_W, BODY_W / 3.0, BODY_L
