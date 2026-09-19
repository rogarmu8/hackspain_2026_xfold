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


def stamp(canvas: np.ndarray, mark: np.ndarray, frac: float, *, cy: float = 0.5) -> None:
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
    x0 = (w - mw) // 2
    y0 = int(round(h * cy)) - mh // 2
    y0 = max(0, min(h - mh, y0))
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


def bake_catalog(mark_path: Path = DEFAULT_MARK) -> None:
    """Write PNG skins for every catalogue garment that is not the default T.

    Cloth is the same white as the default T. Silhouette carries the type;
    ink is only a small chest print / stitch so vision HSV stays white-cloth.
    """
    from PIL import Image, ImageDraw, ImageFont

    mark = extract_mark(_load_rgb(mark_path))
    size = SIZE
    ink = tuple(int(c) for c in INK)

    def white() -> np.ndarray:
        return np.full((size, size, 3), CLOTH, dtype=np.float64)

    def _font(px: int):
        try:
            return ImageFont.truetype("Arial.ttf", px)
        except OSError:
            return ImageFont.load_default()

    # Work tee: white + pocket stitch + tiny mark.
    work = white()
    stamp(work, mark, 0.055, cy=0.46)
    img = Image.fromarray(np.clip(work, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    pocket = (int(size * 0.62), int(size * 0.48), int(size * 0.78), int(size * 0.62))
    draw.rounded_rectangle(pocket, radius=12, outline=ink, width=3)
    _save_png(MODELS / "garment_work_tee.png", np.asarray(img))

    # Jersey: white + number 10.
    jersey = white()
    img = Image.fromarray(np.clip(jersey, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    text = "10"
    font = _font(size // 5)
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - size * 0.02), text, fill=ink, font=font)
    _save_png(MODELS / "garment_jersey.png", np.asarray(img.convert("RGB")))

    # Tank: white + mark.
    tank = white()
    stamp(tank, mark, 0.09, cy=0.48)
    _save_png(MODELS / "garment_tank.png", np.clip(tank, 0, 255).astype(np.uint8))

    # Polo: white + placket stitch + tiny mark.
    polo = white()
    stamp(polo, mark, 0.06, cy=0.48)
    img = Image.fromarray(np.clip(polo, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    cx = size // 2
    draw.line([(cx, int(size * 0.18)), (cx, int(size * 0.38))], fill=ink, width=4)
    _save_png(MODELS / "garment_polo.png", np.asarray(img))

    # A-line tee-dress: same white + mark.
    dress = white()
    stamp(dress, mark, 0.07)
    _save_png(MODELS / "garment_dress.png", np.clip(dress, 0, 255).astype(np.uint8))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mark", type=Path, default=DEFAULT_MARK)
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--frac", type=float, default=MARK_FRAC)
    p.add_argument("--catalog", action="store_true", help="Bake jersey / tank / polo / dress / work tee")
    args = p.parse_args(argv)
    if not args.mark.is_file():
        raise SystemExit(f"mark image not found: {args.mark}")
    if args.catalog:
        bake_catalog(args.mark)
        print("wrote garment_*.png", flush=True)
        return
    make_print(args.mark, args.out, frac=args.frac)
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
