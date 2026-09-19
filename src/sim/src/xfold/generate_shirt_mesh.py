"""Generate a flat adult T-shirt surface (OBJ) for MuJoCo flexcomp.

The outline is a real T — torso, short sleeves, crew neck — sized for the
Japanese / ninja fold in SOLUTION.md §5.3:

  body 0.60 × 0.64 m  →  left/right thirds of 0.20 m, hem fold ≈ 0.28 m
  sleeves 0.15 m      →  the bits the flip has to hide
  packet target       →  0.20 × 0.28 m

Vertex count stays near 160 so the platen can support the whole sheet
(mjMAXCONPAIR = 50, SOLUTION.md §4.3).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

MODELS = Path(__file__).resolve().parents[2] / "models"
DEFAULT_OUT = MODELS / "shirt_t.obj"

# Rest-frame metres. X = left/right, Y = hem (−) → collar (+).
BODY_W = 0.60
BODY_L = 0.64
SLEEVE_L = 0.15
SLEEVE_H = 0.18
NECK_W = 0.18
NECK_D = 0.08
DEFAULT_SPACING = 0.050

# Ninja crease lines (SOLUTION.md §5.3): pinch on x = ±BODY_W/6.
LEFT_CREASE_X = -BODY_W / 6.0
RIGHT_CREASE_X = BODY_W / 6.0


def shirt_outline() -> np.ndarray:
    """Closed iconic T, clockwise, starting at the left neck."""
    hw = 0.5 * BODY_W
    hl = 0.5 * BODY_L
    nw = 0.5 * NECK_W
    # Sleeve sits on the shoulder band; cuff is slightly dropped.
    y_collar = hl
    y_shoulder = hl - 0.02
    y_cuff_top = y_shoulder - 0.03
    y_armpit = y_shoulder - SLEEVE_H
    y_hem = -hl
    x_cuff = hw + SLEEVE_L

    return np.array(
        [
            (-nw, y_collar),
            (-hw + 0.02, y_shoulder),
            (-x_cuff, y_cuff_top),
            (-x_cuff - 0.01, y_cuff_top - 0.55 * SLEEVE_H),
            (-x_cuff, y_armpit),
            (-hw, y_armpit),
            (-hw - 0.01, y_hem + 0.06),
            (-hw + 0.02, y_hem),
            (0.0, y_hem - 0.02),
            (hw - 0.02, y_hem),
            (hw + 0.01, y_hem + 0.06),
            (hw, y_armpit),
            (x_cuff, y_armpit),
            (x_cuff + 0.01, y_cuff_top - 0.55 * SLEEVE_H),
            (x_cuff, y_cuff_top),
            (hw - 0.02, y_shoulder),
            (nw, y_collar),
            (0.4 * nw, y_collar - NECK_D),
            (-0.4 * nw, y_collar - NECK_D),
        ],
        dtype=np.float64,
    )


def _point_in_poly(x: float, y: float, poly: np.ndarray) -> bool:
    """Even-odd ray cast. The neck is a bite in the outline, not a hole."""
    inside = False
    n = len(poly)
    x1, y1 = poly[-1]
    for x2, y2 in poly:
        if (y1 > y) != (y2 > y):
            xing = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-18) + x1
            if x < xing:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def _axis(lo: float, hi: float, spacing: float) -> np.ndarray:
    n = int(np.floor((hi - lo) / spacing)) + 1
    span = (n - 1) * spacing
    start = 0.5 * (lo + hi) - 0.5 * span
    return start + spacing * np.arange(n)


def build_mesh(spacing: float = DEFAULT_SPACING) -> tuple[np.ndarray, np.ndarray]:
    poly = shirt_outline()
    pad = 0.02
    xs = _axis(float(poly[:, 0].min()) - pad, float(poly[:, 0].max()) + pad, spacing)
    ys = _axis(float(poly[:, 1].min()) - pad, float(poly[:, 1].max()) + pad, spacing)
    idx = -np.ones((len(ys), len(xs)), dtype=np.int32)
    verts: list[tuple[float, float, float]] = []
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            if _point_in_poly(float(x), float(y), poly):
                idx[j, i] = len(verts)
                verts.append((float(x), float(y), 0.0))

    faces: list[tuple[int, int, int]] = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            a, b = idx[j, i], idx[j, i + 1]
            c, d = idx[j + 1, i], idx[j + 1, i + 1]
            if a >= 0 and b >= 0 and c >= 0 and d >= 0:
                faces.append((a, b, d))
                faces.append((a, d, c))
            elif a >= 0 and b >= 0 and d >= 0:
                faces.append((a, b, d))
            elif a >= 0 and d >= 0 and c >= 0:
                faces.append((a, d, c))
            elif a >= 0 and b >= 0 and c >= 0:
                faces.append((a, b, c))
            elif b >= 0 and d >= 0 and c >= 0:
                faces.append((b, d, c))

    if not verts or not faces:
        raise RuntimeError("T-shirt mesh is empty — check silhouette bounds")
    return np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int32)


def write_obj(path: Path, verts: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("# XFOLD adult T-shirt (ninja-fold proportions, sleeves + crew neck)\n")
        f.write(f"# verts={len(verts)} faces={len(faces)}\n")
        f.write(f"# body={BODY_W:.2f}x{BODY_L:.2f} crease_x=±{BODY_W/6:.3f}\n")
        for x, y, z in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            f.write(f"f {a + 1} {b + 1} {c + 1}\n")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--spacing", type=float, default=DEFAULT_SPACING)
    args = p.parse_args(argv)
    verts, faces = build_mesh(args.spacing)
    write_obj(args.out, verts, faces)
    print(
        f"wrote {args.out}  verts={len(verts)}  faces={len(faces)}  "
        f"span={np.ptp(verts[:, 0]):.3f}×{np.ptp(verts[:, 1]):.3f} m  "
        f"thirds={BODY_W/3:.2f} m",
        flush=True,
    )


if __name__ == "__main__":
    main()
