"""The line, no robots: belt -> press -> flap folder.

1. A shirt lies flat on the belt, collar leading, already where it belongs.
2. The belt carries it under the press and stops. The platen comes down on
   the belt itself, steams, and lifts.
3. The belt runs on. The shirt leaves the belt's end onto the folder, and
   stops there with its hem on the folder's upstream edge.
4. The folder flips its flaps, FlipFold style: left side, right side, then
   the hem half up over the collar half.

The belt is not a moving body. Cloth lying on it is given the belt's speed
each step, which is what a belt does to something that does not slip. The
folder's infeed runs with the belt while it takes the shirt over: cloth
cannot be pushed, so a folder that only let the belt shove the shirt onto
it would get a heap, not a shirt.

A flap carries the cloth lying on it rigidly while it swings, the way a
real flap's friction does, and lets go at the top of the swing. The cloth
does not collide with itself in MuJoCo, so ClothLayers keeps the folded
layers apart from then on.

With a window:  moon run sim:run              # type, then good / damaged / notGood / skewed
                moon run sim:run -- -g tee --skewed
                moon run sim:run -- -g dress  # skip the list
Headless:       pixi run -e mujoco python -P -m xfold.line --headless --cycles 1 -g jersey
Catalogue:      moon run sim:run -- --list-garments
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .garments import add_garment_arguments, garment_from_args, rewrite_argv_garment
from .platform import reexec_under_mjpython
from .self_collide import ClothLayers
from .shirt import (
    SHIRT_RADIUS,
    apply_shirt_config,
    load_mujoco_plugins,
    load_shirt_mesh,
    select_garment,
    set_steam,
    shirt_config,
    shirt_rest_world,
    shirt_vertex_qposadr,
    spec_from_mjcf,
)
from .sim_loop import smoothstep
from .steam import SteamField

LINE_PATH = Path(__file__).resolve().parents[2] / "models" / "line.xml"

# Belt top and folder plates, from line.xml.
SURFACE_Z = 0.562
BELT_X = (-2.00, 0.30)
# The folder's boards, hem edge to collar edge.
FOLDER_X = (0.305, 0.965)
# The hem stops this far onto the folder, not hanging off its edge.
HEM_INSET = 0.012
BELT_SPEED = 0.35  # m/s
BELT_ACCEL = 0.6  # m/s^2, both speeding up and braking
# Cloth this close above the belt top rides with it.
ON_BELT = 0.03

# How far a "not square on the belt" drop is rotated / shifted.
SKEW_YAW = math.radians(35.0)
SKEW_Y = 0.09
# The shirt's centre when it is put on the belt, and where the press is.
SPAWN_X = -1.55
PRESS_X = -0.75

# press_stroke commands (press_rig.xml): 0 is open, PRESSED squeezes cloth
# lying at SURFACE_Z.
STROKE_OPEN = 0.0
STROKE_PRESSED = -0.755

# Gap the folded layers keep between them. The flap hinges in line.xml are
# lifted by multiples of this so each flip lands on top of what is there.
LAYER_GAP = 0.008
# Keeping the layers apart is Python, not MuJoCo; every step is 3x too slow
# for a live window, and under gravity a layer sags ~0.5 mm in 5 steps.
LAYER_EVERY = 5


@dataclass(frozen=True)
class Flap:
    body: str
    axis: tuple[float, float, float]
    over: float  # seconds for the swing up and over
    back: float  # seconds to swing back down, empty

    def carries(self, pos: np.ndarray, hinge: np.ndarray) -> np.ndarray:
        """Which cloth vertices lie on this flap's side of the hinge.

        All of them: one left behind on the flap side loses its support when
        the flap swings and drops into the seam.
        """
        if self.axis[1]:
            return pos[:, 0] < hinge[0]
        side = math.copysign(1.0, self.axis[0])
        return side * (pos[:, 1] - hinge[1]) > 0.0


# In folding order.
FLAPS = (
    Flap("flap_left", (1.0, 0.0, 0.0), over=1.2, back=0.8),
    Flap("flap_right", (-1.0, 0.0, 0.0), over=1.2, back=0.8),
    Flap("flap_bottom", (0.0, 1.0, 0.0), over=1.4, back=0.9),
)


class _Layers(ClothLayers):
    """ClothLayers with a dense pair search. At 410 vertices one distance
    matrix is ~3x faster than the spatial hash, which is built for the
    1080-vertex playground mesh."""

    def _near_pairs(self, pos: np.ndarray) -> np.ndarray:
        sq = np.einsum("ij,ij->i", pos, pos)
        near = sq[:, None] + sq[None, :] - 2.0 * pos @ pos.T < self._sep**2
        return np.column_stack(np.nonzero(near & self._allow))


def build():
    """Compile line.xml, with the press's own bed and table taken out."""
    import mujoco

    load_mujoco_plugins()
    spec = spec_from_mjcf(LINE_PATH)
    apply_shirt_config(spec, claws=False)
    # The belt runs through the press, so the belt is its bed now.
    spec.delete(spec.actuator("press_tilt"))
    for name in ("press_table", "press_bed"):
        spec.delete(spec.body(name))
    spec.body("press_origin").pos = [PRESS_X, 0.0, 0.0]
    return spec.compile()


def flat_shirt(center_x: float, *, yaw: float = 0.0, y: float = 0.0) -> np.ndarray:
    """World vertices of the shirt lying flat on the belt, collar toward +x.

    ``yaw`` is rotation about +Z (radians). ``y`` is a lateral shift. A
    square drop is yaw=0, y=0; a bad belt place uses SKEW_YAW / SKEW_Y.
    """
    mesh = load_shirt_mesh()[0]  # OBJ frame: sleeves along x, collar at +y
    world = np.empty_like(mesh)
    world[:, 0] = mesh[:, 1] - 0.5 * (mesh[:, 1].min() + mesh[:, 1].max()) + center_x
    world[:, 1] = -mesh[:, 0]
    world[:, 2] = SURFACE_Z + SHIRT_RADIUS
    if yaw or y:
        mid = world.mean(axis=0)
        rel = world - mid
        cos, sin = math.cos(yaw), math.sin(yaw)
        rot = np.empty_like(rel)
        rot[:, 0] = rel[:, 0] * cos - rel[:, 1] * sin
        rot[:, 1] = rel[:, 0] * sin + rel[:, 1] * cos
        rot[:, 2] = rel[:, 2]
        world = rot + mid
        world[:, 1] += y
        world[:, 2] = SURFACE_Z + SHIRT_RADIUS
    return world


class Line:
    """Runs the line one physics step at a time: ``step()`` forever.

    The cycle is a generator that sets this step's commands and yields; the
    viewer, a headless run and the dashboard viewport all just call step().
    """

    def __init__(self, model, data, repeat: bool = True, log=print, *, skewed: bool = False) -> None:
        import mujoco

        self._mujoco = mujoco
        self.model = model
        self.data = data
        self.repeat = repeat
        self.log = log
        self.skewed = skewed
        self.dt = float(model.opt.timestep)

        self._qadr = shirt_vertex_qposadr(model)
        self._dadr = np.array(
            [int(model.jnt_dofadr[model.body_jntadr[b]]) for b in model.flex_vertbodyid]
        )
        mujoco.mj_resetData(model, data)
        mujoco.mj_forward(model, data)
        self._rest = shirt_rest_world(model, data)
        self._xyz = np.arange(3)

        self._stroke = model.actuator("press_stroke").id
        self._steam = SteamField(model)
        self._slats = [
            model.geom(i).id
            for i in range(model.ngeom)
            if model.geom(i).name.startswith("belt_slat_")
        ]
        self._slat_x0 = model.geom_pos[self._slats, 0].copy()
        self._mocap = {f.body: int(model.body(f.body).mocapid[0]) for f in FLAPS}
        self._flap_geom = {f.body: model.geom(f.body).id for f in FLAPS}

        self.belt_speed = 0.0
        self._belt_travel = 0.0
        self._drive_to = BELT_X[1]  # cloth rides the belt up to this x
        self._layers: ClothLayers | None = None
        self._since_layers = 0
        self.stage = "idle"
        self.cycles = 0
        self.finished = False
        self._program = self._run()

    # --- stepping -----------------------------------------------------

    def step(self) -> None:
        """Advance the line by one physics step."""
        if not self.finished:
            try:
                next(self._program)
            except StopIteration:
                self.finished = True
        self._drive_belt()
        self._steam.follow(self.data)
        self._mujoco.mj_step(self.model, self.data)
        self._since_layers += 1
        if self._layers is not None and self._since_layers >= LAYER_EVERY:
            self._layers.separate()
            self._since_layers = 0

    def positions(self) -> np.ndarray:
        """Cloth vertices in the world, current as of this step's qpos."""
        return self._rest + self.data.qpos[self._qadr[:, None] + self._xyz]

    def _pin(self, ids: np.ndarray, world: np.ndarray, vel: np.ndarray | None) -> None:
        self.data.qpos[self._qadr[ids, None] + self._xyz] = world - self._rest[ids]
        self.data.qvel[self._dadr[ids, None] + self._xyz] = 0.0 if vel is None else vel

    def _drive_belt(self) -> None:
        if self.belt_speed == 0.0:
            return
        self._belt_travel += self.belt_speed * self.dt
        span = BELT_X[1] - BELT_X[0]
        self.model.geom_pos[self._slats, 0] = (
            BELT_X[0] + (self._slat_x0 - BELT_X[0] + self._belt_travel) % span
        )
        pos = self.positions()
        riding = (
            (pos[:, 0] >= BELT_X[0])
            & (pos[:, 0] <= self._drive_to)
            & (pos[:, 2] < SURFACE_Z + ON_BELT)
        )
        self.data.qvel[self._dadr[riding]] = self.belt_speed

    # --- the cycle ----------------------------------------------------

    def _run(self):
        while True:
            self.cycles += 1
            yield from self._cycle()
            if not self.repeat:
                return

    def _cycle(self):
        self._load()
        load_msg = (
            "skewed shirt on the belt" if self.skewed else "flat shirt on the belt"
        )
        yield from self._hold("LOAD", load_msg, 0.6)

        self._enter("BELT", "carry the shirt under the press")
        yield from self._belt_until(lambda pos: PRESS_X - float(pos[:, 0].mean()))

        self._enter("PRESS", "platen down on the belt")
        yield from self._ramp_stroke(STROKE_PRESSED, 2.5)
        self._enter("STEAM", "steam under the platen")
        yield from self._steam_for(3.0)
        self._enter("LIFT", "platen up")
        yield from self._ramp_stroke(STROKE_OPEN, 2.0)

        self._enter("BELT", "run the shirt off the belt onto the folder")
        self._drive_to = FOLDER_X[1]
        yield from self._belt_until(lambda pos: FOLDER_X[0] + HEM_INSET - float(pos[:, 0].min()))
        self._drive_to = BELT_X[1]
        yield from self._hold("SETTLE", "shirt on the folder", 0.5)

        self._layers = _Layers(self.model, self.data, thickness=0.5 * LAYER_GAP)
        for flap in FLAPS:
            self._enter("FOLD", flap.body.replace("flap_", "") + " flap over")
            yield from self._flip(flap)
            yield from self._hold("FOLD", "", 0.3, quiet=True)

        pos = self.positions()
        size = pos.max(axis=0) - pos.min(axis=0)
        yield from self._hold(
            "DONE",
            f"folded pack {size[0] * 100:.0f} x {size[1] * 100:.0f} cm, "
            f"{size[2] * 1000:.0f} mm tall",
            2.5,
        )

    def _load(self) -> None:
        mujoco = self._mujoco
        mujoco.mj_resetData(self.model, self.data)
        self._layers = None
        self.belt_speed = 0.0
        self._steam.reset()
        set_steam(self.model, False)
        self.data.ctrl[self._stroke] = STROKE_OPEN
        world = (
            flat_shirt(SPAWN_X, yaw=SKEW_YAW, y=SKEW_Y)
            if self.skewed
            else flat_shirt(SPAWN_X)
        )
        ids = np.arange(len(world))
        self._pin(ids, world, None)
        mujoco.mj_forward(self.model, self.data)

    def _enter(self, stage: str, message: str) -> None:
        self.stage = stage
        if message:
            self.log(f"[line {self.cycles}] {stage:<6} {message}")

    def _hold(self, stage: str, message: str, seconds: float, quiet: bool = False):
        if not quiet:
            self._enter(stage, message)
        for _ in range(self._steps(seconds)):
            yield

    def _belt_until(self, remaining):
        """Run the belt until ``remaining(positions)`` metres reach zero.

        The belt brakes on the way in so the shirt stops right there, the way
        a line stops a part at a station.
        """
        while True:
            left = remaining(self.positions())
            if left <= 0.002:
                break
            self.belt_speed = min(
                BELT_SPEED,
                self.belt_speed + BELT_ACCEL * self.dt,
                max(0.02, math.sqrt(2.0 * BELT_ACCEL * left)),
            )
            yield
        self.belt_speed = 0.0

    def _ramp_stroke(self, target: float, seconds: float):
        start = float(self.data.ctrl[self._stroke])
        steps = self._steps(seconds)
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            self.data.ctrl[self._stroke] = start + (target - start) * blend
            yield

    def _steam_for(self, seconds: float):
        set_steam(self.model, True)
        for index in range(self._steps(seconds)):
            self._steam.puff(index * self.dt, seconds)
            yield
        self._steam.reset()
        set_steam(self.model, False)

    def _flip(self, flap: Flap):
        """Swing a flap over, carrying its cloth, let go, swing back."""
        mocap = self._mocap[flap.body]
        hinge = self.data.mocap_pos[mocap].copy()
        axis = np.asarray(flap.axis)

        pos = self.positions()
        ids = np.flatnonzero(flap.carries(pos, hinge))
        arm = pos[ids] - hinge

        for angle, rate in self._swing(0.0, math.pi, flap.over):
            self._set_flap(mocap, axis, angle)
            moved = _rotate(arm, axis, angle)
            self._pin(ids, hinge + moved, rate * np.cross(axis, moved))
            yield
        # Set down still, at the top of the swing.
        self._pin(ids, hinge + _rotate(arm, axis, math.pi), None)

        # Swinging back empty, the flap's edge by the hinge would sweep
        # through the crease it just made and trap it underneath.
        geom = self._flap_geom[flap.body]
        affinity = int(self.model.geom_conaffinity[geom])
        self.model.geom_conaffinity[geom] = 0
        for angle, _ in self._swing(math.pi, 0.0, flap.back):
            self._set_flap(mocap, axis, angle)
            yield
        self.model.geom_conaffinity[geom] = affinity

    def _swing(self, start: float, end: float, seconds: float):
        steps = self._steps(seconds)
        previous = start
        for index in range(steps):
            angle = start + (end - start) * smoothstep((index + 1) / steps)
            yield angle, (angle - previous) / self.dt
            previous = angle

    def _set_flap(self, mocap: int, axis: np.ndarray, angle: float) -> None:
        half = 0.5 * angle
        self.data.mocap_quat[mocap] = [math.cos(half), *(math.sin(half) * axis)]

    def _steps(self, seconds: float) -> int:
        return max(1, int(round(seconds / self.dt)))


def _rotate(points: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """Rotate points about a unit axis through the origin (Rodrigues)."""
    cos, sin = math.cos(angle), math.sin(angle)
    return (
        points * cos
        + np.cross(axis, points) * sin
        + np.outer(points @ axis, axis) * (1.0 - cos)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="XFOLD line: belt, press, folder")
    parser.add_argument("--cycles", type=int, default=0, help="0 keeps going")
    parser.add_argument("--headless", action="store_true", help="no window, as fast as it can")
    add_garment_arguments(parser)
    parser.add_argument(
        "--shots", default="", help="headless: save a frame per stage into this directory"
    )
    parser.add_argument("--camera", default="overview")
    args = parser.parse_args()
    chosen = garment_from_args(
        args, interactive=not args.headless, current=shirt_config().garment
    )
    if chosen:
        rewrite_argv_garment(chosen)
        args.garment = chosen.key
        args.skewed = chosen.skewed

    try:
        import mujoco
    except ImportError:
        raise SystemExit("MuJoCo is not installed.\nFrom the repo root run:  moon run install-mujoco")
    if not args.headless:
        reexec_under_mjpython("xfold.line")

    if args.garment:
        select_garment(args.garment)
    cfg = shirt_config()
    model = build()
    data = mujoco.MjData(model)
    line = Line(model, data, repeat=args.cycles == 0, skewed=bool(args.skewed))
    pose = "skewed" if args.skewed else "square"
    print(
        f"XFOLD line  garment={cfg.garment} ({cfg.mesh})  pose={pose}  {LINE_PATH}",
        flush=True,
    )

    def done() -> bool:
        return line.finished or (args.cycles and line.cycles > args.cycles)

    if args.headless:
        _run_headless(line, args.shots, args.camera, done)
        return

    import mujoco.viewer

    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
        viewer.cam.fixedcamid = model.camera(args.camera).id
        per_frame = max(1, round((1.0 / 60.0) / line.dt))
        while viewer.is_running() and not done():
            started = time.perf_counter()
            for _ in range(per_frame):
                line.step()
            viewer.sync()
            time.sleep(max(0.0, per_frame * line.dt - (time.perf_counter() - started)))


def _run_headless(line: Line, shots: str, camera: str, done) -> None:
    renderer = None
    if shots:
        import mujoco

        Path(shots).mkdir(parents=True, exist_ok=True)
        renderer = mujoco.Renderer(line.model, height=720, width=1280)

    frame = 0
    previous = None
    started = time.perf_counter()
    while not done():
        line.step()
        # One frame as each stage ends, plus a few through each flip.
        label = (line.stage, line.cycles)
        flipping = line.stage == "FOLD" and line.data.time % 0.4 < line.dt
        if renderer is not None and (label != previous or flipping):
            from PIL import Image

            renderer.update_scene(line.data, camera=camera)
            path = Path(shots) / f"{frame:03d}_{line.stage.lower()}.png"
            Image.fromarray(renderer.render()).save(path)
            frame += 1
        previous = label
    wall = time.perf_counter() - started
    print(f"{line.data.time:.1f} s simulated in {wall:.1f} s", flush=True)


if __name__ == "__main__":
    main()
