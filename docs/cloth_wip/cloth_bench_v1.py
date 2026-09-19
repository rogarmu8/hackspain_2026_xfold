#!/usr/bin/env python
"""Cloth stability + task benchmark for xfold shirt variants (v2).

Run from repo root:  pixi run -e mujoco python -P scripts/cloth_bench.py [args]

Two scenarios per (variant, shape, seed), each on a fresh MjData:
  PRESS  settle flat -> crumple (mocap hand lifts an interior vertex, shakes,
         drops) -> force-limited platen press. Metrics: flatness pre/post,
         penetration, settle vmax, rt_factor.
  FOLD   settle flat -> two mocap hands weld the hem corners and lay the hem
         over the collar on a semicircular arc. Metrics: span ratio, second-
         layer fraction, overlap.
Support surfaces = thick tiles, ONE <body> per tile (mjMAXCONPAIR is per
body-flex pair). PNGs: {variant}_{shape}_{seed}_{stage}_{top|side}.png.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import time
from pathlib import Path

import mujoco
import numpy as np

from xfold.shirt import (
    ShirtParams,
    flexcomp_xml,
    generate_grid,
    landmarks,
    required_option,
    span_ratio,
    tiled_surface_xml,
    vertex_body,
    vertices,
)

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "cloth_bench"

BED_TOP = 0.095
BED_HZ = 0.06
BED_HX, BED_HY = 0.45, 0.55  # 0.9 x 1.1 m bed, contains the shirt at any yaw
# Contact budget is mjMAXCONPAIR=50 per (BODY, flex) pair — per body, not
# per geom. Support surfaces must be one <body> per thick tile (~0.15 m).
BED_TILES = (6, 8)
PLATEN_HZ = 0.05
PLATEN_Z0 = 0.6
PRESS_GAP_MULT = 1.5  # platen bottom stops at bed_top + 1.5*(2*radius)
DROP_Z = 0.12

SCENE = """
<mujoco>
  <option timestep="0.002" {option}/>
  <size memory="400M"/>
  <visual>
    <global offwidth="960" offheight="540"/>
    <headlight diffuse="0.6 0.6 0.6" ambient="0.25 0.25 0.25"/>
  </visual>
  <worldbody>
    <light pos="0 0 2" dir="0 0 -1"/>
    <geom name="floor" type="plane" size="2 2 .1" rgba=".18 .18 .2 1"/>
    <body name="lookat" pos="0 0 0.1" mocap="true"/>
    <camera name="bench_top" pos="0 0 1.35" xyaxes="1 0 0 0 1 0"/>
    <camera name="bench_side" pos="-1.1 -0.8 0.40" mode="targetbody" target="lookat"/>
    {bed_tiles}
    <body name="platen" pos="0 0 0">
      <joint name="platen_z" type="slide" axis="0 0 1" range="{ctrl_lo} {ctrl_hi}"/>
      {platen_tiles}
    </body>
    <body name="hand_a" mocap="true" pos="0 0 2">
      <geom type="sphere" size="0.012" rgba="1 0 0 1" contype="0" conaffinity="0"/>
    </body>
    <body name="hand_b" mocap="true" pos="0 0 2">
      <geom type="sphere" size="0.012" rgba="0 1 0 1" contype="0" conaffinity="0"/>
    </body>
    {flexcomp}
  </worldbody>
  <equality>
    <weld name="grasp_a" body1="hand_a" body2="{weld_body}" active="false" solref="0.005 1"/>
    <weld name="grasp_b" body1="hand_b" body2="{weld_body}" active="false" solref="0.005 1"/>
  </equality>
  <actuator>
    <position name="platen_ctl" joint="platen_z" kp="2000"
              forcerange="-60 60" ctrlrange="{ctrl_lo} {ctrl_hi}"/>
  </actuator>
</mujoco>
"""


def build_scene(params: ShirtParams, yaw: float, iterations: int):
    opt = dict(required_option(params))
    if "iterations" in opt:
        opt["iterations"] = str(iterations)
    opt_s = " ".join(f'{k}="{v}"' for k, v in opt.items())
    platen_lo = BED_TOP + PLATEN_HZ + PRESS_GAP_MULT * (2 * params.radius)
    xml = SCENE.format(
        option=opt_s,
        ctrl_lo=platen_lo,
        ctrl_hi=PLATEN_Z0,
        bed_tiles=tiled_surface_xml(
            "bed", (0, 0, 0), (BED_HX, BED_HY), BED_TOP, BED_HZ,
            tiles=BED_TILES, friction=1.0, rgba=(0.55, 0.55, 0.58, 1)),
        platen_tiles=tiled_surface_xml(
            "platen", (0, 0, 0), (BED_HX, BED_HY), PLATEN_HZ, PLATEN_HZ,
            tiles=BED_TILES, friction=0.6, rgba=(0.45, 0.45, 0.5, 0.25)),
        flexcomp=flexcomp_xml(params, pos=(0, 0, DROP_Z), yaw=yaw),
        weld_body=vertex_body(params, 0),
    )
    return xml, platen_lo


def shirt_dofadr(model, name: str) -> np.ndarray:
    fid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, name)
    bids = model.flex_vertbodyid[model.flex_vertadr[fid]:
                               model.flex_vertadr[fid] + model.flex_vertnum[fid]]
    adrs = []
    for b in bids:
        adrs.extend(range(int(model.body_dofadr[b]),
                          int(model.body_dofadr[b]) + int(model.body_dofnum[b])))
    return np.asarray(adrs)


class Runner:
    """Step driver with warning/finiteness checks and contact tracking."""

    def __init__(self, model, data):
        self.m, self.d = model, data
        self.ncon_max = 0
        self.diverged = False

    def run(self, seconds, cb=None):
        n = int(seconds / self.m.opt.timestep)
        for _ in range(n):
            if cb:
                cb(self.d.time)
            mujoco.mj_step(self.m, self.d)
            self.ncon_max = max(self.ncon_max, self.d.ncon)
            if self.d.warning.number.sum() or not np.isfinite(self.d.qpos).all():
                self.diverged = True
                return


def make_data(model, platen_z0=PLATEN_Z0):
    d = mujoco.MjData(model)
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "platen_z")
    d.qpos[model.jnt_qposadr[jid]] = platen_z0
    d.ctrl[0] = platen_z0
    mujoco.mj_forward(model, d)
    return d


def weld_to(model, data, weld_name: str, hand_name: str, vert_body_id: int):
    wid = model.equality(weld_name).id
    model.eq_obj2id[wid] = int(vert_body_id)
    # weld relpose is stored at compile time for the ORIGINAL body2; after
    # retargeting we want an identity relative pose (vertex pinned to hand)
    model.eq_data[wid, :] = 0.0
    model.eq_data[wid, 6] = 1.0  # relpose quaternion w
    mocap = model.body(hand_name).mocapid[0]
    return wid, mocap


def vert_body_id(model, params: ShirtParams, i: int) -> int:
    return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY,
                             vertex_body(params, i))


def interior_vertex(params: ShirtParams, rng) -> int:
    """Random vertex id ≥2 grid cells inside the outline."""
    _, _, index_map, (nx, ny) = generate_grid(params)
    inner = [v for (i, j), v in index_map.items()
           if 2 <= i <= nx - 3 and 2 <= j <= ny - 3]
    return int(rng.choice(inner))


def png(model, data, out_dir, tag, stage):
    r = mujoco.Renderer(model, 360, 640)
    for cam in ("top", "side"):
        r.update_scene(data, camera=f"bench_{cam}")
        from PIL import Image
        Image.fromarray(r.render()).save(
            out_dir / f"{tag}_{stage}_{cam}.png")
    r.close()


def scenario_press(model, params, rng, yaw, platen_lo, out_dir, tag):
    """flat -> crumple -> press. Returns metrics dict."""
    m = model
    d = make_data(m)
    r = Runner(m, d)
    name = params.name
    dofs = shirt_dofadr(m, name)
    hand = m.body("hand_a").mocapid[0]
    wid, _ = weld_to(m, d, "grasp_a", "hand_a", 0)
    pa = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, "platen_ctl")
    jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "platen_z")
    t_wall0 = time.perf_counter()

    # 1) settle flat
    r.run(1.0)
    flat_flat = float(vertices(m, d, name)[:, 2].std())
    png(m, d, out_dir, tag, "flat")

    # 2) crumple: weld an interior vertex, lift, shake, release
    grab = interior_vertex(params, rng)
    m.eq_obj2id[wid] = vert_body_id(m, params, grab)
    v = vertices(m, d, name)
    d.mocap_pos[hand] = v[grab]
    mujoco.mj_forward(m, d)
    d.eq_active[wid] = 1
    p0 = v[grab].copy()
    p_up = p0.copy(); p_up[2] = BED_TOP + 0.30
    t0 = d.time
    r.run(0.6, lambda t: d.mocap_pos.__setitem__(
        hand, p0 + np.clip((t - t0) / 0.6, 0, 1) * (p_up - p0)))
    jitter = rng.uniform(-0.10, 0.10, 2)
    t1 = d.time
    r.run(0.4, lambda t: d.mocap_pos.__setitem__(
        hand, p_up + np.array([jitter[0], jitter[1], 0])
        * np.sin(2 * np.pi * 4 * (t - t1))))
    d.eq_active[wid] = 0
    r.run(2.0)
    v = vertices(m, d, name)
    flat_pre = float(v[:, 2].std())
    span_pre = span_ratio(m, d, params)
    settle_vmax = float(np.abs(d.qvel[dofs]).max())
    stable = (not r.diverged) and settle_vmax < 0.05
    png(m, d, out_dir, tag, "crumpled")

    # 3) press
    t2 = d.time
    r.run(0.8, lambda t: d.ctrl.__setitem__(
        pa, PLATEN_Z0 - np.clip((t - t2) / 0.8, 0, 1) * (PLATEN_Z0 - platen_lo)))
    r.run(1.0)
    t3 = d.time
    r.run(0.5, lambda t: d.ctrl.__setitem__(
        pa, platen_lo + np.clip((t - t3) / 0.5, 0, 1) * (PLATEN_Z0 - platen_lo)))
    r.run(0.5)
    v = vertices(m, d, name)
    flat_post = float(v[:, 2].std())
    span_post = span_ratio(m, d, params)
    inside = v[(np.abs(v[:, 0]) < BED_HX) & (np.abs(v[:, 1]) < BED_HY)]
    penetration = float(inside[:, 2].min() - (BED_TOP + params.radius)) \
        if len(inside) else float("nan")
    png(m, d, out_dir, tag, "pressed")

    wall = time.perf_counter() - t_wall0
    return {
        "flatness_flat": round(flat_flat, 4),
        "flatness_pre": round(flat_pre, 4),
        "flatness_post": round(flat_post, 4),
        "press_gain": round(flat_post / max(flat_pre, 1e-9), 3),
        "span_ratio_pre": round(span_pre, 3),
        "span_ratio_post": round(span_post, 3),
        "penetration_post": round(penetration, 4),
        "settle_vmax": round(settle_vmax, 4),
        "stable": int(stable),
        "diverged": int(r.diverged),
        "ncon_max": r.ncon_max,
        "rt_factor": round(d.time / wall, 3),
    }


def scenario_fold(model, params, rng, out_dir, tag):
    """flat -> two-hand hem-to-collar half fold. Returns metrics dict."""
    m = model
    d = make_data(m)
    r = Runner(m, d)
    name = params.name

    # 1) settle flat (yaw 0)
    r.run(1.0)
    lm = landmarks(params)
    v = vertices(m, d, name)
    span_pre_y = float(np.ptp(v[:, 1]))
    v_start = v.copy()
    moved_mask = v_start[:, 1] < np.median(v_start[:, 1])  # hem half
    png(m, d, out_dir, tag, "fold_flat")

    # 2) weld both hem corners
    grabs = [lm["hem_left"], lm["hem_right"]]
    hands = [m.body("hand_a").mocapid[0], m.body("hand_b").mocapid[0]]
    wids = []
    p0s = []
    for wname, hname, g in (("grasp_a", "hand_a", grabs[0]),
                          ("grasp_b", "hand_b", grabs[1])):
        wid, mp = weld_to(m, d, wname, hname, vert_body_id(m, params, g))
        d.mocap_pos[mp] = v[g]
        wids.append(wid); p0s.append(v[g].copy())
    mujoco.mj_forward(m, d)
    for wid in wids:
        d.eq_active[wid] = 1

    # lift
    p_ups = [p.copy() + np.array([0, 0, BED_TOP + 0.12 - p[2]]) for p in p0s]
    t0 = d.time
    def lift(t):
        u = np.clip((t - t0) / 0.5, 0, 1)
        for mp, a, b in zip(hands, p0s, p_ups):
            d.mocap_pos[mp] = a + u * (b - a)
    r.run(0.5, lift)

    # semicircular arc in the y-z plane, hem -> just short of collar
    collar_y = float(v[lm["collar_left"], 1])
    ends = [np.array([p[0], collar_y - 0.02, BED_TOP + 0.02]) for p in p_ups]
    centers = [(a + b) / 2 for a, b in zip(p_ups, ends)]
    radii = [np.linalg.norm(b - a) / 2 for a, b in zip(p_ups, ends)]
    u0s = [np.arctan2(a[2] - c[2], a[1] - c[1]) for a, c in zip(p_ups, centers)]
    t1 = d.time
    def arc(t):
        u = np.clip((t - t1) / 1.5, 0, 1)
        for mp, c, rad, th0, e in zip(hands, centers, radii, u0s, ends):
            th = th0 + u * (np.arctan2(e[2] - c[2], e[1] - c[1]) - th0)
            d.mocap_pos[mp] = [c[0] + u * (e[0] - c[0]),
                               c[1] + rad * np.cos(th),
                               c[2] + rad * np.sin(th)]
    r.run(1.5, arc)
    r.run(0.3)
    for wid in wids:
        d.eq_active[wid] = 0
    r.run(1.5)

    v = vertices(m, d, name)
    span_post_y = float(np.ptp(v[:, 1]))
    layer_frac = float((v[:, 2] > BED_TOP + 3 * params.radius).mean())
    unmoved = v[~moved_mask]
    lo, hi = unmoved[:, :2].min(0), unmoved[:, :2].max(0)
    moved = v[moved_mask]
    fold_overlap = float((((moved[:, :2] >= lo) & (moved[:, :2] <= hi))
                          .all(1)).mean())
    png(m, d, out_dir, tag, "folded")
    return {
        "span_pre_y": round(span_pre_y, 3),
        "fold_span_ratio": round(span_post_y / max(span_pre_y, 1e-9), 3),
        "fold_layer_frac": round(layer_frac, 3),
        "fold_overlap": round(fold_overlap, 3),
        "fold_diverged": int(r.diverged),
        "ncon_max_fold": r.ncon_max,
    }


COLS = ["variant", "shape", "spacing", "iterations", "seed", "mujoco_version",
        "git_sha", "nv", "ncon_max", "rt_factor", "stable", "settle_vmax",
        "flatness_flat", "flatness_pre", "flatness_post", "press_gain",
        "span_ratio_pre", "span_ratio_post", "penetration_post",
        "span_pre_y", "fold_span_ratio", "fold_layer_frac", "fold_overlap",
        "pass_count", "error"]


def run_case(model_kind, bending, shape, seed, spacing, iterations,
             out_dir, save_png):
    params = ShirtParams(shape=shape, model=model_kind, spacing=spacing,
                         bending=bending or "medium")
    rng = np.random.default_rng(seed)
    yaw = float(rng.uniform(0, 2 * np.pi))
    tag = f"{model_kind}{':' + bending if bending else ''}_{shape}_{seed}"
    tag = tag.replace(":", "-")
    row = {
        "variant": f"{model_kind}:{bending}" if bending else model_kind,
        "shape": shape, "spacing": spacing, "iterations": iterations,
        "seed": seed, "mujoco_version": mujoco.__version__,
        "git_sha": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                  capture_output=True, text=True,
                                  cwd=REPO).stdout.strip(),
    }
    try:
        xml, platen_lo = build_scene(params, yaw, iterations)
        model = mujoco.MjModel.from_xml_string(xml)
    except Exception as e:  # noqa: BLE001
        row.update(stable=0, error=str(e).splitlines()[0][:120])
        return row
    expected = 1 + 2 * (BED_TILES[0] * BED_TILES[1]) + 4 + model.flex_vertnum[0]
    if model.nbody != expected:
        print(f"   [warn] nbody={model.nbody}, expected {expected}")
    row["nv"] = model.nv

    try:
        # PRESS scenario (fresh data; shirt was generated at yaw)
        pr = scenario_press(model, params, rng, yaw, platen_lo, out_dir, tag)
        row.update({k: v for k, v in pr.items() if k in COLS or k == "ncon_max"})
        if pr["flatness_pre"] < 0.015:
            print(f"   [warn] crumple too weak: flatness_pre={pr['flatness_pre']}")
        # FOLD scenario (fresh data)
        fr = scenario_fold(model, params, rng, out_dir, tag)
        row["span_pre_y"] = fr["span_pre_y"]
        row["fold_span_ratio"] = fr["fold_span_ratio"]
        row["fold_layer_frac"] = fr["fold_layer_frac"]
        row["fold_overlap"] = fr["fold_overlap"]
        row["ncon_max"] = max(pr["ncon_max"], fr["ncon_max_fold"])
        if fr["fold_diverged"]:
            row["diverged"] = 1
    except Exception as e:  # noqa: BLE001
        row.update(stable=row.get("stable", 0), error=str(e)[:160])

    crit = [
        bool(row.get("stable")),
        (row.get("press_gain") or 9) < 0.6,
        (row.get("penetration_post") or -9) > -0.010,
        (row.get("fold_span_ratio") or 9) <= 0.7,
        (row.get("fold_layer_frac") or 0) >= 0.30,
        (row.get("fold_overlap") or 0) >= 0.6,
        (row.get("rt_factor") or 0) >= 0.5,
    ]
    row["pass_count"] = sum(crit)
    row["_crit"] = crit
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+",
                    default=["constraint", "hybrid:soft", "hybrid:medium",
                             "hybrid:stiff", "fem"])
    ap.add_argument("--shapes", nargs="+", default=["rect", "tshirt"],
                    choices=["rect", "tshirt"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0])
    ap.add_argument("--spacing", type=float, default=0.035)
    ap.add_argument("--iterations", type=int, default=200)
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--csv", default=str(OUT_DIR / "results.csv"))
    args = ap.parse_args()

    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = Path(args.csv)
    new = not csv_path.exists()

    rows = []
    for var in args.variants:
        kind, _, bend = var.partition(":")
        for shape in args.shapes:
            for seed in args.seeds:
                print(f"=== {var}/{shape}/s{seed}", flush=True)
                row = run_case(kind, bend or None, shape, seed,
                               args.spacing, args.iterations, out_dir,
                               not args.no_png)
                rows.append(row)
                print("   ", {k: row.get(k) for k in
                               ("stable", "press_gain", "penetration_post",
                                "fold_span_ratio", "fold_layer_frac",
                                "fold_overlap", "rt_factor", "pass_count",
                                "error")}, flush=True)

    with csv_path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)

    print(f"\n{'variant':<18}{'shape':<7}{'seed':<5}{'stab':<6}{'press':<7}"
          f"{'penet':<7}{'fspan':<7}{'layer':<7}{'overl':<7}{'rt':<6}{'pass'}")
    for r in rows:
        c = r.get("_crit", [False] * 7)
        print(f"{r['variant']:<18}{r['shape']:<7}{r['seed']:<5}"
              + "".join(f"{str(x):<7}" for x in c[:6])
              + f"{str(c[6]):<6}{r.get('pass_count', 0)}/7")
    print(f"\nCSV: {csv_path}")

    # contact sheet: rows = bench rows, cols = stages (side view)
    stages = ["flat", "crumpled", "pressed", "folded"]
    try:
        from PIL import Image
        imgs = []
        for r in rows:
            tag = f"{r['variant'].replace(':', '-')}_{r['shape']}_{r['seed']}"
            row_imgs = []
            for st in stages:
                p = out_dir / f"{tag}_{st}_side.png"
                row_imgs.append(Image.open(p) if p.exists()
                                else Image.new("RGB", (640, 360), (30, 30, 30)))
            imgs.append(row_imgs)
        if imgs:
            w, h = imgs[0][0].size
            sheet = Image.new("RGB", (w * len(stages), h * len(imgs)))
            for ri, row_imgs in enumerate(imgs):
                for ci, im in enumerate(row_imgs):
                    sheet.paste(im, (ci * w, ri * h))
            sheet.save("/tmp/xfold_bench_sheet.png")
            print("sheet: /tmp/xfold_bench_sheet.png")
    except Exception as e:  # noqa: BLE001
        print(f"[sheet fail] {e}")


if __name__ == "__main__":
    main()
