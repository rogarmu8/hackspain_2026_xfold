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

LEFT_CREASE_X = -BODY_W / 6.0
RIGHT_CREASE_X = BODY_W / 6.0

_HEM, _NECK, _LCUFF, _RCUFF, _SEAM = "hem", "neck", "lcuff", "rcuff", "seam"


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


def shirt_outline() -> np.ndarray:
    """Closed classic crew-neck T, clockwise from the left neck.

    Iconic front-view tee: circular collar, nearly level shoulders, short
    sleeves that hang with rounded cuffs, straight sides, stadium hem.
    One loop (U-neck, not a hole) so the sheet stays foldable.
    """
    hw = 0.5 * BODY_W
    hl = 0.5 * BODY_L
    neck_cy = hl - 0.015
    neck_rx, neck_ry = 0.5 * NECK_W, NECK_D
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
        (-hw - SLEEVE_L + 0.03, hl - 0.11),
        7,
    )
    cuff = _arc(
        -hw - SLEEVE_L + 0.05,
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
        (-hw, hl - SLEEVE_H),
        6,
    )
    # Straight torso, then a stadium hem (rounded-rect, not a bag).
    side = _bezier(
        to_armpit[-1],
        (-hw, 0.02),
        (-hw, -hl + 0.18),
        (-hw, -hl + 0.08),
        8,
    )
    hem_r = 0.085
    hem = _arc(-hw + hem_r, -hl + hem_r, hem_r, hem_r, np.pi, 1.5 * np.pi, 10)
    hem = np.vstack([hem, np.array([[0.0, -hl]], dtype=np.float64)])

    left = _join(shoulder, sleeve_top, cuff, to_armpit, side, hem)
    right = left[-2:0:-1].copy()
    right[:, 0] *= -1.0
    neck = _arc(0.0, neck_cy, neck_rx, neck_ry, a_right, a_left, 18)
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
    verts: np.ndarray, faces: np.ndarray, poly: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Project the grid silhouette onto the nearest T-outline point."""
    loops = boundary_loops(faces)
    if len(loops) != 1:
        return verts, faces
    out = verts.copy()
    for index in loops[0]:
        out[index, :2] = _closest_on_poly(out[index, :2], poly)

    keep: list[tuple[int, int, int]] = []
    for face in faces:
        tri = out[face]
        if _signed_area(tri[:, :2]) < 1e-10:
            continue
        c = tri.mean(axis=0)
        if _point_in_poly(float(c[0]), float(c[1]), poly):
            keep.append((int(face[0]), int(face[1]), int(face[2])))
    if not keep:
        return verts, faces
    faces2 = np.asarray(keep, dtype=np.int32)
    fitted_v, fitted_f = _remap_used(out, faces2)
    if len(boundary_loops(fitted_f)) == 1:
        return fitted_v, fitted_f
    # Projection without culling still hugs the sleeves / hem.
    return out, faces


def build_panel(spacing: float) -> tuple[np.ndarray, np.ndarray]:
    """One T-shaped 2D panel (z = 0) from the sewing pattern."""
    poly = shirt_outline()
    pad = 0.5 * spacing
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
        raise RuntimeError("T-shirt panel is empty — check silhouette bounds")
    mesh_v = np.asarray(verts, dtype=np.float64)
    mesh_f = np.asarray(faces, dtype=np.int32)
    fitted_v, fitted_f = _fit_boundary(mesh_v, mesh_f, poly)
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


def build_mesh(spacing: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Single T panel — the foldable sheet."""
    return build_panel(DEFAULT_SPACING if spacing is None else spacing)


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
    expect = 4 if shell else 1
    if len(loops) != expect:
        raise RuntimeError(
            f"expected {expect} boundary loop(s), got {len(loops)} "
            f"({', '.join(str(len(L)) for L in loops)})"
        )
    return loops


def write_obj(path: Path, verts: np.ndarray, faces: np.ndarray, *, shell: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    loops = validate_mesh(verts, faces, shell=shell)
    kind = "hollow shell" if shell else "single T panel (ninja fold)"
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# XFOLD {kind}\n")
        f.write(f"# verts={len(verts)} faces={len(faces)} loops={len(loops)}\n")
        f.write(
            f"# body={BODY_W:.2f}x{BODY_L:.2f} "
            f"crease_x=±{BODY_W / 6:.3f}\n"
        )
        for x, y, z in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            f.write(f"f {a + 1} {b + 1} {c + 1}\n")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--spacing", type=float, default=DEFAULT_SPACING)
    p.add_argument("--nx", type=int, default=None)
    p.add_argument("--ny", type=int, default=None)
    p.add_argument("--ns", type=int, default=None)
    p.add_argument("--depth", type=float, default=TORSO_D)
    p.add_argument(
        "--shell",
        action="store_true",
        help="Sew a hollow front+back T (wearable). Not the ninja-fold default.",
    )
    args = p.parse_args(argv)
    spacing = args.spacing
    if args.nx:
        spacing = BODY_W / max(int(args.nx) - 1, 1)
    if args.shell:
        verts, faces = build_sewn_t(spacing, depth=args.depth)
    else:
        verts, faces = build_panel(spacing)
    write_obj(args.out, verts, faces, shell=args.shell)
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
