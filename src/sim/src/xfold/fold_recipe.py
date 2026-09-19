"""Pick a fold recipe from the QC photo (OpenCV) plus the live silhouette.

Industrial folders do not run one FlipFold for every SKU:

* T-shirts: left sleeve, right sleeve, one hem cross-fold.
* Dresses / gowns longer than the deck: a drop-gate at the inlet halves them
  at the waist (pre-fold), then the same three flaps treat them as a T.
* Multi-pass: a second or third cross-fold if the pack is still too long.
* Trousers: one leg over the other (crease), then the cross-folds.

The QC camera fires before the folder. OpenCV segments the white cloth;
length, width and a crotch score choose the recipe. Cloth vertices are the
fallback when the shot is missing (headless, no GL) and a tie-break for
shape. Nothing here is written as pixels on the journal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Folder deck along +x (line.xml FOLDER_X). Longer than this needs a pre-fold.
FOLDER_MAX_LENGTH = 0.68
# Retail pack that fits the peel / bag.
PACK_MAX_LENGTH = 0.36
PACK_MAX_WIDTH = 0.36
# FlipFold side pins (line.xml flap_left / flap_right).
SIDE_HINGE_Y = 0.16
LAYER_GAP = 0.008

# qc_cam: 1.06 m above the belt, fovy 58, 512 px square used by Line._qc_rgb.
QC_HEIGHT_M = 1.06
QC_FOVY_DEG = 58.0
QC_SIZE_PX = 512

# White cotton in HSV (OpenCV). Same gate as vision.py; stains stay mostly
# bright so MORPH_CLOSE fills them.
_HSV_LOW = (0, 0, 140)
_HSV_HIGH = (179, 80, 255)


@dataclass(frozen=True)
class FoldRecipe:
    """What the folder should do to this garment."""

    kind: str  # flipfold | prefold_flipfold | pants
    prefold: bool
    side_mode: str  # both | crease | none
    cross_folds: int
    length_m: float
    width_m: float
    crotch: float
    reason: str
    source: str  # photo | vertices | fused

    def describe(self) -> str:
        sides = {
            "both": "mangas izquierda+derecha",
            "crease": "una pernera sobre la otra",
            "none": "sin palas laterales",
        }[self.side_mode]
        bits = []
        if self.prefold:
            bits.append("prepliegue a la cintura")
        bits.append(sides)
        bits.append(
            "1 pase transversal"
            if self.cross_folds == 1
            else f"{self.cross_folds} pases transversales"
        )
        return (
            f"{self.kind}  {self.length_m * 100:.0f}×{self.width_m * 100:.0f} cm  "
            f"→ {', '.join(bits)}  ({self.reason})"
        )


def qc_metres_per_px(size: int = QC_SIZE_PX) -> float:
    half = QC_HEIGHT_M * math.tan(math.radians(QC_FOVY_DEG) / 2.0)
    return (2.0 * half) / max(size, 1)


def choose_fold_recipe(
    *,
    rgb: np.ndarray | None = None,
    world_xy: np.ndarray | None = None,
    rest_xy: np.ndarray | None = None,
    metres_per_px: float | None = None,
) -> FoldRecipe:
    """Fuse the QC shot with the cloth outline and return a recipe.

    ``rest_xy`` is the rest mesh in the controller frame (collar +x, left +y),
    the same axes as a square lay on the belt. ``world_xy`` is live vertices.
    """
    photo = _features_from_image(rgb, metres_per_px) if rgb is not None else None
    verts = None
    if rest_xy is not None and len(rest_xy) >= 8:
        verts = _features_from_points(np.asarray(rest_xy, dtype=float)[:, :2])
    elif world_xy is not None and len(world_xy) >= 8:
        verts = _features_from_points(np.asarray(world_xy, dtype=float)[:, :2])

    if photo is None and verts is None:
        return FoldRecipe(
            "flipfold", False, "both", 1, 0.0, 0.0, 0.0,
            "no silhouette; default FlipFold", "none",
        )

    if photo is not None and verts is not None:
        length = max(photo["length"], verts["length"])
        width = max(photo["width"], verts["width"])
        crotch = max(photo["crotch"], verts["crotch"])
        source = "fused"
    elif photo is not None:
        length, width, crotch, source = photo["length"], photo["width"], photo["crotch"], "photo"
    else:
        length, width, crotch, source = verts["length"], verts["width"], verts["crotch"], "vertices"

    return _decide(length, width, crotch, source)


def apply_recipe(world: np.ndarray, recipe: FoldRecipe) -> np.ndarray:
    """Kinematic creases matching Line._fold_pack (no physics).

    Used to prove a recipe packs a catalogue panel before the live flaps run.
    """
    pos = np.asarray(world, dtype=float).copy()
    if pos.ndim != 2 or pos.shape[1] < 2:
        return pos
    if pos.shape[1] == 2:
        z = np.zeros((len(pos), 1))
        pos = np.hstack([pos, z])
    if recipe.prefold:
        pos = _fold_x(pos, 0.5 * (pos[:, 0].min() + pos[:, 0].max()))
    if recipe.side_mode == "both":
        cy = 0.5 * (pos[:, 1].min() + pos[:, 1].max())
        pos = _fold_y(pos, cy + SIDE_HINGE_Y, side=1.0)
        pos = _fold_y(pos, cy - SIDE_HINGE_Y, side=-1.0)
    elif recipe.side_mode == "crease":
        cy = 0.5 * (pos[:, 1].min() + pos[:, 1].max())
        pos = _fold_y(pos, cy, side=1.0)
    for _ in range(max(1, int(recipe.cross_folds))):
        pos = _fold_x(pos, 0.5 * (pos[:, 0].min() + pos[:, 0].max()))
    return pos


def pack_ok(world: np.ndarray, *, length: float = PACK_MAX_LENGTH, width: float = PACK_MAX_WIDTH) -> bool:
    pos = np.asarray(world, dtype=float)
    span = pos.max(axis=0) - pos.min(axis=0)
    return float(span[0]) <= length + 1e-6 and float(span[1]) <= width + 1e-6


def _decide(length: float, width: float, crotch: float, source: str) -> FoldRecipe:
    long = length > FOLDER_MAX_LENGTH
    # Two legs on the hem end beat an A-line / T, even when the panel is long.
    if crotch >= 0.50 and width > 0.28:
        half = 0.5 * length if long else length
        crosses = 1
        if half > PACK_MAX_LENGTH:
            crosses = 2
        if 0.5 * half > PACK_MAX_LENGTH:
            crosses = 3
        return FoldRecipe(
            "pants",
            prefold=long,
            side_mode="crease",
            cross_folds=crosses,
            length_m=length,
            width_m=width,
            crotch=crotch,
            reason="entrepierna: dos perneras",
            source=source,
        )
    if long:
        half = 0.5 * length
        crosses = 2 if half > FOLDER_MAX_LENGTH * 0.85 else 1
        if 0.5 * half > PACK_MAX_LENGTH:
            crosses = max(crosses, 2)
        return FoldRecipe(
            "prefold_flipfold",
            prefold=True,
            side_mode="both",
            cross_folds=crosses,
            length_m=length,
            width_m=width,
            crotch=crotch,
            reason=f"largo {length * 100:.0f} cm > cubierta {FOLDER_MAX_LENGTH * 100:.0f} cm",
            source=source,
        )
    return FoldRecipe(
        "flipfold",
        prefold=False,
        side_mode="both",
        cross_folds=1,
        length_m=length,
        width_m=width,
        crotch=crotch,
        reason="camiseta / panel corto",
        source=source,
    )


def _features_from_points(xy: np.ndarray) -> dict[str, float]:
    xs, ys = xy[:, 0], xy[:, 1]
    length = float(xs.max() - xs.min())
    width = float(ys.max() - ys.min())
    return {
        "length": length,
        "width": width,
        "crotch": _crotch_score(xy, length_axis=0),
    }


def _crotch_score(xy: np.ndarray, *, length_axis: int) -> float:
    """High when the hem third is two occupancy lobes with a valley on the midline."""
    if len(xy) < 16:
        return 0.0
    along = xy[:, length_axis]
    across = xy[:, 1 - length_axis]
    length = float(along.max() - along.min())
    width = float(across.max() - across.min())
    if length < 0.08 or width < 0.12:
        return 0.0
    lo, hi = float(along.min()), float(along.min() + 0.40 * length)
    band = across[(along >= lo) & (along <= hi)]
    if len(band) < 8:
        return 0.0
    hist, _ = np.histogram(band, bins=16, range=(float(across.min()), float(across.max())))
    hist = hist.astype(float)
    peak = float(hist.max())
    if peak <= 0:
        return 0.0
    left, mid, right = hist[:5].mean(), hist[5:11].mean(), hist[11:].mean()
    sides = 0.5 * (left + right)
    if sides <= 1e-9:
        return 0.0
    valley = (sides - mid) / (sides + 1e-9)
    both = 1.0 if (left > 0.22 * peak and right > 0.22 * peak) else 0.0
    return float(np.clip(0.55 * valley + 0.45 * both, 0.0, 1.0))


def _features_from_image(rgb: np.ndarray, metres_per_px: float | None) -> dict[str, float] | None:
    try:
        import cv2
    except ImportError:
        return None
    if rgb is None or rgb.size == 0:
        return None
    image = np.asarray(rgb)
    if image.ndim == 2:
        bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        bgr = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    elif image.shape[2] == 3:
        # Renderer is RGB.
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    else:
        return None
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _HSV_LOW, _HSV_HIGH)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) > 400]
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    (cx, cy), (w, h), angle = cv2.minAreaRect(largest)
    length_px = float(max(w, h))
    width_px = float(min(w, h))
    scale = float(metres_per_px if metres_per_px is not None else qc_metres_per_px(image.shape[0]))
    pts = largest.reshape(-1, 2).astype(np.float64)
    # qc_cam: +x (collar) is up in the frame, so image y *decreases* along length.
    # Map pixels to a length/width plane: x_along = -v, y_across = -u.
    along_across = np.column_stack((-pts[:, 1], -pts[:, 0])) * scale
    return {
        "length": length_px * scale,
        "width": width_px * scale,
        "crotch": _crotch_score(along_across, length_axis=0),
        "center": (cx, cy),
        "angle": angle,
    }


def _fold_x(pos: np.ndarray, hinge_x: float) -> np.ndarray:
    """Reflect the upstream (small x) half over a hinge parallel to y."""
    out = pos.copy()
    ids = out[:, 0] < hinge_x
    out[ids, 0] = 2.0 * hinge_x - out[ids, 0]
    out[ids, 2] += LAYER_GAP
    return out


def _fold_y(pos: np.ndarray, hinge_y: float, *, side: float) -> np.ndarray:
    """Reflect vertices on ``side`` of a hinge parallel to x. ``side`` is ±1.

    Extra length past the far pin is tucked onto the pack (long sleeves), not
    flipped through to the other aisle.
    """
    out = pos.copy()
    ids = side * (out[:, 1] - hinge_y) > 0.0
    out[ids, 1] = 2.0 * hinge_y - out[ids, 1]
    far = hinge_y - side * 2.0 * SIDE_HINGE_Y
    if side > 0:
        out[ids, 1] = np.maximum(out[ids, 1], far)
    else:
        out[ids, 1] = np.minimum(out[ids, 1], far)
    out[ids, 2] += LAYER_GAP
    return out
