"""T-shirt pattern for the two-claw ninja fold (SOLUTION.md §5.3).

Default output is a *single* T panel — the pressed sheet the clamps crease.
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
# Short-sleeve tee matching a classic crew silhouette (hanging set-in sleeves).
SLEEVE_L = 0.18
SLEEVE_H = 0.16
NECK_W = 0.20
NECK_D = 0.08
NECK_WRAP = 1.72
# Physics grid: ~410 verts at 3.2 cm stays near 60 fps (shirt.toml).
# The silhouette is snapped to the smooth outline, so this is not voxel stairs.
DEFAULT_SPACING = 0.032
HI_SPACING = 0.024
DEFAULT_NX = 22
DEFAULT_NY = 24
DEFAULT_NS = 6

LEFT_CREASE_X = -BODY_W / 6.0
RIGHT_CREASE_X = BODY_W / 6.0

_HEM, _NECK, _LCUFF, _RCUFF, _SEAM = "hem", "neck", "lcuff", "rcuff", "seam"


def _cubic(
    p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, n: int
) -> np.ndarray:
    """Open cubic Bezier from p0 to p3."""
    t = np.linspace(0.0, 1.0, n, endpoint=True)
    u = 1.0 - t
    p0, p1, p2, p3 = (np.asarray(p, dtype=np.float64) for p in (p0, p1, p2, p3))
    return (
        (u**3)[:, None] * p0
        + (3.0 * u**2 * t)[:, None] * p1
        + (3.0 * u * t**2)[:, None] * p2
        + (t**3)[:, None] * p3
    )


def shirt_outline() -> np.ndarray:
    """Closed short-sleeve tee, clockwise from the left neck.

    Classic crew silhouette: round collar, one-piece rounded shoulders,
    short sleeves that hang with a slanted cuff. Body width stays BODY_W
    so ninja thirds stay at ±body/6.
    """
    hw = 0.5 * BODY_W
    hl = 0.5 * BODY_L
    rx, ry = 0.5 * NECK_W, NECK_D
    beta = NECK_WRAP
    y_c = hl - 0.04
    x_join = float(rx * np.sin(beta))
    y_join = float(y_c - ry * np.cos(beta))

    # Set-in sleeve as a hanging parallelogram (axis ~20°), blunt cuff.
    ang = np.deg2rad(20.0)
    axis = np.array([-np.cos(ang), -np.sin(ang)])
    perp = np.array([np.sin(ang), -np.cos(ang)])  # toward underarm along the cuff
    y_arm_top = hl - 0.05
    y_arm_bot = y_arm_top - 0.20
    arm_top = np.array([-hw, y_arm_top])
    arm_bot = np.array([-hw, y_arm_bot])
    cuff_mid = 0.5 * (arm_top + arm_bot) + SLEEVE_L * axis
    cuff_half = 0.082
    cuff_top = cuff_mid - cuff_half * perp
    cuff_bot = cuff_mid + cuff_half * perp

    # Collar → high round shoulder → down the sleeve to the cuff.
    shoulder_sleeve = _cubic(
        (-x_join, y_join),
        (-x_join - 0.07, hl + 0.01),
        (-hw - 0.05, hl - 0.01),
        tuple(cuff_top),
        24,
    )
    cuff = _cubic(
        tuple(cuff_top),
        tuple(0.70 * cuff_top + 0.30 * cuff_bot + 0.004 * axis),
        tuple(0.30 * cuff_top + 0.70 * cuff_bot + 0.004 * axis),
        tuple(cuff_bot),
        10,
    )
    # Underarm rises into a small armpit fillet, like the reference tee.
    sleeve_bot = _cubic(
        tuple(cuff_bot),
        tuple(0.60 * cuff_bot + 0.40 * arm_bot + np.array([-0.02, -0.012])),
        tuple(arm_bot + np.array([-0.035, 0.012])),
        tuple(arm_bot),
        14,
    )
    side = _cubic(
        tuple(arm_bot),
        (-hw - 0.002, 0.04),
        (-hw + 0.008, -0.18),
        (-hw + 0.022, -hl + 0.025),
        12,
    )
    hem_l = _cubic(
        (-hw + 0.022, -hl + 0.025),
        (-hw + 0.05, -hl - 0.004),
        (-0.14, -hl - 0.02),
        (0.0, -hl - 0.022),
        12,
    )
    left = np.vstack([shoulder_sleeve[:-1], cuff[:-1], sleeve_bot[:-1], side[:-1], hem_l])
    right = left[::-1].copy()
    right[:, 0] *= -1.0

    t = np.linspace(beta, -beta, 41)
    neck = np.column_stack((rx * np.sin(t), y_c - ry * np.cos(t)))
    return np.vstack([left, right[1:], neck[1:-1]])


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


def _arclength_samples(poly: np.ndarray, n: int) -> np.ndarray:
    """n points around a closed polyline, starting at poly[0], equal arc length."""
    pts = np.vstack([poly, poly[0]]) if not np.allclose(poly[0], poly[-1]) else poly
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate(([0.0], np.cumsum(seg)))
    total = float(s[-1])
    t = (np.arange(n, dtype=np.float64) / max(n, 1)) * total
    k = np.clip(np.searchsorted(s, t, side="right") - 1, 0, len(seg) - 1)
    u = ((t - s[k]) / (seg[k] + 1e-18))[:, None]
    return pts[k] + u * (pts[k + 1] - pts[k])


def _snap_boundary_to_outline(
    verts: np.ndarray, faces: np.ndarray, poly: np.ndarray
) -> tuple[np.ndarray, list[int]]:
    """Move the raster silhouette onto the true T outline so the cloth looks like a tee."""
    loops = boundary_loops(faces)
    loop = max(loops, key=len)
    start = int(np.argmin(np.sum((verts[loop, :2] - poly[0]) ** 2, axis=1)))
    order = loop[start:] + loop[:start]
    want = poly[1] - poly[0]
    got = verts[order[1], :2] - verts[order[0], :2]
    if float(np.dot(want, got)) < 0.0:
        order = [order[0]] + order[:0:-1]
    samples = _arclength_samples(poly[:, :2], len(order))
    out = verts.copy()
    out[order, 0] = samples[:, 0]
    out[order, 1] = samples[:, 1]
    return out, order


def _relax_interior(verts: np.ndarray, faces: np.ndarray, boundary: list[int]) -> np.ndarray:
    """Laplacian-smooth interior verts so snapped edges do not leave sliver triangles."""
    n = len(verts)
    adj: list[set[int]] = [set() for _ in range(n)]
    for a, b, c in faces:
        ia, ib, ic = int(a), int(b), int(c)
        adj[ia].update((ib, ic))
        adj[ib].update((ia, ic))
        adj[ic].update((ia, ib))
    bound = np.zeros(n, dtype=bool)
    bound[list(boundary)] = True
    out = verts.copy()
    for _ in range(12):
        nxt = out.copy()
        for i in range(n):
            if bound[i] or not adj[i]:
                continue
            pts = out[list(adj[i]), :2]
            nxt[i, :2] = pts.mean(axis=0)
        out = nxt
    return out


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
    v = np.asarray(verts, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int32)
    v, boundary = _snap_boundary_to_outline(v, f, poly)
    v = _relax_interior(v, f, boundary)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (
        c[:, 0] - a[:, 0]
    )
    flip = area < 0.0
    if np.any(flip):
        f = f.copy()
        f[flip] = f[flip][:, (0, 2, 1)]
    return v, f


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
    if y >= ymax - 0.16 - pad and abs(x) <= 0.5 * NECK_W + 0.04:
        return _NECK
    # Neck bite sits inside the bounding box; catch the U as well.
    if y >= 0.5 * BODY_L - 0.16 - pad and abs(x) <= 0.5 * NECK_W + 0.04:
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
            if not nxts:
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
