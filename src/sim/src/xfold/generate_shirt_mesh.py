"""T-shirt pattern for the two-claw ninja fold (SOLUTION.md §5.3).

Default output is a *single* iconic T panel — circular crew neck, hanging
short sleeves, stadium hem. The pressed sheet the clamps crease.
`--shell` sews a hollow front+back copy (wearable topology) but that bag
cannot hold a Japanese fold: the layers slide and the T becomes a rag.

Body 0.60 × 0.64 m → thirds of 0.20 m, hem fold ≈ 0.28 m.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

MODELS = Path(__file__).resolve().parents[2] / "models"
DEFAULT_OUT = MODELS / "shirt_t.obj"

BODY_W = 0.60
BODY_L = 0.64
# Laid-flat stack: two layers, not a worn torso. Wearable topology, foldable pose.
TORSO_D = 0.012
# Iconic crew-neck T (front view): circular collar, hanging short sleeves,
# rounded hem. Extents stay on the 0.70 m press / ninja thirds.
SLEEVE_L = 0.16
SLEEVE_H = 0.16
NECK_W = 0.22
NECK_D = 0.11
DEFAULT_SPACING = 0.032
DEFAULT_NX = 22
DEFAULT_NY = 24
DEFAULT_NS = 6
# Unit-square UVs: one PNG covers the whole T (collar at the top of the
# image). A chest print stays in the middle instead of tiling.

LEFT_CREASE_X = -BODY_W / 6.0
RIGHT_CREASE_X = BODY_W / 6.0

_HEM, _NECK, _LCUFF, _RCUFF, _SEAM = "hem", "neck", "lcuff", "rcuff", "seam"

# Ellipses (cx, cy, rx, ry) in the OBJ frame. Interior holes + bites that
# chew the hem / sleeve so the damaged twin is not just a dirty print.
_DAMAGE_CUTS: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "tee_damaged": (
        (0.08, 0.05, 0.050, 0.042),
        (0.14, -0.32, 0.080, 0.058),
    ),
    "work_tee_damaged": (
        (0.16, 0.00, 0.044, 0.038),
        (-0.18, -0.32, 0.075, 0.055),
    ),
    "jersey_damaged": (
        (0.00, 0.02, 0.060, 0.052),
        (-0.52, 0.20, 0.085, 0.055),
    ),
    "tank_damaged": (
        (0.05, 0.00, 0.055, 0.048),
        (-0.12, -0.32, 0.070, 0.052),
    ),
    "polo_damaged": (
        (0.04, 0.02, 0.045, 0.038),
        (0.10, -0.27, 0.072, 0.050),
    ),
    "dress_damaged": (
        (0.12, -0.22, 0.070, 0.062),
        (0.34, -0.54, 0.090, 0.070),
    ),
}


def damage_cuts(garment_key: str) -> tuple[tuple[float, float, float, float], ...]:
    return _DAMAGE_CUTS.get(garment_key, ())


def _arc(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, n: int) -> np.ndarray:
    t = np.linspace(a0, a1, n, dtype=np.float64)
    return np.column_stack((cx + rx * np.cos(t), cy + ry * np.sin(t)))


def _bezier(p0, p1, p2, p3, n: int) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float64)
    u = 1.0 - t
    w = np.column_stack((u**3, 3.0 * u**2 * t, 3.0 * u * t**2, t**3))
    pts = np.stack([np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64),
                    np.asarray(p2, dtype=np.float64), np.asarray(p3, dtype=np.float64)])
    return w @ pts


def _join(*parts: np.ndarray) -> np.ndarray:
    chunks = [np.asarray(parts[0], dtype=np.float64)]
    for part in parts[1:]:
        pts = np.asarray(part, dtype=np.float64)
        if np.allclose(chunks[-1][-1], pts[0], atol=1e-9):
            chunks.append(pts[1:])
        else:
            chunks.append(pts)
    return np.vstack(chunks)


def shirt_outline(style: str = "tee") -> np.ndarray:
    """Closed foldable panel, clockwise from the left neck.

    One loop (U or V, not a hole) so the sheet stays a FlipFold / ninja panel.
    """
    style = "tee" if style in ("tee", "work_tee") else style
    if style == "tank":
        return _outline_tank()
    if style == "jersey":
        return _outline_jersey()
    if style == "polo":
        return _outline_polo()
    if style == "dress":
        return _outline_dress()
    if style == "custom":
        loaded = load_custom_outline()
        return loaded if loaded is not None else _outline_square()
    if style != "tee":
        raise ValueError(f"unknown panel style {style!r}")
    return _outline_crew()


def _outline_square(side: float = BODY_W) -> np.ndarray:
    """Fallback sheet when the operator photo has no usable silhouette."""
    h = side / 2.0
    return np.array(
        ((-h, -h), (h, -h), (h, h), (-h, h), (-h, -h)),
        dtype=np.float64,
    )


CUSTOM_MESH_PATH = MODELS / "garment_custom.obj"
CUSTOM_OUTLINE_PATH = MODELS / "_custom_outline.npy"


def load_custom_outline() -> np.ndarray | None:
    """Detected garment loop in metres, or ``None`` to keep the square sheet."""
    path = CUSTOM_OUTLINE_PATH
    if not path.is_file():
        return None
    try:
        poly = np.load(path)
    except Exception:
        return None
    if poly.ndim != 2 or poly.shape[-1] != 2 or len(poly) < 4:
        return None
    return np.asarray(poly, dtype=np.float64)


def square_domain_uvs(verts: np.ndarray, side: float = BODY_W) -> np.ndarray:
    """UVs against the letterboxed PNG, not the silhouette AABB.

    The print is baked into a square. After the mesh is cut to the outline,
    sampling the same square keeps the photo aligned with the cut.
    """
    u = verts[:, 0] / side + 0.5
    v = verts[:, 1] / side + 0.5
    return np.column_stack((u, v))


def ensure_custom_mesh() -> Path:
    """Rebuild ``garment_custom.obj`` from the latest detected outline."""
    path = CUSTOM_MESH_PATH
    verts, faces = build_panel(DEFAULT_SPACING, style="custom")
    write_obj(path, verts, faces, shell=False, uvs=square_domain_uvs(verts))
    return path


def _outline_crew(
    *,
    neck: str = "crew",
    sleeve_l: float = SLEEVE_L,
    sleeve_h: float = SLEEVE_H,
    neck_w: float = NECK_W,
    neck_d: float = NECK_D,
    hem_flare: float = 0.0,
) -> np.ndarray:
    hw = 0.5 * BODY_W
    hl = 0.5 * BODY_L
    neck_cy = hl - 0.015
    neck_rx, neck_ry = 0.5 * neck_w, neck_d
    a_right = np.deg2rad(18.0)
    a_left = np.deg2rad(-198.0)
    left_neck = (
        neck_rx * np.cos(a_left),
        neck_cy + neck_ry * np.sin(a_left),
    )

    shoulder = _bezier(
        left_neck,
        (-0.15, hl + 0.01),
        (-0.22, hl - 0.005),
        (-hw + 0.03, hl - 0.025),
        8,
    )
    sleeve_top = _bezier(
        shoulder[-1],
        (-hw - 0.05, hl - 0.04),
        (-hw - 0.10, hl - 0.08),
        (-hw - sleeve_l + 0.03, hl - 0.11),
        7,
    )
    cuff = _arc(
        -hw - sleeve_l + 0.05,
        hl - 0.16,
        0.048,
        0.052,
        np.deg2rad(100.0),
        np.deg2rad(260.0),
        12,
    )
    to_armpit = _bezier(
        cuff[-1],
        (-hw - 0.08, hl - 0.21),
        (-hw - 0.02, hl - 0.185),
        (-hw, hl - sleeve_h),
        6,
    )
    side_x = -hw - hem_flare
    side = _bezier(
        to_armpit[-1],
        (-hw, 0.02),
        (side_x, -hl + 0.18),
        (side_x, -hl + 0.08),
        8,
    )
    hem_r = 0.085 + 0.4 * hem_flare
    hem = _arc(side_x + hem_r, -hl + hem_r, hem_r, hem_r, np.pi, 1.5 * np.pi, 10)
    hem = np.vstack([hem, np.array([[0.0, -hl]], dtype=np.float64)])

    left = _join(shoulder, sleeve_top, cuff, to_armpit, side, hem)
    right = left[-2:0:-1].copy()
    right[:, 0] *= -1.0
    if neck == "v":
        v_tip = np.array([0.0, neck_cy - neck_ry], dtype=np.float64)
        right_pt = np.array(
            [neck_rx * np.cos(a_right), neck_cy + neck_ry * np.sin(a_right)]
        )
        left_pt = np.array(left_neck)
        neck_pts = np.vstack([right_pt, v_tip, left_pt])
    else:
        neck_pts = _arc(0.0, neck_cy, neck_rx, neck_ry, a_right, a_left, 18)
    return _join(left, right, neck_pts)


def _outline_tank() -> np.ndarray:
    """Sleeveless muscle tank: thin straps, deep armholes, torso past the pins.

    Body is wider than the folder's side hinges (±0.16 m) so the sheet sits on
    the flaps and the deck, not down between the rails. Straps stay narrow so
    it still reads as sleeveless next to a tee.
    """
    hw = 0.38  # 0.76 m torso; FlipFold pins leave a 0.32 m pack
    hl = 0.5 * BODY_L
    # Straps ~5 cm, well inside the torso (tee sleeves reach ±0.46 m).
    strap_i, strap_o = 0.09, 0.145
    neck_cy = hl - 0.03
    neck_rx, neck_ry = 0.10, 0.13
    a_right = np.deg2rad(12.0)
    a_left = np.deg2rad(-192.0)
    left_neck = (
        neck_rx * np.cos(a_left),
        neck_cy + neck_ry * np.sin(a_left),
    )
    strap = _bezier(
        left_neck,
        (-strap_i, hl + 0.025),
        (-strap_o, hl + 0.025),
        (-strap_o, hl - 0.01),
        8,
    )
    armhole = _bezier(
        strap[-1],
        (-strap_o - 0.02, hl - 0.12),
        (-hw + 0.12, hl - 0.22),
        (-hw, hl - 0.36),
        12,
    )
    side = _bezier(
        armhole[-1],
        (-hw, 0.0),
        (-hw, -hl + 0.18),
        (-hw, -hl + 0.08),
        8,
    )
    hem_r = 0.085
    hem = _arc(-hw + hem_r, -hl + hem_r, hem_r, hem_r, np.pi, 1.5 * np.pi, 10)
    hem = np.vstack([hem, np.array([[0.0, -hl]], dtype=np.float64)])
    left = _join(strap, armhole, side, hem)
    right = left[-2:0:-1].copy()
    right[:, 0] *= -1.0
    neck = _arc(0.0, neck_cy, neck_rx, neck_ry, a_right, a_left, 16)
    return _join(left, right, neck)


def _outline_jersey() -> np.ndarray:
    """Deep V, long raglan sleeves, longer body — not a crew T with stripes."""
    hw = 0.33
    hl = 0.40
    sleeve_l = 0.30
    v_half = 0.11
    v_depth = 0.26
    left_neck = (-v_half, hl - 0.02)
    raglan = _bezier(
        left_neck,
        (-0.20, hl + 0.03),
        (-hw - 0.10, hl - 0.02),
        (-hw - sleeve_l + 0.05, hl - 0.10),
        10,
    )
    cuff = _arc(
        -hw - sleeve_l + 0.07,
        hl - 0.17,
        0.058,
        0.062,
        np.deg2rad(95.0),
        np.deg2rad(265.0),
        12,
    )
    to_armpit = _bezier(
        cuff[-1],
        (-hw - 0.14, hl - 0.26),
        (-hw - 0.04, hl - 0.32),
        (-hw, hl - 0.36),
        7,
    )
    side = _bezier(
        to_armpit[-1],
        (-hw - 0.01, 0.04),
        (-hw + 0.01, -hl + 0.18),
        (-hw, -hl + 0.05),
        8,
    )
    hem = _bezier(
        side[-1],
        (-hw + 0.04, -hl),
        (-0.10, -hl - 0.008),
        (0.0, -hl),
        8,
    )
    left = _join(raglan, cuff, to_armpit, side, hem)
    right = left[-2:0:-1].copy()
    right[:, 0] *= -1.0
    down = np.column_stack(
        (np.linspace(v_half, 0.0, 9), np.linspace(hl - 0.02, hl - v_depth, 9))
    )
    up = np.column_stack(
        (np.linspace(0.0, -v_half, 9), np.linspace(hl - v_depth, hl - 0.02, 9))
    )
    neck = np.vstack([down, up[1:]])
    return _join(left, right, neck)


def _outline_polo() -> np.ndarray:
    """Spread collar points + cap sleeves + boxy hem."""
    hw = 0.27
    hl = 0.27
    left_neck = (-0.05, hl - 0.05)
    collar = _bezier(
        left_neck,
        (-0.07, hl + 0.05),
        (-0.12, hl + 0.13),
        (-0.18, hl + 0.11),
        8,
    )
    to_shoulder = _bezier(
        collar[-1],
        (-0.20, hl + 0.04),
        (-0.22, hl + 0.01),
        (-hw + 0.03, hl - 0.02),
        6,
    )
    sleeve_top = _bezier(
        to_shoulder[-1],
        (-hw - 0.03, hl - 0.03),
        (-hw - 0.07, hl - 0.06),
        (-hw - 0.09, hl - 0.10),
        6,
    )
    cuff = _arc(
        -hw - 0.055,
        hl - 0.13,
        0.032,
        0.036,
        np.deg2rad(80.0),
        np.deg2rad(250.0),
        8,
    )
    to_armpit = _bezier(
        cuff[-1],
        (-hw - 0.03, hl - 0.16),
        (-hw - 0.01, hl - 0.18),
        (-hw, hl - 0.20),
        5,
    )
    side = _bezier(
        to_armpit[-1],
        (-hw, 0.0),
        (-hw, -hl + 0.10),
        (-hw, -hl + 0.03),
        6,
    )
    hem = _bezier(
        side[-1],
        (-hw + 0.02, -hl),
        (-0.08, -hl - 0.006),
        (0.0, -hl),
        8,
    )
    left = _join(collar, to_shoulder, sleeve_top, cuff, to_armpit, side, hem)
    right = left[-2:0:-1].copy()
    right[:, 0] *= -1.0
    neck = _bezier(
        (0.05, hl - 0.05),
        (0.02, hl - 0.12),
        (-0.02, hl - 0.12),
        (-0.05, hl - 0.05),
        10,
    )
    return _join(left, right, neck)


def _outline_dress() -> np.ndarray:
    """Pinafore: braces, bib, long A-line skirt — not a flared T."""
    strap_i, strap_o = 0.06, 0.14
    bib_y = 0.20
    brace_top = 0.48
    bib_hw = 0.21
    hem_hw = 0.50
    hem_y = -0.54
    left_neck = (-strap_i, bib_y)
    inner_up = _bezier(
        left_neck,
        (-strap_i, bib_y + 0.12),
        (-strap_i - 0.005, brace_top - 0.05),
        (-strap_i, brace_top),
        8,
    )
    cap = _bezier(
        inner_up[-1],
        (-strap_i - 0.01, brace_top + 0.035),
        (-strap_o + 0.01, brace_top + 0.035),
        (-strap_o, brace_top),
        6,
    )
    outer_down = _bezier(
        cap[-1],
        (-strap_o, brace_top - 0.10),
        (-strap_o + 0.01, bib_y + 0.06),
        (-strap_o, bib_y),
        8,
    )
    to_arm = _bezier(
        outer_down[-1],
        (-0.17, bib_y - 0.02),
        (-bib_hw + 0.02, bib_y - 0.05),
        (-bib_hw, bib_y - 0.10),
        6,
    )
    armhole = _bezier(
        to_arm[-1],
        (-bib_hw - 0.05, bib_y - 0.18),
        (-bib_hw - 0.02, 0.02),
        (-bib_hw - 0.05, -0.06),
        10,
    )
    flare = _bezier(
        armhole[-1],
        (-0.30, -0.18),
        (-hem_hw + 0.05, hem_y + 0.16),
        (-hem_hw, hem_y + 0.08),
        10,
    )
    hem_r = 0.11
    hem = _arc(-hem_hw + hem_r, hem_y + hem_r, hem_r, hem_r, np.pi, 1.5 * np.pi, 10)
    hem = np.vstack([hem, np.array([[0.0, hem_y]], dtype=np.float64)])
    left = _join(inner_up, cap, outer_down, to_arm, armhole, flare, hem)
    right = left[-2:0:-1].copy()
    right[:, 0] *= -1.0
    neck = _bezier(
        (strap_i, bib_y),
        (0.03, bib_y - 0.10),
        (-0.03, bib_y - 0.10),
        (-strap_i, bib_y),
        12,
    )
    return _join(left, right, neck)


def _point_in_poly(x: float, y: float, poly: np.ndarray) -> bool:
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


def _in_cut(x: float, y: float, cuts: tuple[tuple[float, float, float, float], ...]) -> bool:
    for cx, cy, rx, ry in cuts:
        if ((x - cx) / max(rx, 1e-6)) ** 2 + ((y - cy) / max(ry, 1e-6)) ** 2 <= 1.0:
            return True
    return False


def _axis(lo: float, hi: float, spacing: float) -> np.ndarray:
    n = int(np.floor((hi - lo) / spacing)) + 1
    span = (n - 1) * spacing
    start = 0.5 * (lo + hi) - 0.5 * span
    return start + spacing * np.arange(n)


def _quad(faces: list[tuple[int, int, int]], a: int, b: int, c: int, d: int) -> None:
    faces.append((a, b, c))
    faces.append((a, c, d))


def _signed_area(tri: np.ndarray) -> float:
    a, b, c = tri
    return 0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))


def _closest_on_poly(point: np.ndarray, poly: np.ndarray) -> np.ndarray:
    pts = np.vstack([poly, poly[0]])
    best = pts[0]
    best_d = np.inf
    for a, b in zip(pts[:-1], pts[1:]):
        ab = b - a
        span = float(np.dot(ab, ab)) + 1e-18
        t = float(np.clip(np.dot(point - a, ab) / span, 0.0, 1.0))
        q = a + t * ab
        d = float(np.sum((point - q) ** 2))
        if d < best_d:
            best_d = d
            best = q
    return best


def _remap_used(verts: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    used = np.unique(faces)
    remap = -np.ones(len(verts), dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    return verts[used], remap[faces]


def _fit_boundary(
    verts: np.ndarray,
    faces: np.ndarray,
    poly: np.ndarray,
    *,
    cuts: tuple[tuple[float, float, float, float], ...] = (),
) -> tuple[np.ndarray, np.ndarray]:
    """Project the outer grid silhouette onto the sewing outline."""
    loops = boundary_loops(faces)
    if not loops:
        return verts, faces
    if not cuts and len(loops) != 1:
        return verts, faces
    outer = max(loops, key=len)
    out = verts.copy()
    for index in outer:
        out[index, :2] = _closest_on_poly(out[index, :2], poly)

    keep: list[tuple[int, int, int]] = []
    for face in faces:
        tri = out[face]
        if _signed_area(tri[:, :2]) < 1e-10:
            continue
        c = tri.mean(axis=0)
        if not _point_in_poly(float(c[0]), float(c[1]), poly):
            continue
        if cuts and _in_cut(float(c[0]), float(c[1]), cuts):
            continue
        keep.append((int(face[0]), int(face[1]), int(face[2])))
    if not keep:
        return verts, faces
    faces2 = np.asarray(keep, dtype=np.int32)
    fitted_v, fitted_f = _remap_used(out, faces2)
    nloop = len(boundary_loops(fitted_f))
    if cuts:
        return (fitted_v, fitted_f) if nloop >= 1 else (out, faces)
    if nloop == 1:
        return fitted_v, fitted_f
    return out, faces


def build_panel(
    spacing: float,
    style: str = "tee",
    *,
    cuts: tuple[tuple[float, float, float, float], ...] = (),
    poly: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """One foldable 2D panel (z = 0) from the sewing pattern."""
    outline = np.asarray(
        poly if poly is not None else shirt_outline(style),
        dtype=np.float64,
    )
    if len(outline) >= 2 and not np.allclose(outline[0], outline[-1]):
        outline = np.vstack((outline, outline[0]))
    pad = 0.5 * spacing
    xs = _axis(float(outline[:, 0].min()) - pad, float(outline[:, 0].max()) + pad, spacing)
    ys = _axis(float(outline[:, 1].min()) - pad, float(outline[:, 1].max()) + pad, spacing)
    idx = -np.ones((len(ys), len(xs)), dtype=np.int32)
    verts: list[tuple[float, float, float]] = []
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            if not _point_in_poly(float(x), float(y), outline):
                continue
            if cuts and _in_cut(float(x), float(y), cuts):
                continue
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
        raise RuntimeError("T-shirt panel is empty — check silhouette bounds")
    mesh_v = np.asarray(verts, dtype=np.float64)
    mesh_f = np.asarray(faces, dtype=np.int32)
    fitted_v, fitted_f = _fit_boundary(mesh_v, mesh_f, outline, cuts=cuts)
    try:
        validate_mesh(fitted_v, fitted_f, shell=False)
    except RuntimeError:
        return mesh_v, mesh_f
    return fitted_v, fitted_f


def _oriented_boundary(faces: np.ndarray) -> list[tuple[int, int]]:
    seen: dict[tuple[int, int], int] = {}
    for a, b, c in faces:
        for u, v in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            key = (u, v) if u < v else (v, u)
            seen[key] = seen.get(key, 0) + 1
    edges: list[tuple[int, int]] = []
    for a, b, c in faces:
        for u, v in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            key = (u, v) if u < v else (v, u)
            if seen[key] == 1:
                edges.append((u, v))
    return edges


def _label_vert(x: float, y: float, xs: np.ndarray, ys: np.ndarray) -> str:
    xmin, xmax = float(xs.min()), float(xs.max())
    ymin, ymax = float(ys.min()), float(ys.max())
    pad = 0.018
    hw = 0.5 * BODY_W
    if y <= ymin + pad:
        return _HEM
    if x <= xmin + pad:
        return _LCUFF
    if x >= xmax - pad:
        return _RCUFF
    if y >= ymax - NECK_D - 0.04 - pad and abs(x) <= 0.5 * NECK_W + pad:
        return _NECK
    # Neck bite sits inside the bounding box; catch the circular U as well.
    if y >= 0.5 * BODY_L - NECK_D - 0.04 - pad and abs(x) <= 0.5 * NECK_W + 0.02:
        return _NECK
    if abs(x) >= hw + 0.5 * SLEEVE_L and x < 0:
        return _LCUFF
    if abs(x) >= hw + 0.5 * SLEEVE_L and x > 0:
        return _RCUFF
    return _SEAM


def build_sewn_t(spacing: float = DEFAULT_SPACING, depth: float = TORSO_D) -> tuple[np.ndarray, np.ndarray]:
    """Front + back panels, seams welded, four openings left open."""
    panel, faces2 = build_panel(spacing)
    n = len(panel)
    front = panel.copy()
    front[:, 2] = 0.0
    back = panel.copy()
    back[:, 2] = float(depth)
    verts = np.vstack([front, back])
    faces = [tuple(int(v) for v in f) for f in faces2]
    faces.extend(tuple(int(v) + n for v in (a, c, b)) for a, b, c in faces2)

    xs, ys = panel[:, 0], panel[:, 1]
    labels = [_label_vert(float(x), float(y), xs, ys) for x, y in panel[:, :2]]
    for a, b in _oriented_boundary(faces2):
        la, lb = labels[a], labels[b]
        opening = la == lb and la != _SEAM
        if opening:
            continue
        _quad(faces, a, b, b + n, a + n)

    return verts, np.asarray(faces, dtype=np.int32)


def build_mesh(spacing: float | None = None, style: str = "tee") -> tuple[np.ndarray, np.ndarray]:
    """Single foldable panel."""
    return build_panel(DEFAULT_SPACING if spacing is None else spacing, style=style)


def build_shell(
    nx: int = DEFAULT_NX, ny: int = DEFAULT_NY, ns: int = DEFAULT_NS
) -> tuple[np.ndarray, np.ndarray]:
    spacing = BODY_W / max(int(nx) - 1, 1)
    return build_panel(spacing)


def boundary_loops(faces: np.ndarray) -> list[list[int]]:
    count: dict[tuple[int, int], int] = defaultdict(int)
    for a, b, c in faces:
        for u, v in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            e = (u, v) if u < v else (v, u)
            count[e] += 1
    adj: dict[int, list[int]] = defaultdict(list)
    for (u, v), n in count.items():
        if n == 1:
            adj[u].append(v)
            adj[v].append(u)
    seen: set[int] = set()
    loops: list[list[int]] = []
    for start in adj:
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        cur, prev = adj[start][0], start
        while cur != start:
            loop.append(cur)
            seen.add(cur)
            nxts = [w for w in adj[cur] if w != prev]
            if not nxts or len(loop) > len(adj) + 2:
                break
            prev, cur = cur, nxts[0]
        loops.append(loop)
    return loops


def validate_mesh(verts: np.ndarray, faces: np.ndarray, *, shell: bool) -> list[list[int]]:
    """One sheet, no non-manifold edges. Panel = 1 outline; shell = 4 openings."""
    count: dict[tuple[int, int], int] = defaultdict(int)
    for a, b, c in faces:
        for u, v in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            e = (u, v) if u < v else (v, u)
            count[e] += 1
    nonman = sum(1 for n in count.values() if n > 2)
    if nonman:
        raise RuntimeError(f"non-manifold edges: {nonman}")
    loops = boundary_loops(faces)
    if shell:
        if len(loops) != 4:
            raise RuntimeError(
                f"expected 4 boundary loop(s), got {len(loops)} "
                f"({', '.join(str(len(L)) for L in loops)})"
            )
    elif len(loops) < 1:
        raise RuntimeError("panel has no boundary")
    return loops


def planar_uvs(verts: np.ndarray, *, span: float | None = None) -> np.ndarray:
    """Map the T in metres onto the unit square, isotropic, collar at the top.

    Independent 0–1 axes would stretch a chest print: the panel is wider
    than it is tall (sleeves). Same metres-per-UV on both axes keeps α^x
    the shape it is in the PNG.
    """
    cx = 0.5 * (float(verts[:, 0].min()) + float(verts[:, 0].max()))
    cy = 0.5 * (float(verts[:, 1].min()) + float(verts[:, 1].max()))
    used = span if span and span > 1e-6 else max(
        float(np.ptp(verts[:, 0])), float(np.ptp(verts[:, 1])), 1e-6
    )
    u = (verts[:, 0] - cx) / used + 0.5
    # v=0 is the first PNG row. Collar (+Y) must sample the top of the print.
    v = (verts[:, 1] - cy) / used + 0.5
    return np.column_stack((u, v))


def outline_uv(style: str = "tee") -> list[list[float]]:
    """Closed garment silhouette in canvas space (u, v), collar at the top.

    ``planar_uvs`` is OpenGL-style (v up). This flips v so a 2D preview
    (y down) and a PNG bake line up with the cloth in MuJoCo.
    """
    poly = np.asarray(shirt_outline(style), dtype=np.float64)
    uv = planar_uvs(poly)
    return [[float(u), float(1.0 - v)] for u, v in uv]


def write_obj(
    path: Path,
    verts: np.ndarray,
    faces: np.ndarray,
    *,
    shell: bool = False,
    uvs: np.ndarray | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    loops = validate_mesh(verts, faces, shell=shell)
    kind = "hollow shell" if shell else "single T panel (ninja fold)"
    uv = planar_uvs(verts) if uvs is None else np.asarray(uvs, dtype=np.float64)
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# XFOLD {kind}\n")
        f.write(f"# verts={len(verts)} faces={len(faces)} loops={len(loops)}\n")
        f.write(
            f"# body={BODY_W:.2f}x{BODY_L:.2f} "
            f"crease_x=±{BODY_W / 6:.3f}\n"
        )
        for x, y, z in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for u, v in uv:
            f.write(f"vt {u:.6f} {v:.6f}\n")
        for a, b, c in faces:
            ia, ib, ic = a + 1, b + 1, c + 1
            f.write(f"f {ia}/{ia} {ib}/{ib} {ic}/{ic}\n")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--spacing", type=float, default=DEFAULT_SPACING)
    p.add_argument("--garment", default="tee", help="catalogue key (tee, tee_damaged, …)")
    p.add_argument("--all", action="store_true", help="Write every catalogue panel")
    p.add_argument("--depth", type=float, default=TORSO_D)
    p.add_argument(
        "--shell",
        action="store_true",
        help="Sew a hollow front+back T (wearable). Not the ninja-fold default.",
    )
    args = p.parse_args(argv)
    spacing = args.spacing
    if args.all:
        from xfold.garments import CATALOG

        seen: set[str] = set()
        for item in CATALOG.values():
            if item.mesh in seen or item.mesh == "shirt_t.obj":
                continue
            seen.add(item.mesh)
            verts, faces = build_panel(
                spacing, style=item.style, cuts=damage_cuts(item.key)
            )
            path = MODELS / item.mesh
            write_obj(path, verts, faces, shell=False)
            print(f"wrote {path}  verts={len(verts)}  faces={len(faces)}", flush=True)
        return
    if args.shell:
        verts, faces = build_sewn_t(spacing, depth=args.depth)
        write_obj(args.out, verts, faces, shell=True)
    else:
        from xfold.garments import resolve_garment

        item = resolve_garment(args.garment)
        out = args.out if args.out != DEFAULT_OUT else MODELS / item.mesh
        verts, faces = build_panel(
            spacing, style=item.style, cuts=damage_cuts(item.key)
        )
        write_obj(out, verts, faces, shell=False)
        args.out = out
    loops = boundary_loops(faces)
    span = verts.max(0) - verts.min(0)
    print(
        f"wrote {args.out}  verts={len(verts)}  faces={len(faces)}  "
        f"loops={len(loops)} ({', '.join(str(len(L)) for L in loops)})  "
        f"span={span[0]:.3f}×{span[1]:.3f}×{span[2]:.3f} m",
        flush=True,
    )


if __name__ == "__main__":
    main()
