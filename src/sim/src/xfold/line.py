"""The line, no robots: belt -> press -> flap folder -> bagger -> carton.

1. A shirt lies flat on the belt, collar leading, already where it belongs.
2. The belt carries it under the press and stops. The platen comes down on
   the belt itself, steams, and lifts.
3. The belt runs on. The shirt leaves the belt's end onto the folder, and
   stops there with its hem on the folder's upstream edge.
4. The folder flips its flaps, FlipFold style: left side, right side, then
   the hem half up over the collar half.
5. The plate the pack sits on is a peel. It slides between two rails into a
   stiff, ready-made bag, like a pizza into an oven, and pulls back out.
6. The bag is ready-made: floor, roof, sides and far end already welded. Only
   the mouth is left. Its tail folds down to the floor, and a seal bar welds
   it while a stamp sticks an RFID label on the roof.
7. Belt 2 carries the bag off its end and it drops into a carton.

A peel or a flap is a mocap body, which the contact solver sees as standing
still, so it cannot drag cloth by friction: whatever it carries is moved
with it explicitly, and nothing it slides out from under is dragged back.
Once sealed, the shirt is fixed inside the bag's frame every step, so it
travels, falls and lands with the bag. The cloth is not simulated as
touching the bag's films.

The belt is not a moving body. Cloth lying on it is given the belt's speed
each step, which is what a belt does to something that does not slip. The
folder's infeed runs with the belt while it takes the shirt over: cloth
cannot be pushed, so a folder that only let the belt shove the shirt onto
it would get a heap, not a shirt.

A flap carries the cloth lying on it rigidly while it swings, the way a
real flap's friction does, and lets go at the top of the swing. The cloth
does not collide with itself in MuJoCo, so ClothLayers keeps the folded
layers apart from then on.

With a window:  moon run sim:run              # arrow-key list
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
FOLDER_X = (0.305, 0.98)
# The hem stops this far onto the folder, not hanging off its edge.
HEM_INSET = 0.012
BELT_SPEED = 0.35  # m/s
BELT_ACCEL = 0.6  # m/s^2, both speeding up and braking
# Cloth this close above the belt top rides with it.
ON_BELT = 0.03

# The shirt's centre when it is put on the belt, and where the press is.
SPAWN_X = -1.55
PRESS_X = -0.75
# The press's columns move out this far from press_rig.xml's +/-0.46, so the
# belt between them (+/-0.485) is wider than the sleeves (+/-0.456).
PRESS_WIDEN = 0.08

# press_stroke commands (press_rig.xml): 0 is open, PRESSED squeezes cloth
# lying at SURFACE_Z.
STROKE_OPEN = 0.0
STROKE_PRESSED = -0.755

# Belt 2, the bag and the stations along it (xfold: line.xml). Belt 2 has the
# same top height as the folder table, so the peel's bottom is flush with it.
BELT2_X = (0.985, 2.10)
BELT2_SPEED = 0.35
# The bag's centre when it stands open at the bagger, and its half-length.
BAG_X = 1.32
BAG_HALF_LENGTH = 0.30
# The shirt's leading edge stops this far short of the bag's closed end.
BAG_END_MARGIN = 0.02
# The tail is the last stretch of the bag's roof, at the mouth. It lies flat
# while the bag is loaded and folds down to the floor to close it: hinge
# position in the bag's frame, length, and the angle (down is negative) at
# which its far end just touches the floor.
BAG_TAIL_HINGE = (-0.19, 0.0, 0.0372)
BAG_TAIL_LENGTH = 0.11
BAG_TAIL_CLOSED = -math.asin(0.0727 / BAG_TAIL_LENGTH)
# Seal bar and stamp: hover and pressed heights.
PRESS_HOVER_Z = 0.70
SEAL_BAR_Z = 0.562
STAMP_Z = 0.637
# The bag counts as boxed once its centre is below this.
BOXED_Z = 0.25

# Gap the folded layers keep between them. Each flap lands on the layers
# already folded, so its hinge rides up by its ``lift`` as it goes over.
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
    lift: float  # metres the hinge rides up by the time the flap lies over

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
    Flap("flap_left", (1.0, 0.0, 0.0), over=1.2, back=0.8, lift=0.028),
    Flap("flap_right", (-1.0, 0.0, 0.0), over=1.2, back=0.8, lift=0.036),
    Flap("flap_bottom", (0.0, 1.0, 0.0), over=1.4, back=0.9, lift=0.060),
)


class _Layers(ClothLayers):
    """ClothLayers with a dense pair search. At 410 vertices one distance
    matrix is ~3x faster than the spatial hash, which is built for the
    1080-vertex playground mesh. Its floor is the folder's plates, not the
    ground: pushing two layers apart must not push the lower one into them."""

    def __init__(self, model, data, thickness: float) -> None:
        super().__init__(model, data, thickness=thickness)
        self._floor = SURFACE_Z + SHIRT_RADIUS

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
    _widen_press(spec, PRESS_WIDEN)
    return spec.compile()


def _widen_press(spec, dy: float) -> None:
    """Move the press's columns, and all that hangs on them, ``dy`` further out.

    The press was built for a bed, not for a belt carrying a shirt with its
    sleeves spread: at y = +/-0.46 the columns stood in the sleeves' way.
    """
    for geom in spec.body("press_frame").find_all("geom"):
        pos = np.array(geom.pos)
        size = np.array(geom.size)
        if geom.name == "beam":
            size[1] += dy
        elif geom.name in ("steam_run", "nut_arm_l", "nut_arm_r"):
            # Pieces that span from the middle out to a column: stretch them.
            size[1] += 0.5 * dy
            pos[1] += math.copysign(0.5 * dy, pos[1])
        elif abs(pos[1]) >= 0.40:
            pos[1] += math.copysign(dy, pos[1])
        geom.pos = pos
        geom.size = size


def flat_shirt(center_x: float) -> np.ndarray:
    """World vertices of the shirt lying flat on the belt, collar toward +x."""
    mesh = load_shirt_mesh()[0]  # OBJ frame: sleeves along x, collar at +y
    world = np.empty_like(mesh)
    world[:, 0] = mesh[:, 1] - 0.5 * (mesh[:, 1].min() + mesh[:, 1].max()) + center_x
    world[:, 1] = -mesh[:, 0]
    world[:, 2] = SURFACE_Z + SHIRT_RADIUS
    return world


class Line:
    """Runs the line one physics step at a time: ``step()`` forever.

    The cycle is a generator that sets this step's commands and yields; the
    viewer, a headless run and the dashboard viewport all just call step().
    """

    def __init__(self, model, data, repeat: bool = True, log=print) -> None:
        import mujoco

        self._mujoco = mujoco
        self.model = model
        self.data = data
        self.repeat = repeat
        self.log = log
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

        self._slats2 = [
            model.geom(i).id
            for i in range(model.ngeom)
            if model.geom(i).name.startswith("belt2_slat_")
        ]
        self._slat2_x0 = model.geom_pos[self._slats2, 0].copy()
        self._peel = int(model.body("peel").mocapid[0])
        self._seal_bar = int(model.body("seal_bar").mocapid[0])
        self._stamp = int(model.body("stamp").mocapid[0])
        bag = model.body("bag")
        joint = int(bag.jntadr[0])
        self._bag = bag.id
        self._bag_qadr = int(model.jnt_qposadr[joint])
        self._bag_dadr = int(model.jnt_dofadr[joint])
        self._g = {
            name: model.geom(name).id
            for name in (
                "bag_tail",
                "bag_seam",
                "bag_sticker",
                "bag_antenna",
                "stamp_sticker",
                "stamp_antenna",
                "seal_bar_head",
            )
        }
        self._rgba0 = {name: model.geom_rgba[gid].copy() for name, gid in self._g.items()}
        self._bag_local: np.ndarray | None = None  # shirt vertices in the bag's frame

        self.belt_speed = 0.0
        self.belt2_speed = 0.0
        self._belt_travel = 0.0
        self._belt2_travel = 0.0
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
        self._drive_belt2()
        self._steam.follow(self.data)
        self._mujoco.mj_step(self.model, self.data)
        self._carry_cloth()
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

    def _drive_belt2(self) -> None:
        """Belt 2 carries the bag while the bag's centre is over it.

        The belt is not a body, so the bag is given the belt's speed and kept
        level; past the belt's end it is on its own and tips off.
        """
        if self.belt2_speed == 0.0:
            return
        self._belt2_travel += self.belt2_speed * self.dt
        span = BELT2_X[1] - BELT2_X[0]
        self.model.geom_pos[self._slats2, 0] = (
            BELT2_X[0] + (self._slat2_x0 - BELT2_X[0] + self._belt2_travel) % span
        )
        adr = self._bag_dadr
        if self.data.xpos[self._bag][0] < BELT2_X[1]:
            self.data.qvel[adr : adr + 2] = (self.belt2_speed, 0.0)
            self.data.qvel[adr + 3 : adr + 6] = 0.0

    def _carry_cloth(self) -> None:
        """Hold the shirt at the same place inside the bag, once it is sealed in."""
        if self._bag_local is None:
            return
        qpos = self.data.qpos[self._bag_qadr : self._bag_qadr + 7]
        rotation = np.empty(9)
        self._mujoco.mju_quat2Mat(rotation, qpos[3:])
        rotation = rotation.reshape(3, 3)
        world = qpos[:3] + self._bag_local @ rotation.T
        adr = self._bag_dadr
        spin = rotation @ self.data.qvel[adr + 3 : adr + 6]  # free-joint spin is body-frame
        vel = self.data.qvel[adr : adr + 3] + np.cross(spin, world - qpos[:3])
        self._pin(np.arange(len(world)), world, vel)

    def _seal_in(self) -> None:
        """Fix every shirt vertex to the bag from here on."""
        qpos = self.data.qpos[self._bag_qadr : self._bag_qadr + 7]
        rotation = np.empty(9)
        self._mujoco.mju_quat2Mat(rotation, qpos[3:])
        self._bag_local = (self.positions() - qpos[:3]) @ rotation.reshape(3, 3)

    # --- the cycle ----------------------------------------------------

    def _run(self):
        while True:
            self.cycles += 1
            yield from self._cycle()
            if not self.repeat:
                return

    def _cycle(self):
        self._load()
        yield from self._hold("LOAD", "flat shirt on the belt", 0.6)

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
        self._enter(
            "FOLD",
            f"folded pack {size[0] * 100:.0f} x {size[1] * 100:.0f} cm, "
            f"{size[2] * 1000:.0f} mm tall",
        )
        yield from self._hold("FOLD", "", 0.6, quiet=True)

        self._enter("BAG", "peel slides the pack through the rails into the ready-made bag")
        travel = BAG_X + BAG_HALF_LENGTH - BAG_END_MARGIN - float(pos[:, 0].max())
        yield from self._slide_peel(travel, 2.4, carry=True)
        self._enter("PEEL", "peel slides back out from under the shirt")
        yield from self._slide_peel(-travel, 2.0, carry=False)
        yield from self._hold("PEEL", "", 0.8, quiet=True)
        # The shirt lies still in the bag now. Fix it there: it cannot sag while
        # the bag closes, and it goes wherever the bag goes.
        self._layers = None
        self._seal_in()

        self._enter("CLOSE", "the bag's tail folds down over the mouth")
        yield from self._close_bag(1.2)
        self._enter("SEAL", "seal bar welds the mouth shut, stamp sticks the RFID label on")
        yield from self._seal_and_tag()

        self._enter("BELT", "belt 2 carries the bag to the carton")
        yield from self._convey()
        yield from self._hold("DONE", "bagged, sealed, tagged, boxed", 2.5)

    def _load(self) -> None:
        mujoco = self._mujoco
        mujoco.mj_resetData(self.model, self.data)
        self._layers = None
        self._bag_local = None
        self.belt_speed = 0.0
        self.belt2_speed = 0.0
        self._steam.reset()
        set_steam(self.model, False)
        self.data.ctrl[self._stroke] = STROKE_OPEN
        world = flat_shirt(SPAWN_X)
        ids = np.arange(len(world))
        self._pin(ids, world, None)
        for name, gid in self._g.items():
            self.model.geom_rgba[gid] = self._rgba0[name]
        self.model.geom_rgba[self._g["bag_seam"], 3] = 0.0
        self.model.geom_rgba[self._g["bag_sticker"], 3] = 0.0
        self.model.geom_rgba[self._g["bag_antenna"], 3] = 0.0
        self._pose_tail(0.0)
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

    def _slide_peel(self, travel: float, seconds: float, carry: bool):
        """Move the peel ``travel`` metres along x.

        With ``carry`` the shirt goes with it, exactly. Without, the peel just
        goes: nothing in the solver drags the shirt, which is the point.
        """
        start = self.data.mocap_pos[self._peel].copy()
        cloth = self.positions()
        everything = np.arange(self.model.nflexvert)
        steps = self._steps(seconds)
        done = 0.0
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            shift = np.array([travel * blend, 0.0, 0.0])
            self.data.mocap_pos[self._peel] = start + shift
            if carry:
                # Absolute, not incremental: the velocity given here is integrated
                # by the step that follows, so an increment would be counted twice.
                velocity = (travel * (blend - done) / self.dt, 0.0, 0.0)
                self._pin(everything, cloth + shift, velocity)
            done = blend
            yield

    def _pose_tail(self, angle: float) -> None:
        """Hold the bag's tail ``angle`` radians off the roof, negative is down.

        The tail is hinged along the mouth end of the roof, so its far end
        swings about the hinge.
        """
        hinge = np.asarray(BAG_TAIL_HINGE)
        half = 0.5 * BAG_TAIL_LENGTH
        gid = self._g["bag_tail"]
        self.model.geom_pos[gid] = hinge + half * np.array([-math.cos(angle), 0.0, math.sin(angle)])
        self.model.geom_quat[gid] = [math.cos(0.5 * angle), 0.0, math.sin(0.5 * angle), 0.0]

    def _close_bag(self, seconds: float):
        steps = self._steps(seconds)
        for index in range(steps):
            self._pose_tail(BAG_TAIL_CLOSED * smoothstep((index + 1) / steps))
            yield

    def _seal_and_tag(self):
        """Lower the seal bar and the stamp together, dwell, lift.

        On contact the mouth seam shows, and the label moves from the stamp
        to the bag.
        """
        model, data = self.model, self.data
        bar, stamp, g = self._seal_bar, self._stamp, self._g
        yield from self._move_presses(SEAL_BAR_Z, STAMP_Z, 1.2)

        model.geom_rgba[g["bag_seam"]] = (0.70, 0.84, 0.95, 0.85)
        model.geom_rgba[g["stamp_sticker"], 3] = 0.0
        model.geom_rgba[g["stamp_antenna"], 3] = 0.0
        model.geom_rgba[g["bag_sticker"], 3] = 1.0
        model.geom_rgba[g["bag_antenna"], 3] = 1.0
        cold = self._rgba0["seal_bar_head"]
        hot = np.array([1.0, 0.45, 0.15, 1.0])
        dwell = 1.6
        for index in range(self._steps(dwell)):
            glow = math.sin(math.pi * min(1.0, index * self.dt / dwell))
            model.geom_rgba[g["seal_bar_head"]] = cold + (hot - cold) * glow
            yield
        model.geom_rgba[g["seal_bar_head"]] = cold

        yield from self._move_presses(PRESS_HOVER_Z, PRESS_HOVER_Z, 1.0)

    def _move_presses(self, bar_z: float, stamp_z: float, seconds: float):
        bar, stamp = self._seal_bar, self._stamp
        bar0, stamp0 = float(self.data.mocap_pos[bar][2]), float(self.data.mocap_pos[stamp][2])
        steps = self._steps(seconds)
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            self.data.mocap_pos[bar][2] = bar0 + (bar_z - bar0) * blend
            self.data.mocap_pos[stamp][2] = stamp0 + (stamp_z - stamp0) * blend
            yield

    def _convey(self):
        """Run belt 2 until the bag is in the carton."""
        while self.data.qpos[self._bag_qadr + 2] > BOXED_Z:
            self.belt2_speed = min(BELT2_SPEED, self.belt2_speed + BELT_ACCEL * self.dt)
            yield
        self.belt2_speed = 0.0
        yield from self._hold("BOXED", "", 1.0, quiet=True)

    def _flip(self, flap: Flap):
        """Swing a flap over, carrying its cloth, let go, swing back.

        The hinge sits under the plates, clear of the cloth. It rides up as the
        flap swings, so the flap lands on the layers already folded instead of
        cutting through them.
        """
        mocap = self._mocap[flap.body]
        hinge = self.data.mocap_pos[mocap].copy()
        axis = np.asarray(flap.axis)
        up = np.array([0.0, 0.0, 1.0])

        pos = self.positions()
        ids = np.flatnonzero(flap.carries(pos, hinge))
        arm = pos[ids] - hinge

        risen = 0.0
        for angle, rate in self._swing(0.0, math.pi, flap.over):
            rise = flap.lift * _rise(angle)
            pivot = hinge + rise * up
            self._set_flap(mocap, axis, angle, pivot)
            moved = _rotate(arm, axis, angle)
            climb = (rise - risen) / self.dt * up
            self._pin(ids, pivot + moved, rate * np.cross(axis, moved) + climb)
            risen = rise
            yield
        # Set down still, at the top of the swing.
        self._pin(ids, hinge + flap.lift * up + _rotate(arm, axis, math.pi), None)

        # Swinging back empty, the flap's edge by the hinge would sweep
        # through the crease it just made and trap it underneath.
        geom = self._flap_geom[flap.body]
        affinity = int(self.model.geom_conaffinity[geom])
        self.model.geom_conaffinity[geom] = 0
        for angle, _ in self._swing(math.pi, 0.0, flap.back):
            self._set_flap(mocap, axis, angle, hinge + flap.lift * _rise(angle) * up)
            yield
        self._set_flap(mocap, axis, 0.0, hinge)
        self.model.geom_conaffinity[geom] = affinity

    def _swing(self, start: float, end: float, seconds: float):
        steps = self._steps(seconds)
        previous = start
        for index in range(steps):
            angle = start + (end - start) * smoothstep((index + 1) / steps)
            yield angle, (angle - previous) / self.dt
            previous = angle

    def _set_flap(self, mocap: int, axis: np.ndarray, angle: float, pivot: np.ndarray) -> None:
        half = 0.5 * angle
        self.data.mocap_quat[mocap] = [math.cos(half), *(math.sin(half) * axis)]
        self.data.mocap_pos[mocap] = pivot

    def _steps(self, seconds: float) -> int:
        return max(1, int(round(seconds / self.dt)))


def _rise(angle: float) -> float:
    """How far up its lift a flap's hinge is, 0 to 1.

    Half of it by upright: the flap's edge by the pin then clears the rail,
    and the flap moves as if hinged half its lift above the plates.
    """
    return 0.5 * (1.0 - math.cos(angle))


def _rotate(points: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """Rotate points about a unit axis through the origin (Rodrigues)."""
    cos, sin = math.cos(angle), math.sin(angle)
    return (
        points * cos
        + np.cross(axis, points) * sin
        + np.outer(points @ axis, axis) * (1.0 - cos)
    )


class FollowCam:
    """A free camera that drifts along with the shirt.

    Looks at the shirt from the aisle side, high enough to see the platen
    come down. Only the look-at point moves, and it is smoothed, so the
    camera glides rather than snapping when the shirt is reloaded at the
    infeed. Angle and distance are set once, so a window can still orbit and
    zoom without the follow fighting it.
    """

    DISTANCE = 2.0
    AZIMUTH = 82.0  # along +y from the aisle, a little off-axis to clear the near column
    ELEVATION = -34.0
    TAU = 0.6  # seconds for the look-at to close ~63% of the gap

    def __init__(self) -> None:
        import mujoco

        self.lookat = np.array([SPAWN_X, 0.0, SURFACE_Z + 0.08])
        self.cam = mujoco.MjvCamera()
        self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.setup(self.cam)
        self._started = False

    def setup(self, cam) -> None:
        """Give ``cam`` this view's angle and distance (once)."""
        import mujoco

        cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        cam.distance = self.DISTANCE
        cam.azimuth = self.AZIMUTH
        cam.elevation = self.ELEVATION
        cam.lookat[:] = self.lookat

    def track(self, cloth: np.ndarray, dt: float) -> None:
        """Move the look-at toward the shirt; ``dt`` is time since the last call."""
        rest_z = SURFACE_Z + 0.08
        goal = np.array([cloth[:, 0].mean(), 0.0, 0.65 * rest_z + 0.35 * cloth[:, 2].mean()])
        if not self._started:
            self.lookat[:] = goal
            self._started = True
        else:
            self.lookat += (goal - self.lookat) * (1.0 - math.exp(-dt / self.TAU))
        self.cam.lookat[:] = self.lookat

    def aim(self, cam) -> None:
        """Point another camera (a window's) at the shirt, leaving its angle alone."""
        cam.lookat[:] = self.lookat


def main() -> None:
    parser = argparse.ArgumentParser(description="XFOLD line: belt, press, folder")
    parser.add_argument("--cycles", type=int, default=0, help="0 keeps going")
    parser.add_argument("--headless", action="store_true", help="no window, as fast as it can")
    add_garment_arguments(parser)
    parser.add_argument(
        "--shots", default="", help="headless: save a frame per stage into this directory"
    )
    parser.add_argument(
        "--camera",
        default="follow",
        help="follow (tracks the shirt) or a fixed one: overview, press_cam, fold_cam",
    )
    args = parser.parse_args()
    chosen = garment_from_args(
        args, interactive=not args.headless, current=shirt_config().garment
    )
    if chosen:
        rewrite_argv_garment(chosen)
        args.garment = chosen

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
    line = Line(model, data, repeat=args.cycles == 0)
    print(
        f"XFOLD line  garment={cfg.garment} ({cfg.mesh})  {LINE_PATH}",
        flush=True,
    )

    def done() -> bool:
        return line.finished or (args.cycles and line.cycles > args.cycles)

    if args.headless:
        _run_headless(line, args.shots, args.camera, done)
        return

    import mujoco.viewer

    with mujoco.viewer.launch_passive(model, data) as viewer:
        follow = FollowCam() if args.camera == "follow" else None
        if follow is not None:
            follow.setup(viewer.cam)
        else:
            viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
            viewer.cam.fixedcamid = model.camera(args.camera).id
        per_frame = max(1, round((1.0 / 60.0) / line.dt))
        while viewer.is_running() and not done():
            started = time.perf_counter()
            for _ in range(per_frame):
                line.step()
            if follow is not None:
                follow.track(line.positions(), per_frame * line.dt)
                follow.aim(viewer.cam)
            viewer.sync()
            time.sleep(max(0.0, per_frame * line.dt - (time.perf_counter() - started)))


def _run_headless(line: Line, shots: str, camera: str, done) -> None:
    renderer = None
    if shots:
        import mujoco

        Path(shots).mkdir(parents=True, exist_ok=True)
        renderer = mujoco.Renderer(line.model, height=720, width=1280)

    follow = FollowCam() if camera == "follow" else None
    every = 25  # steps between camera updates: 50 ms of sim time
    frame = 0
    count = 0
    previous = None
    started = time.perf_counter()
    while not done():
        line.step()
        count += 1
        if follow is not None and count % every == 0:
            follow.track(line.positions(), every * line.dt)
        # One frame as each stage ends, plus a few through each flip.
        label = (line.stage, line.cycles)
        flipping = line.stage == "FOLD" and line.data.time % 0.4 < line.dt
        if renderer is not None and (label != previous or flipping):
            from PIL import Image

            renderer.update_scene(line.data, camera=camera if follow is None else follow.cam)
            path = Path(shots) / f"{frame:03d}_{line.stage.lower()}.png"
            Image.fromarray(renderer.render()).save(path)
            frame += 1
        previous = label
    wall = time.perf_counter() - started
    print(f"{line.data.time:.1f} s simulated in {wall:.1f} s", flush=True)


if __name__ == "__main__":
    main()
