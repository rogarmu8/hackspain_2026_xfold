"""Fold quality from a top-down RGB frame of the packed garment.

The live engine is Isaac: OpenCV scores the opener-mounted `fold_qc_cam`
frame. The percent is **100 minus wrinkle coverage minus the share of pack
that sits off the light folder deck**. A pack that is smooth and fully on
the plates is high 90s. Missing pack → None.

A NumPy path exists only so a machine without cv2 (laptop tests) still
returns a number. Install OpenCV on the GPU box with
``src/isaac/scripts/ensure-opencv.sh``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Local gray std (11 px window) that counts as wrinkled. Generous: lighting
# and fabric weave sit below this; only real creases light up.
WRINKLE_STD = 14.0
WRINKLE_WIN = 11
# Folder deck (plates / closed flaps) is the bright table. Below this gray
# is floor, steel, belt — not the white surface.
PLATE_GRAY = 130.0


@dataclass(frozen=True)
class FoldInspect:
    """Score plus the RGB frame the operator sees (wrinkle overlay + outline)."""

    score: float | None
    annotated: np.ndarray | None


def score_fold(rgb: np.ndarray) -> float | None:
    """Return fold quality in ``[0, 100]``, or None if no pack is in view."""
    return inspect_fold(rgb).score


def inspect_fold(rgb: np.ndarray) -> FoldInspect:
    """Score the pack and return an OpenCV-annotated RGB frame."""
    if rgb is None or np.asarray(rgb).size == 0:
        return FoldInspect(None, None)
    image = np.asarray(rgb)
    try:
        import cv2
    except ImportError:
        score, _, _ = _score_numpy(image)
        if score is None:
            return FoldInspect(None, None)
        return FoldInspect(score, _as_rgb(image))
    return _inspect_cv2(image, cv2)


def _inspect_cv2(image: np.ndarray, cv2) -> FoldInspect:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    pack = _pack_mask_cv2(gray, cv2)
    if pack is None:
        return FoldInspect(None, None)
    plate = _plate_mask(gray)
    wrinkle = _wrinkle_mask_cv2(gray, pack, cv2)
    overflow = pack & ~plate
    score = _coverage_score(wrinkle | overflow, pack)
    if score is None:
        return FoldInspect(None, None)
    return FoldInspect(
        score, _annotate_cv2(_as_rgb(image), pack, wrinkle, overflow, score, cv2)
    )


def _wrinkle_mask_cv2(gray: np.ndarray, pack: np.ndarray, cv2) -> np.ndarray:
    """Pixels on the pack whose local contrast looks like a crease."""
    gray_f = gray.astype(np.float32)
    k = (WRINKLE_WIN, WRINKLE_WIN)
    mean = cv2.blur(gray_f, k)
    mean2 = cv2.blur(gray_f * gray_f, k)
    std = cv2.sqrt(cv2.max(mean2 - mean * mean, 0.0))
    raw = pack & (std > WRINKLE_STD)
    opened = cv2.morphologyEx(
        raw.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)
    )
    return opened.astype(bool)


def _plate_mask(gray: np.ndarray) -> np.ndarray:
    """Light folder deck as the dense bright plateau, ignoring hanging sleeves.

    Bright pixels are the plates, closed flaps, and pale cloth. The table is
    the longest run where the x and y histograms stay near their peak; a
    shorter sleeve off the side does not raise that peak enough to join.
    A small margin keeps a seated pack from being nickeled on the rim. If
    the frame has no clear table, skip the overflow penalty.
    """
    bright = np.asarray(gray) >= PLATE_GRAY
    height, width = bright.shape[:2]
    if float(bright.mean()) < 0.04:
        return np.ones((height, width), dtype=bool)
    ys, xs = np.nonzero(bright)
    if xs.size < 32:
        return np.ones((height, width), dtype=bool)
    x0, x1 = _dense_span(xs, width)
    y0, y1 = _dense_span(ys, height)
    if (x1 - x0) < 16 or (y1 - y0) < 16:
        return np.ones((height, width), dtype=bool)
    margin = 6
    plate = np.zeros((height, width), dtype=bool)
    plate[
        max(0, y0 - margin) : min(height, y1 + 1 + margin),
        max(0, x0 - margin) : min(width, x1 + 1 + margin),
    ] = True
    return plate


def _dense_span(coords: np.ndarray, length: int, frac: float = 0.85) -> tuple[int, int]:
    """First and last index of the histogram plateau (near-peak occupancy)."""
    hist = np.bincount(coords.astype(np.int32), minlength=length).astype(np.float64)
    if hist.max() < 1:
        return 0, max(0, length - 1)
    if length >= 5:
        hist = np.convolve(hist, np.ones(5) / 5.0, mode="same")
    on = hist >= frac * hist.max()
    padded = np.concatenate([[False], on, [False]])
    d = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    if starts.size == 0:
        return 0, max(0, length - 1)
    lengths = ends - starts
    i = int(np.argmax(lengths))
    return int(starts[i]), int(ends[i] - 1)


def _coverage_score(bad: np.ndarray, pack: np.ndarray) -> float | None:
    area = float(np.count_nonzero(pack))
    if area < 1:
        return None
    covered = float(np.count_nonzero(bad & pack)) / area
    return float(max(0.0, min(100.0, 100.0 * (1.0 - covered))))


def _annotate_cv2(
    rgb: np.ndarray,
    pack: np.ndarray,
    wrinkle: np.ndarray,
    overflow: np.ndarray,
    score: float,
    cv2,
) -> np.ndarray:
    """Wrinkles in red, off-plate cloth in cyan, contour, and the percent."""
    canvas = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2BGR)
    overlay = canvas.copy()
    wrinkle_tint = np.zeros_like(canvas)
    wrinkle_tint[wrinkle] = (40, 40, 220)
    overflow_tint = np.zeros_like(canvas)
    overflow_tint[overflow] = (200, 160, 20)
    overlay[pack] = cv2.addWeighted(canvas, 0.78, wrinkle_tint, 0.22, 0)[pack]
    overlay[wrinkle] = cv2.addWeighted(canvas, 0.35, wrinkle_tint, 0.65, 0)[wrinkle]
    overlay[overflow] = cv2.addWeighted(canvas, 0.40, overflow_tint, 0.60, 0)[overflow]
    contours, _ = cv2.findContours(
        pack.astype(np.uint8) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(overlay, contours, -1, (0, 220, 255), 2)
    wrinkle_pct = 100.0 * float(np.count_nonzero(wrinkle & pack)) / max(1, int(pack.sum()))
    off_pct = 100.0 * float(np.count_nonzero(overflow)) / max(1, int(pack.sum()))
    banner = f"FOLD QUALITY  {score:.0f}%"
    hint = f"{wrinkle_pct:.0f}% wrinkled, {off_pct:.0f}% off the plates"
    (tw, th), _ = cv2.getTextSize(banner, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(overlay, (8, 8), (20 + max(tw, 280), 28 + th + 18), (12, 12, 12), -1)
    tone = (40, 200, 80) if score >= 80 else (0, 180, 220) if score >= 50 else (40, 40, 220)
    cv2.putText(overlay, banner, (14, 28 + th - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.7, tone, 2, cv2.LINE_AA)
    cv2.putText(overlay, hint, (14, 28 + th + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)
    return cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)


def _as_rgb(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return np.stack([image, image, image], axis=-1)
    return image


def _pack_mask_cv2(gray: np.ndarray, cv2) -> np.ndarray | None:
    height, width = gray.shape[:2]
    y0, y1 = int(0.12 * height), int(0.88 * height)
    x0, x1 = int(0.12 * width), int(0.88 * width)
    roi = np.zeros_like(gray)
    roi[y0:y1, x0:x1] = 255
    mask = cv2.bitwise_and(cv2.inRange(gray, 28, 245), roi)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n_labels <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    best = 1 + int(np.argmax(areas))
    if stats[best, cv2.CC_STAT_AREA] < 0.04 * gray.size:
        return None
    pack = cv2.erode((labels == best).astype(np.uint8), np.ones((9, 9), np.uint8))
    if int(pack.sum()) < 0.02 * gray.size:
        return None
    return pack.astype(bool)


def _score_numpy(image: np.ndarray) -> tuple[float | None, np.ndarray | None, np.ndarray | None]:
    if image.ndim == 3:
        gray = (
            0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]
        ).astype(np.float32)
    else:
        gray = image.astype(np.float32)
    height, width = gray.shape
    if height < 16 or width < 16:
        return None, None, None
    y0, y1 = int(0.12 * height), int(0.88 * height)
    x0, x1 = int(0.12 * width), int(0.88 * width)
    pack_full = np.zeros_like(gray, dtype=bool)
    roi = gray[y0:y1, x0:x1]
    pack_roi = (roi >= 28.0) & (roi <= 245.0)
    if pack_roi.mean() < 0.04:
        return None, None, None
    pack_full[y0:y1, x0:x1] = pack_roi
    # Drop the silhouette so a dark floor around a seated pack is not a crease.
    pack = _box_blur(pack_full.astype(np.float32), 5) > 0.9
    if float(pack.mean()) < 0.02:
        return None, None, None
    radius = WRINKLE_WIN // 2
    mean = _box_blur(gray, radius)
    mean2 = _box_blur(gray * gray, radius)
    std = np.sqrt(np.maximum(mean2 - mean * mean, 0.0))
    wrinkle = pack & (std > WRINKLE_STD)
    plate = _plate_mask(gray)
    overflow = pack & ~plate
    score = _coverage_score(wrinkle | overflow, pack)
    return score, wrinkle, pack


def _box_blur(image: np.ndarray, radius: int) -> np.ndarray:
    """Separable box filter; radius 0 is a no-op. Output matches input shape."""
    if radius <= 0:
        return image
    pad = np.pad(image, ((radius + 1, radius), (radius + 1, radius)), mode="edge")
    cum = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    width = 2 * radius + 1
    window = (
        cum[width:, width:]
        - cum[width:, :-width]
        - cum[:-width, width:]
        + cum[:-width, :-width]
    )
    return window / float(width * width)
