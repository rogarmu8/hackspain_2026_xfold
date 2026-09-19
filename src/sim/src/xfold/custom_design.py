"""Operator photo → custom flexcomp (silhouette + print).

Detect the clothing blob, bake it onto a square PNG (both faces), and cut
the panel mesh to that outline. Pixels stay off the journal.
"""

from __future__ import annotations

import base64
import binascii
import io
from pathlib import Path

import numpy as np

from xfold.generate_shirt_mesh import (
    BODY_W,
    CUSTOM_OUTLINE_PATH,
    MODELS,
    ensure_custom_mesh,
)
from xfold.shirt_shot import write_png

CUSTOM_TEXTURE = "_custom_garment.png"
CUSTOM_TEXTURE_PATH = MODELS / CUSTOM_TEXTURE
TEX_SIZE = 1024
DETECT_SIZE = 256
MAX_BYTES = 4 * 1024 * 1024
CLOTH = (246, 246, 248)
ALLOWED_MIME = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}


def decode_payload(data: str, mime: str = "image/png") -> bytes:
    """Base64 body of ``customDesign.data``. Rejects huge or empty payloads."""
    kind = (mime or "image/png").split(";")[0].strip().lower()
    if kind not in ALLOWED_MIME:
        raise ValueError(f"unsupported format ({mime}); use PNG, JPEG, or WebP")
    raw = (data or "").strip()
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")
    try:
        blob = base64.b64decode(raw, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("the image is not valid base64") from exc
    if not blob:
        raise ValueError("the image is empty")
    if len(blob) > MAX_BYTES:
        raise ValueError("the image exceeds 4 MB")
    return blob


def _load_rgb(blob: bytes):
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
    except Exception as exc:  # noqa: BLE001 — operator upload, not a bug
        raise ValueError("could not read the image") from exc
    return img.convert("RGB")


def _border_bg(rgb: np.ndarray) -> np.ndarray:
    border = np.concatenate(
        [rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]],
        axis=0,
    )
    return np.median(border, axis=0)


def _color_dist(rgb: np.ndarray, bg: np.ndarray) -> np.ndarray:
    return np.max(np.abs(rgb.astype(np.int16) - bg.astype(np.int16)), axis=2)


def _auto_thresh(dist: np.ndarray) -> float:
    h, w = dist.shape
    ring = np.concatenate([dist[0], dist[-1], dist[:, 0], dist[:, -1]])
    return float(max(22.0, np.percentile(ring, 88) + 10.0))


def _flood_background(is_bg: np.ndarray) -> np.ndarray:
    """True where a border-connected background flood can reach."""
    h, w = is_bg.shape
    flooded = np.zeros((h, w), dtype=bool)
    stack: list[tuple[int, int]] = []
    for x in range(w):
        if is_bg[0, x]:
            stack.append((0, x))
        if is_bg[h - 1, x]:
            stack.append((h - 1, x))
    for y in range(h):
        if is_bg[y, 0]:
            stack.append((y, 0))
        if is_bg[y, w - 1]:
            stack.append((y, w - 1))
    while stack:
        y, x = stack.pop()
        if y < 0 or x < 0 or y >= h or x >= w or flooded[y, x] or not is_bg[y, x]:
            continue
        flooded[y, x] = True
        stack.extend(((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)))
    return flooded


def _largest_component(fg: np.ndarray) -> np.ndarray:
    h, w = fg.shape
    seen = np.zeros((h, w), dtype=bool)
    best: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            if not fg[y, x] or seen[y, x]:
                continue
            blob: list[tuple[int, int]] = []
            stack = [(y, x)]
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                blob.append((cy, cx))
                for ny, nx in (
                    (cy - 1, cx),
                    (cy + 1, cx),
                    (cy, cx - 1),
                    (cy, cx + 1),
                ):
                    if (
                        0 <= ny < h
                        and 0 <= nx < w
                        and fg[ny, nx]
                        and not seen[ny, nx]
                    ):
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(blob) > len(best):
                best = blob
    out = np.zeros((h, w), dtype=bool)
    for y, x in best:
        out[y, x] = True
    return out


def detect_garment_mask(rgb: np.ndarray) -> np.ndarray:
    """Boolean mask (H, W) of the main garment vs a flood-filled backdrop."""
    dist = _color_dist(rgb, _border_bg(rgb))
    thresh = _auto_thresh(dist)
    is_bg = dist <= thresh
    flooded = _flood_background(is_bg)
    fg = ~flooded
    frac = float(fg.mean()) if fg.size else 0.0
    if frac < 0.02:
        raise ValueError(
            "no garment visible; try a smoother backdrop and centre the clothing"
        )
    if frac > 0.94:
        return np.ones(fg.shape, dtype=bool)
    return _largest_component(fg)


def mask_contour_uv(mask: np.ndarray, limit: int = 80) -> list[list[float]]:
    """Coarse outline in unit-square UV (origin top-left, like a PNG)."""
    uv = _scanline_contour_uv(np.asarray(mask, dtype=bool))
    if uv is None or len(uv) < 3:
        return []
    if len(uv) > limit:
        stride = max(1, len(uv) // limit)
        uv = uv[::stride]
        if not np.allclose(uv[0], uv[-1]):
            uv = np.vstack((uv, uv[0]))
    return uv.tolist()


def _morph_close(mask: np.ndarray, n: int = 2) -> np.ndarray:
    out = mask.astype(bool)
    for _ in range(n):
        p = np.pad(out, 1, constant_values=False)
        out = (
            out
            | p[:-2, 1:-1]
            | p[2:, 1:-1]
            | p[1:-1, :-2]
            | p[1:-1, 2:]
            | p[:-2, :-2]
            | p[:-2, 2:]
            | p[2:, :-2]
            | p[2:, 2:]
        )
    for _ in range(n):
        p = np.pad(out, 1, constant_values=True)
        out = (
            out
            & p[:-2, 1:-1]
            & p[2:, 1:-1]
            & p[1:-1, :-2]
            & p[1:-1, 2:]
        )
    return out


def _scanline_contour_uv(mask: np.ndarray) -> np.ndarray | None:
    h, w = mask.shape
    if h < 3 or w < 3 or float(mask.mean()) < 0.015:
        return None
    step = max(1, h // 64)
    lefts: list[tuple[float, float]] = []
    rights: list[tuple[float, float]] = []
    denom_x = max(w - 1, 1)
    denom_y = max(h - 1, 1)
    for y in range(0, h, step):
        row = np.nonzero(mask[y])[0]
        if row.size == 0:
            continue
        v = float(y) / denom_y
        lefts.append((float(row[0]) / denom_x, v))
        rights.append((float(row[-1]) / denom_x, v))
    if len(lefts) < 3:
        return None
    pts = np.asarray(lefts + rights[::-1], dtype=np.float64)
    if not np.allclose(pts[0], pts[-1]):
        pts = np.vstack((pts, pts[0]))
    return pts


def _rdp(pts: np.ndarray, eps: float) -> np.ndarray:
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    span = float(np.hypot(ab[0], ab[1])) + 1e-18
    cross = (pts[:, 0] - a[0]) * ab[1] - (pts[:, 1] - a[1]) * ab[0]
    dist = np.abs(cross) / span
    i = int(np.argmax(dist))
    if dist[i] <= eps:
        return np.vstack((a, b))
    left = _rdp(pts[: i + 1], eps)
    right = _rdp(pts[i:], eps)
    return np.vstack((left[:-1], right))


def outline_metres_from_mask(mask: np.ndarray, side: float = BODY_W) -> np.ndarray | None:
    """PNG-space blob → closed sewing loop in metres (collar at +Y)."""
    m = np.asarray(mask)
    if m.ndim == 3:
        m = m.any(axis=2)
    m = m.astype(bool)
    if m.size == 0 or float(m.mean()) < 0.015:
        return None
    from PIL import Image

    work = Image.fromarray((m.astype(np.uint8) * 255), mode="L")
    work = work.resize((128, 128), Image.Resampling.NEAREST)
    closed = _morph_close(np.asarray(work) > 127, 2)
    uv = _scanline_contour_uv(closed)
    if uv is None or len(uv) < 6:
        return None
    ring = uv[:-1] if np.allclose(uv[0], uv[-1]) else uv
    uv = _rdp(ring, 0.008)
    if len(uv) < 4:
        return None
    if not np.allclose(uv[0], uv[-1]):
        uv = np.vstack((uv, uv[0]))
    x = (uv[:, 0] - 0.5) * side
    y = (0.5 - uv[:, 1]) * side
    return np.column_stack((x, y))


def _contain_square(img, size: int, fill: tuple[int, int, int]):
    from PIL import Image

    canvas = Image.new("RGB", (size, size), fill)
    scale = min(size / max(img.width, 1), size / max(img.height, 1))
    nw = max(1, int(round(img.width * scale)))
    nh = max(1, int(round(img.height * scale)))
    fitted = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas.paste(fitted, ((size - nw) // 2, (size - nh) // 2))
    return canvas


def _cutout_square(photo, mask_img, size: int):
    """Tight-crop the garment into a square on cloth-white, plus that mask."""
    from PIL import Image

    box = mask_img.getbbox()
    if not box:
        return _contain_square(photo, size, CLOTH), None
    pad = 4
    l, t, r, b = box
    l = max(0, l - pad)
    t = max(0, t - pad)
    r = min(photo.width, r + pad)
    b = min(photo.height, b + pad)
    crop = photo.crop((l, t, r, b))
    crop_mask = mask_img.crop((l, t, r, b))
    square = _contain_square(crop, size, CLOTH)
    mask_sq = _contain_square(crop_mask.convert("RGB"), size, (0, 0, 0)).convert("L")
    cloth = Image.new("RGB", (size, size), CLOTH)
    cloth.paste(square, mask=mask_sq)
    return cloth, mask_sq


def bake_custom_design(
    blob: bytes,
    *,
    style: str = "custom",
    size: int = TEX_SIZE,
    dest: Path | None = None,
    **_ignored,
) -> Path:
    """Write the two-sided PNG and cut ``garment_custom.obj`` to the outline.

    ``style`` is ignored (kept so older callers do not crash). Extra kwargs
    from the old overlay fit are ignored on purpose.
    """
    from PIL import Image

    del style
    photo = _load_rgb(blob)
    work_w = DETECT_SIZE
    work_h = max(32, int(round(DETECT_SIZE * photo.height / max(photo.width, 1))))
    work = photo.resize((work_w, work_h), Image.Resampling.BILINEAR)
    mask_sq = None
    try:
        small_mask = detect_garment_mask(np.asarray(work, dtype=np.uint8))
    except ValueError:
        cloth = _contain_square(photo, size, CLOTH)
    else:
        mask_img = Image.fromarray((small_mask.astype(np.uint8) * 255), mode="L")
        mask_img = mask_img.resize(photo.size, Image.Resampling.NEAREST)
        cloth, mask_sq = _cutout_square(photo, mask_img, size)
    rgb = np.asarray(cloth, dtype=np.uint8)
    out = dest or CUSTOM_TEXTURE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        cloth.save(out, format="PNG", optimize=True)
    except Exception:
        write_png(out, rgb)
    poly = None
    if mask_sq is not None:
        poly = outline_metres_from_mask(np.asarray(mask_sq) > 32)
    if poly is not None:
        np.save(CUSTOM_OUTLINE_PATH, poly)
    elif CUSTOM_OUTLINE_PATH.is_file():
        CUSTOM_OUTLINE_PATH.unlink()
    ensure_custom_mesh()
    return out
