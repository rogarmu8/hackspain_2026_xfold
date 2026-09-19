"""Generate a flat T-shirt surface mesh (OBJ) for MuJoCo flexcomp."""

from __future__ import annotations

from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[2] / "models" / "shirt_t.obj"

# Adult T silhouette in metres (XY plane, Z=0). Origin at torso centre.
SPACING = 0.045
X_SLEEVE = 0.36
X_TORSO = 0.17
Y_HEM = -0.32
Y_ARMPIT = 0.08
Y_SHOULDER = 0.32


def in_t_shirt(x: float, y: float) -> bool:
    """True if (x, y) lies on the T (torso + sleeve bar)."""
    sleeve_bar = (-X_SLEEVE <= x <= X_SLEEVE) and (Y_ARMPIT <= y <= Y_SHOULDER)
    torso = (-X_TORSO <= x <= X_TORSO) and (Y_HEM <= y <= Y_ARMPIT + 1e-9)
    return sleeve_bar or torso


def build_mesh(spacing: float = SPACING) -> tuple[np.ndarray, np.ndarray]:
    xs = np.arange(-X_SLEEVE, X_SLEEVE + 1e-9, spacing)
    ys = np.arange(Y_HEM, Y_SHOULDER + 1e-9, spacing)
    # Vertex grid; -1 = outside
    idx = -np.ones((len(ys), len(xs)), dtype=np.int32)
    verts: list[tuple[float, float, float]] = []
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            if in_t_shirt(float(x), float(y)):
                idx[j, i] = len(verts)
                verts.append((float(x), float(y), 0.0))

    faces: list[tuple[int, int, int]] = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            a, b = idx[j, i], idx[j, i + 1]
            c, d = idx[j + 1, i], idx[j + 1, i + 1]
            # two triangles if the quad is fully inside
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
        f.write("# XFOLD T-shirt surface (flat, with sleeves)\n")
        f.write(f"# verts={len(verts)} faces={len(faces)}\n")
        for x, y, z in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        # OBJ faces are 1-indexed
        for a, b, c in faces:
            f.write(f"f {a + 1} {b + 1} {c + 1}\n")


def main() -> None:
    verts, faces = build_mesh()
    write_obj(OUT, verts, faces)
    print(f"wrote {OUT}  verts={len(verts)}  faces={len(faces)}", flush=True)


if __name__ == "__main__":
    main()
