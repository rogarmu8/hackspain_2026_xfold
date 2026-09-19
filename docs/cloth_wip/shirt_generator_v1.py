"""Shirt cloth module: flexcomp generator + material variants + runtime helpers.

Geometry is a planar point cloud on a regular grid clipped to an outline
(rectangle body, optional sleeves + neck notch), triangulated per retained cell.

Bending parameterization (hypothesis — validated by scripts/cloth_bench.py):
a thin plate has bending rigidity  B = E * t^3 / (12 * (1 - nu^2)).
With nu = 0 and thickness t = 1e-3 m,  young = 12 * B / t^3.
Presets target B (N*m): soft = 2e-5, medium = 1e-4, stiff = 5e-4.
Whether MuJoCo's internal bending scaling matches plate theory is measured,
not assumed.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

SIZE_PRESETS = {"S": (0.46, 0.66), "M": (0.50, 0.70), "L": (0.54, 0.74)}

# target plate bending rigidity B [N*m] per preset
_BENDING_PRESETS = {"soft": 2e-5, "medium": 1e-4, "stiff": 5e-4}

_THICKNESS = 1e-3
_SLEEVE_LEN = 0.20
_SLEEVE_H = 0.22
_SLEEVE_DROP = 0.06
_NECK_W = 0.16
_NECK_D = 0.04

# original model arrays saved on first set_steam so toggling is lossless
_steam_backup: dict[int, dict[str, np.ndarray]] = {}


@dataclass(frozen=True)
class ShirtParams:
    shape: Literal["rect", "tshirt"] = "rect"
    size: Literal["S", "M", "L"] = "M"
    spacing: float = 0.035
    radius: float = 0.004
    mass: float = 0.18
    model: Literal["constraint", "hybrid", "hybrid_vert", "fem"] = "hybrid"
    bending: Literal["soft", "medium", "stiff"] = "medium"
    friction: float = 1.0
    name: str = "shirt"
    rgba: tuple[float, float, float, float] = (0.15, 0.25, 0.55, 1.0)


def _young(params: ShirtParams) -> float:
    return 12.0 * _BENDING_PRESETS[params.bending] / _THICKNESS**3


def _outline(params: ShirtParams):
    """Return inside(x, y) predicate in shirt-local frame (x across, y along)."""
    w, length = SIZE_PRESETS[params.size]
    hw, hl = w / 2, length / 2

    if params.shape == "rect":
        def inside(x: float, y: float) -> bool:
            return -hw <= x <= hw and -hl <= y <= hl
        return inside, (hw, hl)

    sy0 = hl - _SLEEVE_DROP - _SLEEVE_H
    sy1 = hl - _SLEEVE_DROP
    nw, nd = _NECK_W / 2, _NECK_D

    def inside(x: float, y: float) -> bool:
        ax = abs(x)
        in_body = ax <= hw and -hl <= y <= hl
        in_sleeve = hw < ax <= hw + _SLEEVE_LEN and sy0 <= y <= sy1
        if not (in_body or in_sleeve):
            return False
        # neck notch cut from top edge of the body
        if ax <= nw and hl - nd <= y <= hl:
            return False
        return True

    return inside, (hw + _SLEEVE_LEN, hl)


def generate_grid(params: ShirtParams):
    """Planar grid clipped to the outline.

    Returns (points (n,3), tris (m,3) CCW, index_map (i,j)->vid, grid_shape).
    """
    inside, (hx, hy) = _outline(params)
    s = params.spacing
    nx = int(math.floor(2 * hx / s)) + 1
    ny = int(math.floor(2 * hy / s)) + 1
    x0 = -(nx - 1) * s / 2
    y0 = -(ny - 1) * s / 2

    def pt(i: int, j: int) -> tuple[float, float]:
        return x0 + i * s, y0 + j * s

    index_map: dict[tuple[int, int], int] = {}
    points: list[tuple[float, float, float]] = []
    tris: list[tuple[int, int, int]] = []

    def vid(i: int, j: int) -> int:
        key = (i, j)
        if key not in index_map:
            x, y = pt(i, j)
            index_map[key] = len(points)
            points.append((x, y, 0.0))
        return index_map[key]

    for j in range(ny - 1):
        for i in range(nx - 1):
            corners = [pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1)]
            if not all(inside(x, y) for x, y in corners):
                continue
            a, b, c, dd = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
            tris.append((a, b, c))
            tris.append((a, c, dd))

    return np.asarray(points), np.asarray(tris, dtype=int), index_map, (nx, ny)


def landmarks(params: ShirtParams) -> dict[str, int]:
    """Named vertex ids: corners (+edge midpoints for rect, sleeve tips for tshirt)."""
    points, _, index_map, _ = generate_grid(params)
    pts = points[:, :2]

    def nearest(x: float, y: float) -> int:
        return int(np.argmin((pts[:, 0] - x) ** 2 + (pts[:, 1] - y) ** 2))

    w, length = SIZE_PRESETS[params.size]
    hw, hl = w / 2, length / 2
    out = {
        "collar_left": nearest(-hw, hl),
        "collar_right": nearest(hw, hl),
        "hem_left": nearest(-hw, -hl),
        "hem_right": nearest(hw, -hl),
    }
    if params.shape == "tshirt":
        out["sleeve_left_tip"] = nearest(-(hw + _SLEEVE_LEN), hl - _SLEEVE_DROP - _SLEEVE_H / 2)
        out["sleeve_right_tip"] = nearest(hw + _SLEEVE_LEN, hl - _SLEEVE_DROP - _SLEEVE_H / 2)
    else:
        out["sleeve_left_tip"] = nearest(0.0, hl)   # top-edge midpoint
        out["sleeve_right_tip"] = nearest(0.0, -hl)  # bottom-edge midpoint
    return out


def vertex_body(params: ShirtParams, i: int) -> str:
    return f"{params.name}_{i}"


def _inner_xml(params: ShirtParams) -> str:
    f = params.friction
    if params.model == "constraint":
        return (
            f'<contact internal="false" selfcollide="auto" solref="0.005 1" '
            f'solimp=".9 .95 .001" friction="{f}"/>'
            f'<edge equality="true" damping="1"/>'
        )
    if params.model in ("hybrid", "hybrid_vert"):
        eq = "vert" if params.model == "hybrid_vert" else "true"
        return (
            f'<contact internal="false" selfcollide="auto" solref="0.005 1" '
            f'solimp=".9 .95 .001" friction="{f}"/>'
            f'<edge equality="{eq}" damping="0.1"/>'
            f'<elasticity young="{_young(params):.6g}" poisson="0" '
            f'thickness="{_THICKNESS}" elastic2d="bend" damping="0.02"/>'
        )
    if params.model == "fem":
        return (
            f'<contact internal="false" selfcollide="auto" solref="0.01 1" '
            f'solimp=".95 .99 .0001" friction="{f}"/>'
            f'<elasticity young="2e4" poisson="0.2" thickness="{_THICKNESS}" '
            f'elastic2d="both" damping="1e-2"/>'
        )
    raise ValueError(f"unknown model variant {params.model!r}")


def flexcomp_xml(
    params: ShirtParams,
    *,
    pos: tuple[float, float, float] = (0.0, 0.0, 0.3),
    yaw: float = 0.0,
) -> str:
    """Emit a <flexcomp type="direct"> element. Rest pose is planar; yaw only."""
    points, tris, _, _ = generate_grid(params)
    pt_str = " ".join(f"{x:.5f} {y:.5f} {z:.5f}" for x, y, z in points)
    el_str = " ".join(f"{a} {b} {c}" for a, b, c in tris)
    rgba = " ".join(f"{v:g}" for v in params.rgba)
    pos_s = " ".join(f"{v:g}" for v in pos)
    return (
        f'<flexcomp name="{params.name}" type="direct" dim="2" '
        f'point="{pt_str}" element="{el_str}" '
        f'radius="{params.radius}" mass="{params.mass}" '
        f'pos="{pos_s}" euler="0 0 {yaw:g}" rgba="{rgba}">'
        f"{_inner_xml(params)}"
        f"</flexcomp>"
    )


def required_option(params: ShirtParams) -> dict[str, str]:
    if params.model == "constraint":
        return {"integrator": "implicitfast", "solver": "CG", "tolerance": "1e-6"}
    return {
        "integrator": "discrete",
        "solver": "CG",
        "tolerance": "1e-6",
        "iterations": "200",
    }


def check_model_option(model, params: ShirtParams) -> None:
    import mujoco

    want = required_option(params)["integrator"]
    have = mujoco.mjtIntegrator(model.opt.integrator).name.lower().removeprefix("mjint_")
    if have != want:
        raise ValueError(
            f"variant {params.model!r} needs integrator={want} "
            f"(required_option()), model has integrator={have}"
        )


def _flexid(model, name: str) -> int:
    import mujoco

    fid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, name)
    if fid < 0:
        raise ValueError(f"no flex named {name!r}")
    return fid


def vertices(model, data, name: str) -> np.ndarray:
    fid = _flexid(model, name)
    adr, num = int(model.flex_vertadr[fid]), int(model.flex_vertnum[fid])
    return data.flexvert_xpos[adr : adr + num].copy()


def flatness(model, data, name: str) -> float:
    return float(vertices(model, data, name)[:, 2].std())


def span_xy(model, data, name: str) -> np.ndarray:
    return np.ptp(vertices(model, data, name)[:, :2], axis=0)


def rest_span(params: ShirtParams) -> np.ndarray:
    points, _, _, _ = generate_grid(params)
    return np.ptp(points[:, :2], axis=0)


def span_ratio(model, data, params: ShirtParams) -> float:
    cur = span_xy(model, data, params.name)
    ref = rest_span(params)
    return float(np.linalg.norm(cur) / np.linalg.norm(ref))


def aabb(model, data, name: str) -> tuple[np.ndarray, np.ndarray]:
    v = vertices(model, data, name)
    return v.min(axis=0), v.max(axis=0)


def top_layer_vertices(model, data, params: ShirtParams, bed_top: float) -> np.ndarray:
    v = vertices(model, data, params.name)
    return v[v[:, 2] > bed_top + 3 * params.radius]


def set_steam(model, data, params: ShirtParams, on: bool) -> None:
    """Soften/restore the shirt (steam). Scales compiled model arrays.

    mjModel has no flex_young in MuJoCo 3.13: elasticity compiles into
    per-element flex_stiffness (stretch/shear) and per-edge flex_bending,
    with per-flex flex_damping / flex_edgedamping scalars. Those arrays are
    consumed directly by the solver each step, so editing them takes effect
    without mj_setConst (verified empirically in cloth_bench dev).
    """
    fid = _flexid(model, params.name)
    key = id(model)
    if key not in _steam_backup:
        _steam_backup[key] = {
            "stiffness": model.flex_stiffness.copy(),
            "bending": model.flex_bending.copy(),
            "damping": model.flex_damping.copy(),
            "edgedamping": model.flex_edgedamping.copy(),
        }
    b = _steam_backup[key]
    scale = 0.05 if on else 1.0
    sadr, send = int(model.flex_stiffnessadr[fid]), (
        int(model.flex_stiffnessadr[fid + 1])
        if fid + 1 < model.nflex
        else model.flex_stiffness.shape[0]
    )
    badr, bend = int(model.flex_bendingadr[fid]), (
        int(model.flex_bendingadr[fid + 1])
        if fid + 1 < model.nflex
        else model.flex_bending.shape[0]
    )
    model.flex_stiffness[sadr:send] = b["stiffness"][sadr:send] * scale
    model.flex_bending[badr:bend] = b["bending"][badr:bend] * scale
    if params.model == "constraint":
        model.flex_edgedamping[fid] = b["edgedamping"][fid] * (10.0 if on else 1.0)
    else:
        model.flex_damping[fid] = b["damping"][fid] * (10.0 if on else 1.0)


def tiled_surface_xml(
    name: str,
    center: tuple[float, float, float],
    half_xy: tuple[float, float],
    top_z: float,
    half_z: float,
    tiles: tuple[int, int] = (4, 5),
    friction: float = 1.0,
    rgba: tuple[float, float, float, float] = (0.55, 0.55, 0.58, 1.0),
) -> str:
    """Support surface as a grid of THICK box geoms, ONE <body> PER TILE.

    engine_collision_driver.c::filterFlexContacts keeps at most
    mjMAXCONPAIR (50) contacts per (body, flex) pair — per BODY, not per
    geom. Geoms sharing a body share one 50-contact budget, so a surface
    must be split into one <body> per tile (~50 contact points per tile at
    35 mm spacing -> tile size ~0.14-0.15 m). Tiles may touch; no overlap
    or stagger needed.

    Emits `<body name="{name}_{i}_{j}">` children — nest inside a parent
    body (e.g. under a slide joint) or in worldbody.
    """
    hx, hy = half_xy
    tx, ty = tiles
    sx, sy = hx / tx, hy / ty
    cx, cy, cz = center
    rgba_s = " ".join(f"{v:g}" for v in rgba)
    out = []
    for i in range(tx):
        for j in range(ty):
            x = cx - hx + sx * (2 * i + 1)
            y = cy - hy + sy * (2 * j + 1)
            out.append(
                f'<body name="{name}_{i}_{j}" pos="{x:.4f} {y:.4f} {top_z - half_z + cz:.4f}">'
                f'<geom type="box" size="{sx:.4f} {sy:.4f} {half_z}" '
                f'rgba="{rgba_s}" friction="{friction}"/>'
                f"</body>"
            )
    return "\n    ".join(out)


def write_file(params: ShirtParams, path: str, *, pos=(0.0, 0.0, 0.3), yaw: float = 0.0) -> None:
    """Write an include-ready file: <mujoco> wrapper whose children splice in."""
    body = flexcomp_xml(params, pos=pos, yaw=yaw)
    with open(path, "w") as fh:
        fh.write(f"<mujoco>\n  {body}\n</mujoco>\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a shirt flexcomp MJCF fragment")
    p.add_argument("--write", required=True, help="output path (include fragment)")
    p.add_argument("--shape", choices=["rect", "tshirt"], default="rect")
    p.add_argument("--size", choices=["S", "M", "L"], default="M")
    p.add_argument("--model", choices=["constraint", "hybrid", "hybrid_vert", "fem"], default="hybrid")
    p.add_argument("--bending", choices=["soft", "medium", "stiff"], default="medium")
    p.add_argument("--spacing", type=float, default=0.035)
    p.add_argument("--radius", type=float, default=0.004)
    p.add_argument("--mass", type=float, default=0.18)
    p.add_argument("--friction", type=float, default=1.0)
    p.add_argument("--name", default="shirt")
    p.add_argument("--pos", nargs=3, type=float, default=[0.0, 0.0, 0.3])
    p.add_argument("--yaw", type=float, default=0.0)
    a = p.parse_args()
    params = ShirtParams(
        shape=a.shape, size=a.size, spacing=a.spacing, radius=a.radius,
        mass=a.mass, model=a.model, bending=a.bending, friction=a.friction,
        name=a.name,
    )
    write_file(params, a.write, pos=tuple(a.pos), yaw=a.yaw)
    pts, tris, _, _ = generate_grid(params)
    print(f"wrote {a.write}: {len(pts)} vertices, {len(tris)} elements, "
          f"variant={params.model}, option={required_option(params)}")


if __name__ == "__main__":
    main()
