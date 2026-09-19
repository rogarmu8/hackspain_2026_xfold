"""Bake a white T-shirt print with a tiny AlphaFold α^x on the chest."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from xfold.generate_shirt_mesh import MODELS
from xfold.shirt_shot import write_png

DEFAULT_OUT = MODELS / "shirt_print.png"
DEFAULT_MARK = MODELS / "shirt_mark.png"
# Ink from the AlphaFold lockup, not pure black (reads as a print, not a hole).
INK = np.array([10, 47, 68], dtype=np.float64)
CLOTH = np.array([246, 246, 248], dtype=np.float64)
SIZE = 1024
# Glyph width as a fraction of the texture — ~6 cm on the 0.92 m sleeve span.
MARK_FRAC = 0.07


def _load_rgb(path: Path) -> np.ndarray:
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("Pillow is required to read the AlphaFold mark")
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def extract_mark(rgb: np.ndarray) -> np.ndarray:
    """Crop the dark glyph and return RGB on a cloth-white field."""
    gray = rgb.mean(axis=2)
    ink = gray < 90.0
    if ink.sum() < 100:
        raise RuntimeError(f"no ink found in mark image (dark pixels={int(ink.sum())})")
    ys, xs = np.where(ink)
    pad = 8
    y0, y1 = max(0, int(ys.min()) - pad), min(rgb.shape[0], int(ys.max()) + pad + 1)
    x0, x1 = max(0, int(xs.min()) - pad), min(rgb.shape[1], int(xs.max()) + pad + 1)
    crop = rgb[y0:y1, x0:x1].astype(np.float64)
    g = crop.mean(axis=2)
    # Smooth coverage so the edges are not crunchy on a 7% stamp.
    t = np.clip((90.0 - g) / 55.0, 0.0, 1.0)[..., None]
    cropped = CLOTH + t * (INK - CLOTH)
    return cropped


def stamp(canvas: np.ndarray, mark: np.ndarray, frac: float) -> None:
    h, w = canvas.shape[:2]
    mw = max(8, int(round(w * frac)))
    scale = mw / mark.shape[1]
    mh = max(8, int(round(mark.shape[0] * scale)))
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("Pillow is required to scale the AlphaFold mark")
    small = np.asarray(
        Image.fromarray(np.clip(mark, 0, 255).astype(np.uint8)).resize(
            (mw, mh), Image.Resampling.LANCZOS
        ),
        dtype=np.float64,
    )
    # Dead centre of the T panel (unit-square UVs).
    x0 = (w - mw) // 2
    y0 = (h - mh) // 2
    canvas[y0 : y0 + mh, x0 : x0 + mw] = small


def _save_png(path: Path, rgb: np.ndarray) -> None:
    try:
        from PIL import Image
    except ImportError:
        write_png(path, rgb)
        return
    Image.fromarray(rgb).save(path, format="PNG", optimize=True)


def make_print(mark_path: Path, out: Path, size: int = SIZE, frac: float = MARK_FRAC) -> None:
    cloth = np.full((size, size, 3), CLOTH, dtype=np.float64)
    mark = extract_mark(_load_rgb(mark_path))
    stamp(cloth, mark, frac)
    out.parent.mkdir(parents=True, exist_ok=True)
    rgb = np.clip(cloth, 0, 255).astype(np.uint8)
    _save_png(out, rgb)
    if mark_path.resolve() != DEFAULT_MARK.resolve():
        _save_png(DEFAULT_MARK, np.clip(mark, 0, 255).astype(np.uint8))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mark", type=Path, default=DEFAULT_MARK)
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--frac", type=float, default=MARK_FRAC)
    args = p.parse_args(argv)
    if not args.mark.is_file():
        raise SystemExit(f"mark image not found: {args.mark}")
    make_print(args.mark, args.out, frac=args.frac)
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
