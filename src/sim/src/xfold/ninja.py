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

# Pinch the panel being folded, not the hinge. A point on the crease cannot
# flip anything — it only tents. Mid-third x = crease ± one third.
LEFT_PANEL_X = LEFT_CREASE_X - BODY_W / 6.0
RIGHT_PANEL_X = RIGHT_CREASE_X + BODY_W / 6.0
from xfold.shirt import shirt_vertex_positions

# Retail packet after the three creases (SOLUTION.md §1 / §8).
PACKET_W = 0.20
PACKET_L = 0.28


@dataclass(frozen=True)
class NinjaLandmarks:
    """Flex vertex indices for the dual-arm (or sequential) ninja fold."""

    left_mid: int
    left_hem: int
    left_panel_mid: int
    left_panel_hem: int
    left_shoulder: int
    right_mid: int
    right_hem: int
    right_panel_mid: int
    right_panel_hem: int
    right_shoulder: int
    hem_centre: int
    collar: int


def _nearest(rest: np.ndarray, target: np.ndarray) -> int:
    return int(np.argmin(np.sum((rest - target) ** 2, axis=1)))


def rest_xyz(model) -> np.ndarray:
    """Shirt vertices in the flex rest pose, shape (nvert, 3)."""
    import mujoco

    from xfold.shirt import load_mujoco_plugins

    load_mujoco_plugins()
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    return shirt_vertex_positions(model, data)


def rest_xy(model) -> np.ndarray:
    """Shirt vertices in the flex rest pose, shape (nvert, 2)."""
    return rest_xyz(model)[:, :2]


def _sheet_mask(xyz: np.ndarray) -> np.ndarray:
    """Verts the two claws may pinch.

    A pressed T is one sheet (tiny z-span) — use every vertex. A hollow
    shell uses the low-z panel so we do not grab the back.
    """
    z0, z1 = float(xyz[:, 2].min()), float(xyz[:, 2].max())
    if (z1 - z0) < 0.04:
        return np.ones(len(xyz), dtype=bool)
    return xyz[:, 2] < 0.5 * (z0 + z1)


def _nearest_front(xyz: np.ndarray, target_xy: np.ndarray) -> int:
    """Nearest vertex on the foldable sheet / front panel."""
    pts = xyz[:, :2].copy()
    pts[~_sheet_mask(xyz)] = np.inf
    return _nearest(pts, target_xy)


def landmarks(model) -> NinjaLandmarks:
    """Pick the eight grasp / crease vertices on the rest T."""
    xyz = rest_xyz(model)
    front_y = xyz[_sheet_mask(xyz), 1]
    y_hem = float(front_y.min()) + 0.04
    y_mid = 0.0
    y_shoulder = float(front_y.max()) - 0.06
    y_collar = float(front_y.max()) - 0.02
    return NinjaLandmarks(
        left_mid=_nearest_front(xyz, np.array([LEFT_CREASE_X, y_mid])),
        left_hem=_nearest_front(xyz, np.array([LEFT_CREASE_X, y_hem])),
        left_panel_mid=_nearest_front(xyz, np.array([LEFT_PANEL_X, y_mid])),
        left_panel_hem=_nearest_front(xyz, np.array([LEFT_PANEL_X, y_hem])),
        left_shoulder=_nearest_front(xyz, np.array([LEFT_CREASE_X, y_shoulder])),
        right_mid=_nearest_front(xyz, np.array([RIGHT_CREASE_X, y_mid])),
        right_hem=_nearest_front(xyz, np.array([RIGHT_CREASE_X, y_hem])),
        right_panel_mid=_nearest_front(xyz, np.array([RIGHT_PANEL_X, y_mid])),
        right_panel_hem=_nearest_front(xyz, np.array([RIGHT_PANEL_X, y_hem])),
        right_shoulder=_nearest_front(xyz, np.array([RIGHT_CREASE_X, y_shoulder])),
        hem_centre=_nearest_front(xyz, np.array([0.0, y_hem])),
        collar=_nearest_front(xyz, np.array([0.0, y_collar])),
    )


def fold_error(model, data) -> float:
    """|final AABB − 0.20 × 0.28 m| in metres (SOLUTION.md §8)."""
    pos = shirt_vertex_positions(model, data)
    span = pos.max(axis=0) - pos.min(axis=0)
    return float(np.hypot(span[0] - PACKET_W, span[1] - PACKET_L))


def shirt_thirds() -> tuple[float, float, float]:
    """(body width, third width, body length) in metres."""
    return BODY_W, BODY_W / 3.0, BODY_L
