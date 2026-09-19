"""Bind a high-res T-shirt skin to the coarse flex physics mesh.

Research (ICARSC 2026, MuJoCo #1433 / docs): physics vertex count is a contact
budget, not a looks knob. Skins are visualisation-only and ride on the
per-vertex flex bodies (`shirt_0` …). That is the dual-mesh the jury paper
used in spirit: a garment outline in sim, a denser surface for the eye.

Also writes a matte knit texture — cube textures on flex render white
(MuJoCo #1457); skins take explicit UVs.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from xfold.generate_shirt_mesh import MODELS, build_mesh
from xfold.shirt import PLAYGROUND_XML, load_mujoco_plugins
from xfold.shirt_shot import write_png

DEFAULT_SKIN = MODELS / "shirt_skin.xml"
DEFAULT_TEX = MODELS / "shirt_knit.png"
VISUAL_SPACING = 0.018
K_BONES = 3
BACK_GAP = 0.0012


def _kabsch(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c_src, c_dst = src.mean(0), dst.mean(0)
    h = (src - c_src).T @ (dst - c_dst)
    u, _, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    if np.linalg.det(r) < 0:
        vt = vt.copy()
        vt[-1] *= -1
        r = vt.T @ u.T
    t = c_dst - r @ c_src
    return r, t


def _weights(fine: np.ndarray, coarse: np.ndarray, k: int = K_BONES):
    """Inverse-distance weights to the k nearest physics verts."""
    d = np.linalg.norm(fine[:, None, :] - coarse[None, :, :], axis=2)
    idx = np.argpartition(d, kth=k, axis=1)[:, :k]
    pick = np.take_along_axis(d, idx, axis=1)
    w = 1.0 / np.maximum(pick, 1e-5)
    w /= w.sum(axis=1, keepdims=True)
    return idx, w


def _knit_texture(path: Path, size: int = 256) -> None:
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:size, 0:size]
    base = np.array([46, 72, 102], dtype=np.float64)
    weave = 10 * np.sin(xx * 0.55) + 8 * np.sin(yy * 0.9)
    noise = rng.normal(0, 5, (size, size))
    rgb = np.clip(base + weave[..., None] + noise[..., None], 0, 255).astype(np.uint8)
    write_png(path, rgb)


def _fmt(vals: np.ndarray, nd: int = 5) -> str:
    return " ".join(f"{float(v):.{nd}f}" for v in np.asarray(vals).ravel())


def _fmt_int(vals) -> str:
    return " ".join(str(int(v)) for v in vals)


def write_skin(out: Path, model_xml: Path, visual_spacing: float) -> tuple[int, int]:
    import mujoco

    load_mujoco_plugins()
    model = mujoco.MjModel.from_xml_path(model_xml.as_posix())
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)

    nphys = int(model.nflexvert)
    bodies = [f"shirt_{i}" for i in range(nphys)]
    for name in bodies:
        if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) < 0:
            raise RuntimeError(f"missing flex body {name}")

    coarse = np.array([data.xpos[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, n)]
                       for n in bodies], dtype=np.float64)
    quats = np.array([data.xquat[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, n)]
                      for n in bodies], dtype=np.float64)

    # Physics OBJ as compiled — do not rebuild at a different spacing.
    from xfold.convert_cloth3d_mesh import load_obj

    obj_v, _obj_f = load_obj(MODELS / "shirt_t.obj")
    if len(obj_v) != nphys:
        raise RuntimeError(f"shirt_t.obj has {len(obj_v)} verts, model has {nphys}")
    r, t = _kabsch(obj_v, coarse)
    fine_v, fine_f = build_mesh(visual_spacing)
    fine_w = (r @ fine_v.T).T + t

    # Two-sided: skins are backface-culled (MuJoCo docs, deformable/skin).
    n0 = len(fine_w)
    normal = r @ np.array([0.0, 0.0, 1.0])
    back_w = fine_w - BACK_GAP * normal
    verts = np.vstack([fine_w, back_w])
    faces = np.vstack([fine_f, fine_f[:, ::-1] + n0])

    xmin, ymin = fine_v[:, 0].min(), fine_v[:, 1].min()
    span_x = max(float(np.ptp(fine_v[:, 0])), 1e-6)
    span_y = max(float(np.ptp(fine_v[:, 1])), 1e-6)
    uv_one = np.stack(
        [(fine_v[:, 0] - xmin) / span_x, (fine_v[:, 1] - ymin) / span_y], axis=1
    )
    uv = np.vstack([uv_one, uv_one])

    idx, w = _weights(np.vstack([fine_v, fine_v]), np.vstack([obj_v, obj_v]))
    # Use OBJ-space neighbours so front/back share the same bones.
    bone_verts: dict[int, list[int]] = defaultdict(list)
    bone_w: dict[int, list[float]] = defaultdict(list)
    for vi in range(len(verts)):
        for b, wt in zip(idx[vi], w[vi]):
            bone_verts[int(b)].append(vi)
            bone_w[int(b)].append(float(wt))

    tex_name = DEFAULT_TEX.name
    lines = [
        "<!-- Auto-generated dual-mesh skin. Do not edit; regenerate with",
        "     python -m xfold.generate_shirt_skin -->",
        "<mujoco>",
        "  <asset>",
        f'    <texture name="shirt_knit" type="2d" file="{tex_name}"/>',
        '    <material name="shirt_knit" texture="shirt_knit"',
        '              specular="0.02" shininess="0.01" reflectance="0"/>',
        "  </asset>",
        "  <deformable>",
        '    <skin name="shirt_visual" inflate="0.0008" material="shirt_knit"',
        f'          vertex="{_fmt(verts)}"',
        f'          texcoord="{_fmt(uv, 4)}"',
        f'          face="{_fmt_int(faces.ravel())}">',
    ]
    for b in range(nphys):
        if not bone_verts[b]:
            continue
        lines.append(
            f'      <bone body="{bodies[b]}" bindpos="{_fmt(coarse[b])}" '
            f'bindquat="{_fmt(quats[b], 4)}" '
            f'vertid="{_fmt_int(bone_verts[b])}" '
            f'vertweight="{_fmt(np.asarray(bone_w[b]), 4)}"/>'
        )
    lines += ["    </skin>", "  </deformable>", "</mujoco>", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return len(verts), int(faces.shape[0])


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--xml", type=Path, default=PLAYGROUND_XML)
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_SKIN)
    p.add_argument("--spacing", type=float, default=VISUAL_SPACING)
    args = p.parse_args(argv)
    _knit_texture(DEFAULT_TEX)
    nv, nf = write_skin(args.out, args.xml, args.spacing)
    print(f"wrote {args.out}  skin_verts={nv}  faces={nf}  tex={DEFAULT_TEX}", flush=True)


if __name__ == "__main__":
    main()
