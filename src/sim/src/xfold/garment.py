"""Flat-garment catalog + projection onto the XFOLD T flex.

Photos are a few CC0 samples from alexeygrigorev/clothing-dataset (T-Shirt,
Polo, Undershirt). Physics stays ``shirt_t.obj``; the photo is warped into the
T UV and uploaded to the shirt skin / cloth material.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import numpy as np

from xfold.convert_cloth3d_mesh import load_obj
from xfold.generate_shirt_mesh import MODELS
from xfold.shirt_shot import write_png

GarmentKind = Literal["tshirt", "polo", "tank"]

GARMENT_KINDS: tuple[GarmentKind, ...] = ("tshirt", "polo", "tank")
GARMENT_LABELS: dict[GarmentKind, str] = {
    "tshirt": "Camiseta",
    "polo": "Polo",
    "tank": "Tirantes",
}

GARMENT_DIR = MODELS / "garments"
RAW_DIR = GARMENT_DIR / "raw"
PROJECTED_PNG = GARMENT_DIR / "projected.png"
TEX_SIZE = 256

# Vendored filenames + upstream ids (clothing-dataset images.csv).
SAMPLES: tuple[dict[str, str], ...] = (
    {
        "id": "tshirt_01",
        "kind": "tshirt",
        "file": "tshirt_01.jpg",
        "sourceId": "ea7b6656-3f84-4eb3-9099-23e623fc1018",
    },
    {
        "id": "tshirt_02",
        "kind": "tshirt",
        "file": "tshirt_02.jpg",
        "sourceId": "ea2ffd4d-9b25-4ca8-9dc2-bd27f1cc59fa",
    },
    {
        "id": "polo_01",
        "kind": "polo",
        "file": "polo_01.jpg",
        "sourceId": "ce5e1ff5-b923-462b-b897-c26d7c571ece",
    },
    {
        "id": "polo_02",
        "kind": "polo",
        "file": "polo_02.jpg",
        "sourceId": "f937d0b8-1c6f-432f-86a8-dac89c03b890",
    },
    {
        "id": "tank_01",
        "kind": "tank",
        "file": "tank_01.jpg",
        "sourceId": "f2ae0355-82ec-4363-ac61-470d7f422a45",
    },
    {
        "id": "tank_02",
        "kind": "tank",
        "file": "tank_02.jpg",
        "sourceId": "142c1548-ba32-4f34-9032-2ece7f8650ea",
    },
)

_DATASET = "https://github.com/alexeygrigorev/clothing-dataset"


def catalog() -> dict[str, Any]:
    """JSON for GET /garments — kinds + samples the UI may pick."""
    kinds = []
    for kind in GARMENT_KINDS:
        samples = [s for s in SAMPLES if s["kind"] == kind]
        kinds.append(
            {
                "id": kind,
                "label": GARMENT_LABELS[kind],
                "samples": [
                    {
                        "id": s["id"],
                        "file": s["file"],
                        "sourceId": s["sourceId"],
                    }
                    for s in samples
                ],
            }
        )
    return {
        "dataset": _DATASET,
        "license": "CC0",
        "kinds": kinds,
    }


def sample_path(sample_id: str) -> Path | None:
    for s in SAMPLES:
        if s["id"] == sample_id:
            path = RAW_DIR / s["file"]
            return path if path.is_file() else None
    return None


def resolve_sample(
    kind: str | None, garment_id: str | None, seed: int
) -> dict[str, str]:
    k: GarmentKind = kind if kind in GARMENT_KINDS else "tshirt"
    pool = [s for s in SAMPLES if s["kind"] == k]
    if garment_id:
        for s in pool:
            if s["id"] == garment_id:
                return s
    if not pool:
        return dict(SAMPLES[0])
    return pool[int(seed) % len(pool)]


def _load_jpeg(path: Path) -> np.ndarray:
    from PIL import Image

    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.uint8)


def _shirt_uv_mask(size: int) -> np.ndarray:
    """Rasterize shirt_t.obj XY into a UV occupancy mask (H, W) bool."""
    verts, faces = load_obj(MODELS / "shirt_t.obj")
    xy = np.asarray(verts[:, :2], dtype=np.float64)
    lo = xy.min(axis=0)
    span = np.maximum(xy.max(axis=0) - lo, 1e-6)
    uv = (xy - lo) / span
    px = np.clip(np.round(uv[:, 0] * (size - 1)).astype(np.int32), 0, size - 1)
    py = np.clip(np.round((1.0 - uv[:, 1]) * (size - 1)).astype(np.int32), 0, size - 1)
    mask = np.zeros((size, size), dtype=bool)
    for a, b, c in faces:
        _fill_triangle(mask, px[a], py[a], px[b], py[b], px[c], py[c])
    return mask


def _fill_triangle(mask: np.ndarray, x0, y0, x1, y1, x2, y2) -> None:
    minx, maxx = int(min(x0, x1, x2)), int(max(x0, x1, x2))
    miny, maxy = int(min(y0, y1, y2)), int(max(y0, y1, y2))
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(den) < 1e-6:
        return
    for y in range(miny, maxy + 1):
        for x in range(minx, maxx + 1):
            w0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / den
            w1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / den
            w2 = 1.0 - w0 - w1
            if w0 >= -1e-4 and w1 >= -1e-4 and w2 >= -1e-4:
                mask[y, x] = True


def _garment_mask(rgb: np.ndarray) -> np.ndarray:
    """Pixels that are not the photo's corner background (wood / tile / wall)."""
    h, w, _ = rgb.shape
    patch = 12
    corners = np.stack(
        [
            rgb[:patch, :patch].reshape(-1, 3).mean(0),
            rgb[:patch, -patch:].reshape(-1, 3).mean(0),
            rgb[-patch:, :patch].reshape(-1, 3).mean(0),
            rgb[-patch:, -patch:].reshape(-1, 3).mean(0),
        ]
    )
    bg = corners.mean(0)
    dist = np.linalg.norm(rgb.astype(np.float32) - bg, axis=2)
    mask = dist > 28.0
    # Drop a thin frame so leftover floor at the edges does not win the bbox.
    mask[:4, :] = False
    mask[-4:, :] = False
    mask[:, :4] = False
    mask[:, -4:] = False
    if not mask.any():
        mask[:] = True
    return mask


def project_photo(photo: np.ndarray, size: int = TEX_SIZE) -> np.ndarray:
    """Warp the photo's garment blob into the T UV silhouette."""
    tmask = _shirt_uv_mask(size)
    gmask = _garment_mask(photo)
    ys, xs = np.where(gmask)
    pys, pxs = np.where(tmask)
    canvas = np.full((size, size, 3), 42, dtype=np.uint8)
    if len(xs) < 8 or len(pxs) < 8:
        # Fallback: letterbox the whole photo into the T bbox.
        canvas[tmask] = 80
        return canvas
    src = photo[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    src_mask = gmask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    dst_y0, dst_y1 = int(pys.min()), int(pys.max())
    dst_x0, dst_x1 = int(pxs.min()), int(pxs.max())
    dh, dw = max(dst_y1 - dst_y0, 1), max(dst_x1 - dst_x0, 1)
    from PIL import Image

    fitted = np.asarray(
        Image.fromarray(src).resize((dw + 1, dh + 1), Image.Resampling.BILINEAR),
        dtype=np.uint8,
    )
    fitted_m = (
        np.asarray(
            Image.fromarray(src_mask.astype(np.uint8) * 255).resize(
                (dw + 1, dh + 1), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        )
        > 127
    )
    fill = (
        photo[gmask].mean(axis=0).astype(np.uint8)
        if gmask.any()
        else np.array([80, 80, 80], dtype=np.uint8)
    )
    canvas[tmask] = fill
    region = canvas[dst_y0 : dst_y1 + 1, dst_x0 : dst_x1 + 1]
    local = tmask[dst_y0 : dst_y1 + 1, dst_x0 : dst_x1 + 1] & fitted_m
    region[local] = fitted[local]
    canvas[dst_y0 : dst_y1 + 1, dst_x0 : dst_x1 + 1] = region
    return canvas


def project_for_run(
    kind: str | None, garment_id: str | None, seed: int
) -> tuple[np.ndarray, dict[str, str]]:
    sample = resolve_sample(kind, garment_id, seed)
    path = RAW_DIR / sample["file"]
    if not path.is_file():
        raise FileNotFoundError(path)
    rgb = project_photo(_load_jpeg(path))
    return rgb, sample


def apply_to_model(model: Any, rgb: np.ndarray) -> bool:
    """Tint shirt materials and upload RGB into the 2D garment texture."""
    import mujoco

    mean = np.clip(rgb.reshape(-1, 3).mean(axis=0) / 255.0, 0.05, 0.95)
    uploaded = False
    for mat_name in ("shirt_knit", "shirt_cloth", "shirt_garment"):
        mid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_MATERIAL, mat_name)
        if mid >= 0:
            model.mat_rgba[mid, 0:3] = mean
            model.mat_rgba[mid, 3] = 1.0
    for tex_name in ("shirt_knit", "shirt_garment"):
        tid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_TEXTURE, tex_name)
        if tid < 0:
            continue
        h = int(model.tex_height[tid])
        w = int(model.tex_width[tid])
        if h <= 0 or w <= 0:
            continue
        from PIL import Image

        resized = np.asarray(
            Image.fromarray(rgb).resize((w, h), Image.Resampling.BILINEAR),
            dtype=np.uint8,
        )
        nchan = 3
        if hasattr(model, "tex_nchannel"):
            nchan = int(np.atleast_1d(model.tex_nchannel)[tid])
        adr = int(model.tex_adr[tid])
        if nchan == 4:
            rgba = np.concatenate(
                [resized, np.full((h, w, 1), 255, dtype=np.uint8)], axis=2
            )
            blob = rgba.reshape(-1)
        else:
            blob = resized.reshape(-1)
        n = h * w * nchan
        data = getattr(model, "tex_data", None)
        if data is None:
            data = getattr(model, "tex_rgb", None)
        if data is None:
            continue
        data[adr : adr + n] = blob[:n]
        uploaded = True
    PROJECTED_PNG.parent.mkdir(parents=True, exist_ok=True)
    write_png(PROJECTED_PNG, rgb)
    return uploaded


def write_default_projected() -> Path:
    rgb, _ = project_for_run("tshirt", "tshirt_01", 0)
    PROJECTED_PNG.parent.mkdir(parents=True, exist_ok=True)
    write_png(PROJECTED_PNG, rgb)
    return PROJECTED_PNG
