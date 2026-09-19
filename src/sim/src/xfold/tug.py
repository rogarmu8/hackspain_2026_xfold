"""Pick which corner to pull, and where to pull it.

Once a shirt is lying on the bed, picking it up again to fix a two-centimetre
error is wasteful and it is not what a person does. A person presses a finger on
whichever corner is furthest from where it belongs and drags it there. Repeat,
and the garment walks itself square.

The maths is one rigid transform. The camera says the shirt is at
(``centre``, ``yaw``); it belongs at (``target``, 0). Both poses put every corner
somewhere definite, so for each corner there is a vector from where it is to
where it should be, and the longest of those vectors is the tug worth making.
One drag rarely lands it - the garment slides as well as swivels - so the caller
measures again and asks for the next one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Where on the garment the fingertips touch down: the torso corners, pulled in
# far enough that the tips land on the panel rather than half off its edge.
CORNER_INSET = 0.022

# The UR5e's 850 mm envelope, kept short of its singular limit. Corners further
# out than this are skipped in favour of a reachable one.
MAX_REACH = 0.78


@dataclass(frozen=True)
class Tug:
    """One corner drag: press down at ``start``, slide to ``finish``."""

    start: np.ndarray
    finish: np.ndarray
    corner: str

    @property
    def distance(self) -> float:
        return float(np.linalg.norm(self.finish - self.start))

    @property
    def heading(self) -> float:
        delta = self.finish - self.start
        return float(math.atan2(delta[1], delta[0]))

    def describe(self) -> str:
        delta = (self.finish - self.start) * 1000.0
        return (
            f"{self.corner} corner, {self.distance * 1000:.0f} mm "
            f"({delta[0]:+.0f} {delta[1]:+.0f})"
        )


def corner_offsets(torso_half: np.ndarray) -> tuple[tuple[str, np.ndarray], ...]:
    """The four touch-down points in the shirt's own frame, with names to log."""
    x = float(torso_half[0]) - CORNER_INSET
    y = float(torso_half[1]) - CORNER_INSET
    return (
        ("collar-left", np.array([x, y])),
        ("collar-right", np.array([x, -y])),
        ("hem-left", np.array([-x, y])),
        ("hem-right", np.array([-x, -y])),
    )


def _rotate(offset: np.ndarray, angle: float) -> np.ndarray:
    cos, sin = math.cos(angle), math.sin(angle)
    return np.array([cos * offset[0] - sin * offset[1], sin * offset[0] + cos * offset[1]])


def choose(
    torso_half: np.ndarray,
    centre: np.ndarray,
    yaw: float,
    target: np.ndarray,
    arm_base: np.ndarray,
    target_yaw: float = 0.0,
) -> Tug | None:
    """The most useful reachable corner drag, or None if none is worth making."""
    best: Tug | None = None
    for name, offset in corner_offsets(torso_half):
        start = np.asarray(centre, dtype=float) + _rotate(offset, yaw)
        finish = np.asarray(target, dtype=float) + _rotate(offset, target_yaw)
        if max(
            np.linalg.norm(start - arm_base), np.linalg.norm(finish - arm_base)
        ) > MAX_REACH:
            continue
        candidate = Tug(start=start, finish=finish, corner=name)
        if best is None or candidate.distance > best.distance:
            best = candidate
    return best
