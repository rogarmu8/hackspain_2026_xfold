"""Convert a CLOTH3D / ClothesNet flat garment OBJ into a MuJoCo-ready surface.

Pipeline: load → drop thin axis into Z → centre → target width → spatial
decimate → rewrite clean triangles. Keeps topology by remapping faces; drops
degenerate triangles after welding.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

MODELS = Path(__file__).resolve().parents[2] / "models"
DEFAULT_OUT = MODELS / "shirt_cloth3d.obj"
# Target edge length. ~2 cm keeps folds readable without tanking the solver.
DEFAULT_SPACING = 0.022
DEFAULT_WIDTH = 0.70  # metres across sleeves


def load_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    verts: list[list[float]] = []
    faces: list[tuple[int, int, int]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("v "):
            parts = line.split()
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            ids: list[int] = []
            for tok in line.split()[1:]:
                ids.append(int(tok.split("/")[0]) - 1)
            if len(ids) < 3:
                continue
            for i in range(1, len(ids) - 1):
                faces.append((ids[0], ids[i], ids[i + 1]))
    if not verts or not faces:
        raise ValueError(f"empty mesh: {path}")
    return np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int32)


def to_thin_axis_z(verts: np.ndarray) -> np.ndarray:
    """Rotate so the thinnest bbox axis becomes +Z (garment lies on XY)."""
    bb = verts.max(axis=0) - verts.min(axis=0)
    thin = int(np.argmin(bb))
    if thin == 0:  # X thin → (Y, Z, X)
        return verts[:, [1, 2, 0]]
    if thin == 1:  # Y thin → (X, Z, Y)  — CLOTH3D flat shirts
        return verts[:, [0, 2, 1]]
    return verts.copy()


def keep_front_layer(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Drop the back panel of the garment.

    CLOTH3D shirts are closed tubes. Flattening both panels onto one plane
    welds front to back and produces non-manifold edges, which flexcomp
    renders as a mess. Faces whose normal points +Z are the front layer.
    """
    a = verts[faces[:, 1]] - verts[faces[:, 0]]
    b = verts[faces[:, 2]] - verts[faces[:, 0]]
    normal_z = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    front = faces[normal_z > 0]
    if len(front) < len(faces) * 0.2:
        raise RuntimeError("front-layer split failed; check the source mesh")
    return front


def flatten(verts: np.ndarray) -> np.ndarray:
    """Collapse residual thickness so flexcomp sees a true surface."""
    out = verts.copy()
    out[:, 2] = 0.0
    return out


def centre_and_scale(verts: np.ndarray, target_width: float) -> np.ndarray:
    v = verts - verts.mean(axis=0)
    width = float(max(np.ptp(v[:, 0]), np.ptp(v[:, 1]), 1e-9))
    return v * (target_width / width)


def drop_unused_verts(
    verts: np.ndarray, faces: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Compact vertices; stray points would become free-falling flex nodes."""
    used = np.unique(faces)
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return verts[used], remap[faces]


def decimate(
    verts: np.ndarray, faces: np.ndarray, spacing: float
) -> tuple[np.ndarray, np.ndarray]:
    """Weld vertices into a spacing grid and remap triangles."""
    keys = np.ascontiguousarray(np.floor(verts / spacing).astype(np.int64))
    # pack XYZ cell coords into a comparable structured key
    packed = np.empty(len(keys), dtype=[("x", np.int64), ("y", np.int64), ("z", np.int64)])
    packed["x"], packed["y"], packed["z"] = keys[:, 0], keys[:, 1], keys[:, 2]
    _, first, inv = np.unique(packed, return_index=True, return_inverse=True)
    new_verts = verts[first]
    # average verts that fell in the same cell for a smoother surface
    accum = np.zeros_like(new_verts)
    counts = np.zeros(len(new_verts), dtype=np.float64)
    np.add.at(accum, inv, verts)
    np.add.at(counts, inv, 1.0)
    new_verts = accum / counts[:, None]
    new_verts[:, 2] = 0.0

    remapped = inv[faces]
    keep = (
        (remapped[:, 0] != remapped[:, 1])
        & (remapped[:, 1] != remapped[:, 2])
        & (remapped[:, 0] != remapped[:, 2])
    )
    new_faces = remapped[keep]
    # drop duplicate faces
    ordered = np.sort(new_faces, axis=1)
    _, uniq = np.unique(ordered, axis=0, return_index=True)
    new_faces = new_faces[np.sort(uniq)]
    if len(new_verts) < 20 or len(new_faces) < 20:
        raise RuntimeError(
            f"decimation too aggressive: verts={len(new_verts)} faces={len(new_faces)}"
        )
    return new_verts, new_faces


def orient_faces(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Wind every triangle CCW seen from +Z.

    The sheet is flat in XY, so a consistent winding is just a sign test.
    Mixed winding is what renders half the shirt as black triangles.
    """
    a = verts[faces[:, 1]] - verts[faces[:, 0]]
    b = verts[faces[:, 2]] - verts[faces[:, 0]]
    cross_z = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    flipped = faces.copy()
    cw = cross_z < 0
    flipped[cw, 1], flipped[cw, 2] = faces[cw, 2], faces[cw, 1]
    return flipped[np.abs(cross_z) > 1e-12]


def write_obj(path: Path, verts: np.ndarray, faces: np.ndarray, note: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# XFOLD MuJoCo shirt surface from CLOTH3D ({note})\n")
        f.write(f"# verts={len(verts)} faces={len(faces)}\n")
        for x, y, z in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            f.write(f"f {a + 1} {b + 1} {c + 1}\n")


def convert(
    src: Path,
    out: Path = DEFAULT_OUT,
    spacing: float = DEFAULT_SPACING,
    width: float = DEFAULT_WIDTH,
) -> tuple[int, int]:
    verts, faces = load_obj(src)
    verts = to_thin_axis_z(verts)
    faces = keep_front_layer(verts, faces)
    verts, faces = drop_unused_verts(verts, faces)
    verts = flatten(verts)
    verts = centre_and_scale(verts, width)
    verts, faces = decimate(verts, faces, spacing)
    verts, faces = drop_unused_verts(verts, faces)
    faces = orient_faces(verts, faces)
    write_obj(out, verts, faces, note=src.name)
    return len(verts), len(faces)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("src", type=Path, help="Source flat garment OBJ (CLOTH3D / ClothesNet)")
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--spacing", type=float, default=DEFAULT_SPACING)
    p.add_argument("--width", type=float, default=DEFAULT_WIDTH)
    args = p.parse_args()
    nv, nf = convert(args.src, args.out, args.spacing, args.width)
    print(f"wrote {args.out}  verts={nv}  faces={nf}", flush=True)


if __name__ == "__main__":
    main()
