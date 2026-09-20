"""The XFOLD line on Isaac Sim: same Line, PhysX underneath.

    export OMNI_KIT_ACCEPT_EULA=YES      # once you have read NVIDIA's EULA
    python -m xfold_isaac.run -g tee --seed 7 --events data/isaac/tee.jsonl \
        --video data/isaac/tee.mp4 --photo data/isaac/tee_qc.jpg

Headless by default (the GPU box has no display). One cycle unless
--cycles says otherwise; 0 keeps going. Events are the same records
Line.on_event gives the dashboard, one JSON object per line, so a MuJoCo
run and an Isaac run can be compared with ``python -m xfold_isaac.compare``.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np


# A step costs ~5.3 ms whatever it integrates (PhysX itself is ~3.2 ms of it),
# so the timestep is what decides how close to realtime the line runs. At
# 5.5 ms it runs at ~1x. Checked against the MuJoCo line: same 29 events and
# outcomes for a packed tee, a packed polo and a skewed stained reject; the
# folded pack is 30.7x32.5cm x31mm vs MuJoCo's 31.0x33.1cm x33mm, and phases
# drift ~1 s over a 47 s cycle.
#
# It is near the edge: at 6 ms the cloth no longer settles where Line waits
# for it and a cycle drags on for minutes of simulated time. Drop to 0.004 (or
# 0.002, MuJoCo's own step) for margin rather than raising this.
DEFAULT_TIMESTEP = 0.0055


def _args() -> argparse.Namespace:
    from xfold.garments import add_garment_arguments

    parser = argparse.ArgumentParser(description="XFOLD line on Isaac Sim (PhysX)")
    parser.add_argument("--cycles", type=int, default=1, help="0 keeps going")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--flat", action="store_true", help="skip the dual-belt turner even if --skewed")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="machinery speed: 1 is nominal, 20 is twenty times")
    add_garment_arguments(parser)
    parser.add_argument("--gui", action="store_true", help="open Isaac Sim's window (needs a display)")
    parser.add_argument("--events", type=Path, help="write Line events here (JSON lines)")
    parser.add_argument("--video", type=Path, help="write an MP4 of --camera here")
    parser.add_argument("--camera", default="follow", help="follow, or a line.xml camera: overview, qc_cam, ...")
    parser.add_argument("--fps", type=float, default=24.0, help="rendered frames per simulated second")
    parser.add_argument("--size", default="1920x1080", help="video frame size, WxH")
    parser.add_argument("--photo", type=Path, help="save the QC product shot here")
    parser.add_argument("--usd", type=Path, help="also save the built stage here (.usda / .usd)")
    parser.add_argument("--max-seconds", type=float, default=0.0, help="stop after this much sim time")
    parser.add_argument("--profile", action="store_true", help="print where each step's time went")
    parser.add_argument("--timestep", type=float, default=DEFAULT_TIMESTEP,
                        help="physics timestep. Fewer, bigger steps run the line closer to realtime; "
                             "0.002 (shirt.toml) matches the MuJoCo line step for step")
    parser.add_argument("--serve", type=int, default=0, metavar="PORT",
                        help="stream the camera + phase on 127.0.0.1:PORT (see scripts/live.sh)")
    cloth = parser.add_argument_group("cloth (PhysX surface deformable)")
    cloth.add_argument("--youngs", type=float, default=2.0e6)
    cloth.add_argument("--poisson", type=float, default=0.3)
    cloth.add_argument("--bend", type=float, default=2.0e-4, help="bend stiffness")
    cloth.add_argument("--cloth-damping", type=float, default=0.02)
    cloth.add_argument("--no-self-collision", action="store_true")
    return parser.parse_args()


class FollowCam:
    """xfold.line.FollowCam's view (same distance, azimuth, elevation, lag),
    as a pose for a USD camera instead of an MjvCamera."""

    def __init__(self) -> None:
        from xfold.line import FollowCam as Reference, SPAWN_X, SURFACE_Z

        self.ref = Reference
        self.lookat = np.array([SPAWN_X, 0.0, SURFACE_Z + 0.08], dtype=float)
        self._started = False

    def reset(self) -> None:
        from xfold.line import SPAWN_X, SURFACE_Z

        self.lookat = np.array([SPAWN_X, 0.0, SURFACE_Z + 0.08], dtype=float)
        self._started = False

    def eye(self) -> tuple[np.ndarray, np.ndarray]:
        az, el = math.radians(self.ref.AZIMUTH), math.radians(self.ref.ELEVATION)
        forward = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
        return self.lookat - self.ref.DISTANCE * forward, forward

    def pose(self, cloth: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
        from xfold.line import SPAWN_X, SURFACE_Z

        rest_z = SURFACE_Z + 0.08
        goal = np.array([cloth[:, 0].mean(), 0.0, 0.65 * rest_z + 0.35 * cloth[:, 2].mean()])
        if not self._started:
            # Rest-pose verts are under the press; stay on the infeed until load.
            if abs(float(goal[0]) - SPAWN_X) > 0.40:
                return self.eye()
            self.lookat = goal
            self._started = True
        elif dt <= 0.0:
            self.lookat = goal
        else:
            self.lookat = self.lookat + (goal - self.lookat) * (1.0 - math.exp(-dt / self.ref.TAU))
        return self.eye()


def kit_args() -> list[str]:
    """Extra Kit arguments from XFOLD_ISAAC_KIT_ARGS, space separated.

    For trying renderer settings without touching the code, e.g.
    XFOLD_ISAAC_KIT_ARGS="--/rtx/ambientOcclusion/enabled=false".
    """
    import os

    return os.environ.get("XFOLD_ISAAC_KIT_ARGS", "").split()


def _time_backend(backend, into: dict) -> None:
    """Wrap the backend's calls so --profile can say where a step went."""

    def timed(name, call):
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                return call(*args, **kwargs)
            finally:
                into[name] = into.get(name, 0.0) + time.perf_counter() - started

        return wrapper

    for name in ("write_kinematics", "write_cloth", "read_cloth", "write_bag",
                 "read_bag", "step", "render", "sync_visuals", "capture"):
        setattr(backend, name, timed(name, getattr(backend, name)))


def main() -> None:
    args = _args()
    width, height = (int(v) for v in args.size.lower().split("x"))

    # Kit has to be up before anything from omni / isaacsim / pxr-with-physx loads.
    from isaacsim import SimulationApp

    # The renderer draws the physics-free VISUAL tree, which is plain USD; with
    # the Fabric scene delegate on it would draw Fabric, where those edits lag.
    app = SimulationApp(
        {
            "headless": not args.gui,
            "width": width,
            "height": height,
            "extra_args": ["--/app/useFabricSceneDelegate=0", *kit_args()],
        }
    )

    import isaacsim.core.experimental.utils.stage as stage_utils
    import mujoco
    from isaacsim.core.simulation_manager import SimulationManager
    from xfold.garments import garment_from_args
    from xfold.line import LINE_PATH, Line, build
    from xfold.shirt import select_garment, shirt_config

    from .engine import EngineShim
    from .isaac_backend import ClothPhysics, IsaacBackend, save_png
    from .usd_scene import build_stage

    chosen = garment_from_args(args, interactive=False, current=shirt_config().garment)
    skewed = bool(args.skewed)
    if chosen:
        select_garment(chosen.key)
        skewed = chosen.skewed
    cfg = shirt_config()
    model = build()
    if args.timestep:
        model.opt.timestep = args.timestep
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    out_dir = Path(args.video or args.events or args.photo or "data/isaac/run").resolve().parent
    stage_utils.create_new_stage()
    stage = stage_utils.get_current_stage(backend="usd")
    scene = build_stage(stage, model, data, texture_dir=out_dir / "textures")
    SimulationManager.setup_simulation(dt=float(model.opt.timestep), device="cuda")
    app.update()

    cloth = ClothPhysics(
        mass=cfg.mass,
        youngs=args.youngs,
        poisson=args.poisson,
        thickness=cfg.thickness,
        bend_stiffness=args.bend,
        friction=cfg.friction,
        damping=args.cloth_damping,
        rest_offset=cfg.radius,
        contact_offset=2.0 * cfg.radius,
        self_collision=not args.no_self_collision,
    )
    backend = IsaacBackend(app, stage, model, scene, cloth)
    if args.usd:
        args.usd.parent.mkdir(parents=True, exist_ok=True)
        stage.Export(str(args.usd))
    backend.start()

    events: list[dict] = []
    sink = None
    if args.events:
        args.events.parent.mkdir(parents=True, exist_ok=True)
        sink = args.events.open("w", encoding="utf-8")

    live = None
    if args.serve:
        from .live import LiveView

        live = LiveView(args.serve)
        live.status(garment=cfg.garment, seed=args.seed)

    def on_event(event: dict) -> None:
        event = {**event, "engine": "isaac", "garment": cfg.garment, "seed": args.seed}
        events.append(event)
        if live is not None:
            live.status(phase=event["state"], operation=event["operation"], message=event["message"], t=event["t"])
        if sink is not None:
            sink.write(json.dumps(event) + "\n")
            sink.flush()

    shim: EngineShim | None = None

    def on_photo() -> None:
        if args.photo is None or shim is None:
            return
        shim.sync_visuals()
        save_png(backend.capture("qc_cam", 768, 768), args.photo)
        print(f"QC photo -> {args.photo}", flush=True)

    def on_fold_inspect():
        from xfold.fold_quality import inspect_fold

        if shim is None:
            return None
        shim.sync_visuals()
        got = inspect_fold(backend.capture("fold_qc_cam", 768, 768))
        if args.photo is not None and got.annotated is not None:
            fold_path = args.photo.with_name(f"{args.photo.stem}_fold{args.photo.suffix}")
            save_png(got.annotated, fold_path)
            print(f"fold eval -> {fold_path}  {got.score:.0f}%", flush=True)
        return got.score

    line = Line(
        model,
        data,
        repeat=args.cycles == 0,
        skewed=skewed,
        flat=bool(args.flat),
        seed=int(args.seed),
        speed=float(args.speed),
        on_photo=on_photo,
        on_fold_inspect=on_fold_inspect,
        on_event=on_event,
    )
    dt = float(model.opt.timestep)
    visual = bool(args.video or args.gui or live)
    every = max(1, round(1.0 / (args.fps * dt))) if visual else max(1, round(0.5 / dt))
    shim = EngineShim(line, backend, render_every=every)

    writer = None
    follow = FollowCam() if args.camera == "follow" else None
    camera = "follow" if follow is not None else args.camera
    if follow is not None:
        backend.set_camera("follow", *follow.eye())
    if args.video:
        import imageio_ffmpeg

        args.video.parent.mkdir(parents=True, exist_ok=True)
        writer = imageio_ffmpeg.write_frames(
            str(args.video), (width, height), fps=args.fps, codec="libx264", pix_fmt_out="yuv420p", quality=8
        )
        writer.send(None)

    timings: dict[str, float] = {}
    if args.profile:
        _time_backend(backend, timings)

    pose = "operator-skewed" if skewed and not args.flat else "square"
    print(f"XFOLD line on Isaac Sim  garment={cfg.garment} ({cfg.mesh})  pose={pose}  seed={args.seed}  {LINE_PATH}")

    def done() -> bool:
        if args.max_seconds and data.time >= args.max_seconds:
            return True
        return line.finished or bool(args.cycles and line.cycles > args.cycles)

    started = time.perf_counter()
    while not done() and app.is_running():
        if follow is not None and shim.steps % every == 0:
            pos, forward = follow.pose(line.positions(), every * dt)
            backend.set_camera("follow", pos, forward)
        rendered = shim.steps % every == 0
        line.step()
        if rendered and (writer is not None or live is not None):
            frame = np.ascontiguousarray(backend.capture(camera, width, height, fresh=False))
            if writer is not None:
                writer.send(frame)
            if live is not None:
                live.frame(frame)
                live.status(t=float(data.time))
    wall = time.perf_counter() - started

    if writer is not None:
        writer.close()
    if sink is not None:
        sink.close()
        # Rewrite with the outcome on the last event, as compare.record does.
        if events:
            events[-1]["outcome"] = line.outcome
        args.events.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    if args.profile and shim.steps:
        print(f"per step ({shim.steps} steps, {1000 * wall / shim.steps:.2f} ms each):")
        for name, spent in sorted(timings.items(), key=lambda kv: -kv[1]):
            print(f"  {name:<14} {1000 * spent / shim.steps:7.3f} ms  {100 * spent / wall:5.1f}%")
        rest = wall - sum(timings.values())
        print(f"  {'controller':<14} {1000 * rest / shim.steps:7.3f} ms  {100 * rest / wall:5.1f}%")
    pos = line.positions()
    print(
        f"{data.time:.1f} s simulated in {wall:.1f} s ({data.time / max(wall, 1e-9):.2f}x)  "
        f"events={len(events)}  outcome={line.outcome}  frames={backend.frames}  "
        f"cloth z {pos[:, 2].min():.3f}..{pos[:, 2].max():.3f}",
        flush=True,
    )
    if live is not None:
        live.status(done=True, outcome=line.outcome)
        live.linger(5.0)
    app.close()


if __name__ == "__main__":
    main()
