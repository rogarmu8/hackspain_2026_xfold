"""The line: dual-arm align -> belt -> press -> flap folder -> bagger -> carton.

1. A garment is laid on the infeed. If the selector's "skewed" place is
   on, any cloth type is dropped at a random heading and a bit crumpled. Two
   robot arms, one each side of the infeed belt, put a suction wrist on each
   half of it, lift it off the belt, swing it round until the collar leads
   downstream and lay it back down. They correct the position, not the
   creases: the wrinkles stay until the press.
2. The belt carries it under the press and stops. The platen comes down on
   the belt itself, steams the wrinkles out, and lifts.
3. The belt runs on to the QC camera. After the product shot, an arm
   mounted on the camera's own post — which stands at the x-midpoint of the
   two totes, so both are the same reach away — carries stained shirts into a
   stained tote and torn shirts into a broken tote and drops them, then the
   cycle ends. Clean and rotated garments continue to the folder.
4. The folder flips its flaps, FlipFold style: left side, right side, then
   the hem half up over the collar half. It is the quickest station on the
   line: each flap carries its cloth rigidly and sets the layer down still,
   so the swings run at machine speed rather than at the solver's.
5. Meanwhile the bagger gets a bag ready. A vacuum picker takes the top one
   off a magazine of flat, pre-made bags (three sides welded) and lays it on
   belt 2, mouth toward the folder. A suction cup lifts the top lip, an air
   knife blows the bag open and two spreader fingers hold the mouth square.
6. The plate the pack sits on is a peel. It runs out of the folder like a
   drawer on telescopic slides, into the bag like a pizza into an oven. Two
   lifters push its back end up, so it tips on its nose and the pack's front
   lands on the bag floor, and it slides back out from under the pack.
7. The opener lets go and the film settles on the pack. Belt 2 indexes the
   bag to the seal station, where a seal bar presses the mouth flat and
   welds it while a stamp puts the label on the top.
8. Belt 2 carries the bag off its end and it drops into a carton.

A peel or a flap is a mocap body, which the contact solver sees as standing
still, so it cannot drag cloth by friction: whatever it carries is moved
with it explicitly, and nothing it slides out from under is dragged back.
The bag is carried kinematically until it lies on belt 2, and its films are
visual geoms that the controller shapes: flat, blown open, settled on the
pack, pressed shut at the mouth. Once the peel is out, the shirt is fixed
inside the bag's frame every step, so it travels, falls and lands with the
bag. The cloth is not simulated as touching the bag's films.

The belt is not a moving body. Cloth lying on it is given the belt's speed
each step, which is what a belt does to something that does not slip. The
align arms work the same way: what the pair holds is written onto the cloth
every step, so the sheet rides between the cups without the solver having to
resolve two grippers gripping. The
folder's infeed runs with the belt while it takes the shirt over: cloth
cannot be pushed, so a folder that only let the belt shove the shirt onto
it would get a heap, not a shirt.

A flap carries the cloth lying on it rigidly while it swings, the way a
real flap's friction does, and lets go at the top of the swing. The cloth
does not collide with itself in MuJoCo, so ClothLayers keeps the folded
layers apart from then on.

With a window:  moon run sim:run              # type, condition, then square / skewed
                moon run sim:run -- -g tee
                moon run sim:run -- -g jersey --skewed  # any cloth, any heading + wrinkles
                moon run sim:run -- -g dress_damaged --skewed
Headless:       pixi run -e mujoco python -P -m xfold.line --headless --cycles 1 -g jersey
Catalogue:      moon run sim:run -- --list-garments
"""

from __future__ import annotations

import argparse
import math
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .garments import (
    add_garment_arguments,
    base_garment,
    garment_from_args,
    qc_reject_bin,
    rewrite_argv_garment,
)
from .platform import reexec_under_mjpython
from .self_collide import ClothLayers
from .align import AlignStation, _heading, _quat_z_to, two_link_ik
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

LINE_PHASES = (
    {"state": "LOAD", "label": "Rotate", "station": "infeed"},
    {"state": "ORIENT", "label": "Rotate", "station": "orient"},
    {"state": "TO_PRESS", "label": "Press", "station": "belt"},
    {"state": "PRESS", "label": "Press", "station": "press"},
    {"state": "TO_QC", "label": "Press", "station": "belt"},
    {"state": "PHOTO", "label": "Press", "station": "qc"},
    {"state": "SORT", "label": "Press", "station": "qc"},
    {"state": "TO_FOLDER", "label": "Fold", "station": "belt"},
    {"state": "FOLD", "label": "Fold", "station": "folder"},
    {"state": "INSERT", "label": "Bag", "station": "bagger"},
    {"state": "TO_SEAL", "label": "Pack", "station": "belt2"},
    {"state": "SEAL", "label": "Pack", "station": "sealer"},
    {"state": "TO_CARTON", "label": "Pack", "station": "belt2"},
    {"state": "DONE", "label": "Pack", "station": "outfeed"},
)
_PHASES = {phase["state"]: phase for phase in LINE_PHASES}

# Belt top and folder plates, from line.xml.
SURFACE_Z = 0.562
BELT_X = (-2.00, 0.30)
# One slat run over both decks: the infeed is a plain belt now, so the slats
# scroll from the infeed roller to belt 1's out roller.
BELT_SLAT_X = (-2.10, 0.30)
# The folder's boards, hem edge to collar edge.
FOLDER_X = (0.305, 0.98)
# The hem stops this far onto the folder, not hanging off its edge.
HEM_INSET = 0.012
BELT_SPEED = 0.35  # m/s
BELT_ACCEL = 0.6  # m/s^2, both speeding up and braking
# Cloth this close above the belt top rides with it.
ON_BELT = 0.03
# Below this the garment is on the floor, not on any machine: whatever the
# line was doing, it lost the shirt (running fast enough makes this happen).
DROPPED_Z = SURFACE_Z - 0.25
# Phases where the garment belongs on a belt, the press or the folder, so
# finding it on the floor means the line lost it. Afterwards it is sealed in
# the bag and rides it down into the carton, and at SORT the QC arm is
# carrying it over a tote on purpose.
CARRIED_PHASES = frozenset(
    {"LOAD", "ORIENT", "TO_PRESS", "PRESS", "TO_QC", "PHOTO", "TO_FOLDER", "FOLD"}
)

# Operator place (selector "skewed"): a T on the belt, pose drawn each cycle.
# Yaw is any heading, plus visible crumple. The align arms square the
# heading; the press irons the wrinkles out.
SKEW_X_MAX = 0.05
SKEW_Y_MAX = 0.05
BELT_HALF_Y = 0.475
# QC station: where the belt stops the pressed shirt for its product shot.
# Downstream of the press and far enough from the belt's end (0.30) that the
# whole 0.65 m of shirt stays on the belt.
QC_X = -0.20
# The reject arm hangs off the QC camera's own post, on a collar at z = 1.05.
# The post stands at x = QC_X, which is the midpoint of the two totes
# (x = -0.70 and x = +0.30), so both are the same 0.99 m reach from the
# shoulder and so is the belt under the camera. Scripted 2-link IK poses the
# mocap links so the cup is never a free-floating pad; because the shoulder
# is on the post, no pose can foul it and there is no detour to plan.
QC_ARM_S = np.array([QC_X, 0.66, 1.05])
QC_ARM_L1 = 0.55
QC_ARM_L2 = 0.58
QC_ARM_WRIST = 0.10
# Park tucked back behind the post, outside qc_cam's cone (half-width there
# is ~0.27 m), so the arm is not in the product shot.
QC_CUP_HOME = np.array([QC_X, 0.92, 0.98])
QC_CUP_LIFT_Z = 1.05
QC_CUP_GRAB_Z = SURFACE_Z + 0.045
QC_BIN_XY = {"stained": np.array([-0.70, 1.50]), "broken": np.array([0.30, 1.50])}
# Hover above the tote mouth so the sheet hangs into the opening; release
# still clear of the walls (top ~0.34 m) so the fabric falls in, not stuffed.
QC_BIN_HOVER_Z = 0.92
QC_BIN_DROP_Z = 0.70
QC_SUCTION_R = 0.07
QC_DROP_WATCH_S = 1.8
FLASH_RISE = 0.12  # seconds, dark -> full
FLASH_HOLD = 0.10  # seconds at full; the shot is taken in here
FLASH_FALL = 0.35  # seconds, full -> dark
# The station works like a photo booth: the line's own lamps dip, then the
# flash fires. Two different dips, because they are for two different eyes.
#
# QC_DIP is what anybody watching sees: the station's own lamps come down a
# little as the flash rises, enough to read as "a picture is being taken".
# It leaves the headlight — which is MuJoCo's camera-mounted lamp, and so
# most of what lights the hall in any view — completely alone, so the rest of
# the screen keeps its brightness. Dipping everything to a fifth, which is
# what this used to do, blacked the whole plant out for half a second.
#
# QC_PHOTO_DIP is the exposure the product shot itself is taken at, and it is
# held for exactly one capture (``_photo_exposure``). The wide-shot lighting
# is far too hot for a white garment seen from 1 m straight up — measured on
# the QC frame, 28% of it clips to pure white, taking the print and any stain
# with it — so the shot needs its own stop. Because the capture is synchronous
# and runs under the session lock, no viewport frame is ever rendered while it
# is applied: the picture gets the dip, the screen does not.
QC_DIP = 0.80  # station lamps while the flash is up, as a fraction of normal
QC_PHOTO_DIP = 0.45  # lamps and headlight for the capture alone
FLASH_DIFFUSE = (0.34, 0.34, 0.33)
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
# The bag's centre at the load station and at the seal station, and its
# half-length.
BAG_X = 1.32
SEAL_X = 1.78
BAG_HALF_LENGTH = 0.30
# The shirt's leading edge stops this far short of the bag's closed end.
BAG_END_MARGIN = 0.02

# Where the bag's centre is: on top of the magazine's stack, carried over the
# belt by the picker, and lying on belt 2.
MAG_Y = 0.66
MAG_BAG_Z = 0.5676
CARRY_BAG_Z = 0.72
BELT2_BAG_Z = 0.586
# Picker head (its cups' lips) parked, and its carriage's height on the beam.
PICKER_PARK_Z = 0.78
PICKER_CARRIAGE_Z = 1.017

# The bag's films, in the bag's frame: the floor film's centre height, film
# thickness, and how tall the bag stands flat, blown open, and at least once
# settled on a pack.
BAG_FLOOR = -0.0372
FILM = 0.0008
BAG_FLAT = 0.002
BAG_OPEN = 0.11
BAG_SETTLED_MIN = 0.02
# The roof and the gussets are BAG_PANELS rings across the bag's length
# (line.xml), so the film can take one height per ring instead of one height
# for the whole bag. BAG_ROOF_X is where the roof starts and ends, in the
# bag's frame: the mouth-end edge is the tail's hinge.
BAG_PANELS = 7
BAG_ROOF_X = (-0.19, 0.30)
# Film clears the cloth under it by this much, and bridges a dip between two
# high points rather than following the cloth down into it — it is a sheet,
# not shrink wrap. BAG_FILM_SAG is how far into such a dip it does fall.
BAG_FILM_LIFT = 0.004
BAG_FILM_SAG = 0.006
# Film alpha (line.xml's "film" material) blown open and settled on a pack:
# pulled down on the product it reads denser than it does standing empty.
BAG_FILM_ALPHA = (0.26, 0.46)
# The roof ends at the tail's hinge. The tail runs to the seal line and a lip
# runs on from there to the mouth. Open, the mouth cup holds the tail flared
# up by TAIL_FLARE; closed, the seal bar has pressed it down to the floor.
TAIL_HINGE_X = -0.19
TAIL_LENGTH = 0.078
LIP_LENGTH = 0.032
TAIL_FLARE = 0.30
# Where along the tail the mouth cup holds it, from the hinge.
MOUTH_CUP_ON_TAIL = 0.07
MOUTH_CUP_PARK_Z = 0.74
# Spreader fingers: parked tip height, tip height in the mouth, and their y
# when they go in and when they have pushed out to hold the mouth square.
FINGER_PARK_Z = 0.74
FINGER_DOWN_Z = 0.556
FINGER_IN_Y = 0.19
FINGER_OUT_Y = 0.232

# Peel: how far its nose tips down in the bag to put the pack's front on the
# bag floor. It tips about the bottom of its front edge, which is PEEL_HALF
# ahead of and PEEL_UNDER below its origin. On the way out it levels off
# before its back end is back in the folder.
PEEL_TILT = math.radians(4.0)
PEEL_HALF = 0.16875
PEEL_UNDER = 0.006
PEEL_LEVEL_AT = 0.35  # m out, fully level again
# The lifters under the hinge rails' ends: x, and the rods' bottom and top
# at rest (the middle slide's underside).
LIFTER_X = 0.965
LIFTER_BASE_Z = 0.498
LIFTER_REST_Z = 0.543

# Seal bar and stamp hover heights. Their pressed heights come from where
# the bag is.
PRESS_HOVER_Z = 0.76
SEAL_BAR_HALF = 0.010
STAMP_UNDER = 0.0132  # stamp origin to the label's face
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


# In folding order. The folder is the fastest machine on the line: a flap
# carries its cloth rigidly, so the swing is not waiting on the solver to
# resolve anything, and it sets its layer down still at the top. Roughly half
# the times these started at; the hem flap keeps the longest swing because it
# lifts the most (lift=0.060) and lands on two layers.
FLAPS = (
    Flap("flap_left", (1.0, 0.0, 0.0), over=0.55, back=0.32, lift=0.028),
    Flap("flap_right", (-1.0, 0.0, 0.0), over=0.55, back=0.32, lift=0.036),
    Flap("flap_bottom", (0.0, 1.0, 0.0), over=0.65, back=0.36, lift=0.060),
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
    # One bag label per clean SKU: a torn / stained twin ships in its base
    # SKU's bag, so key the sticker off the base garment, not the variant.
    label = f"label_{base_garment(shirt_config().garment).key}"
    if spec.material(label) is None:
        label = "label_tee"
    for name in ("bag_sticker", "stamp_sticker"):
        spec.geom(name).material = label
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


def skew_pose(seed: int) -> tuple[float, float]:
    """Yaw (rad) and lateral y (m) for a flat, rotated belt drop.

    The shirt stays on the belt plane; only heading and a small side nudge
    vary. Same seed ⇒ same pose.
    """
    import random

    rng = random.Random((int(seed) * 13 + 5) & 0xFFFFFFFF)
    yaw = rng.uniform(-math.pi, math.pi)
    y = rng.uniform(-SKEW_Y_MAX, SKEW_Y_MAX)
    return yaw, y


def flat_shirt(center_x: float, *, yaw: float = 0.0, y: float = 0.0) -> np.ndarray:
    """World vertices of the shirt lying flat on the belt, collar toward +x.

    ``yaw`` is rotation about +Z (radians). ``y`` is a lateral shift. A
    square drop is yaw=0, y=0; a skewed drop uses ``skew_pose(seed)``.
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


@dataclass(frozen=True)
class OperatorPlace:
    world: np.ndarray
    yaw: float
    dx: float
    dy: float


def _slide_onto_belt(world: np.ndarray) -> np.ndarray:
    """Shift the T so as much of it as possible sits on the infeed."""
    out = world.copy()
    y_min, y_max = float(out[:, 1].min()), float(out[:, 1].max())
    if y_min < -BELT_HALF_Y:
        out[:, 1] += -BELT_HALF_Y - y_min
    if y_max > BELT_HALF_Y:
        out[:, 1] += BELT_HALF_Y - y_max
    y_min, y_max = float(out[:, 1].min()), float(out[:, 1].max())
    if y_min < -BELT_HALF_Y or y_max > BELT_HALF_Y:
        out[:, 1] -= 0.5 * (y_min + y_max)
    x_min, x_max = float(out[:, 0].min()), float(out[:, 0].max())
    if x_min < BELT_X[0]:
        out[:, 0] += BELT_X[0] - x_min
    if x_max > BELT_X[1]:
        out[:, 0] += BELT_X[1] - x_max
    return out


def _crumple_shirt(
    world: np.ndarray, rng: np.random.Generator, *, amount: float | None = None
) -> np.ndarray:
    """A new random fold pattern every call. Always a little crumple, never a heap.

    ``amount`` 0.4 is a square lay that still looks handled; 1.0 is a messy dump.
    Drawn from the rng when omitted.
    """
    if amount is None:
        amount = float(rng.uniform(0.55, 1.15))
    amount = float(np.clip(amount, 0.25, 1.4))
    out = world.copy()
    mid = out.mean(axis=0)
    rel = out - mid
    z0 = SURFACE_Z + SHIRT_RADIUS
    nfold = int(rng.integers(2, 6) if amount >= 0.7 else rng.integers(1, 4))
    for _ in range(nfold):
        ang = float(rng.uniform(0.0, math.pi))
        nx, ny = math.cos(ang), math.sin(ang)
        off = float(rng.uniform(-0.22, 0.22))
        freq = float(rng.uniform(8.0, 34.0))
        phase = float(rng.uniform(0.0, 2.0 * math.pi))
        amp_z = float(rng.uniform(0.006, 0.018)) * amount
        amp_xy = float(rng.uniform(0.004, 0.014)) * amount
        width = float(rng.uniform(0.18, 0.42))
        axis = rel[:, 0] * nx + rel[:, 1] * ny - off
        wave = np.sin(freq * axis + phase)
        envelope = np.exp(-((axis / width) ** 2))
        ridge = 0.25 + 0.75 * np.abs(wave) if rng.random() < 0.6 else 0.5 + 0.5 * wave
        out[:, 2] += amp_z * ridge * envelope
        out[:, 0] += amp_xy * wave * envelope * nx
        out[:, 1] += amp_xy * wave * envelope * ny
    ndimple = int(rng.integers(1, 5))
    for _ in range(ndimple):
        cx = float(rng.uniform(-0.22, 0.22))
        cy = float(rng.uniform(-0.28, 0.28))
        sigma = float(rng.uniform(0.05, 0.16))
        amp = float(rng.uniform(0.005, 0.014)) * amount
        bump = np.exp(-((rel[:, 0] - cx) ** 2 + (rel[:, 1] - cy) ** 2) / (2.0 * sigma**2))
        out[:, 2] += amp * bump
        if rng.random() < 0.5:
            out[:, 0] += 0.35 * amp * bump * np.sign(rel[:, 0] - cx + 1e-9)
            out[:, 1] += 0.35 * amp * bump * np.sign(rel[:, 1] - cy + 1e-9)
    ncorner = int(rng.integers(0, 3))
    for _ in range(ncorner):
        sx = float(rng.choice((-1.0, 1.0)))
        sy = float(rng.choice((-1.0, 1.0)))
        lift = float(rng.uniform(0.006, 0.016)) * amount
        corner = np.clip(sx * rel[:, 0] + sy * rel[:, 1], 0.0, None)
        scale = float(np.max(corner)) + 1e-9
        out[:, 2] += lift * (corner / scale) ** 2
    out[:, 2] = np.maximum(out[:, 2], z0)
    span = float(out[:, 2].max() - z0)
    lo, hi = 0.010 + 0.006 * amount, 0.026 + 0.020 * amount
    if span < lo:
        out[:, 2] = z0 + (out[:, 2] - z0) * (lo / max(span, 1e-6))
    elif span > hi:
        out[:, 2] = z0 + (out[:, 2] - z0) * (hi / span)
    return out


def operator_shirt(center_x: float, rng: np.random.Generator) -> OperatorPlace:
    """Random operator lay: any heading, a shift, visible wrinkles.

    Drawn again every cycle. The dual-belt turner yaws it collar-downstream;
    the press irons the crumple out.
    """
    yaw = float(rng.uniform(-math.pi, math.pi))
    dy = float(rng.uniform(-SKEW_Y_MAX, SKEW_Y_MAX))
    dx = float(rng.uniform(-SKEW_X_MAX, SKEW_X_MAX))
    world = _slide_onto_belt(flat_shirt(center_x + dx, yaw=yaw, y=dy))
    world = _slide_onto_belt(
        _crumple_shirt(world, rng, amount=float(rng.uniform(0.75, 1.25)))
    )
    dx = float(world[:, 0].mean() - center_x)
    dy = float(world[:, 1].mean())
    return OperatorPlace(world, yaw, dx, dy)


class Line:
    """Runs the line one physics step at a time: ``step()`` forever.

    The cycle is a generator that sets this step's commands and yields; the
    viewer, a headless run and the dashboard viewport all just call step().
    """

    # Machine speed multiplier; see __init__. Here as well so the helpers work
    # on a Line put together piecemeal (scripts/test-sim-observability.py).
    speed = 1.0

    def __init__(
        self,
        model,
        data,
        repeat: bool = True,
        log=print,
        *,
        skewed: bool = False,
        flat: bool = False,
        seed: int = 0,
        speed: float = 1.0,
        garment: str | None = None,
        on_photo=None,
        on_event=None,
    ) -> None:
        import mujoco

        self._mujoco = mujoco
        self.model = model
        self.data = data
        self.repeat = repeat
        self.log = log
        # How much faster than nominal the machinery runs. Every duration is
        # divided by it and every speed multiplied, so the line does the same
        # motions in less time: belts and accelerations included. Cloth is not
        # asked to keep up — past some speed it slides off a belt or misses
        # the folder, and the cycle ends as a drop (see ``_dropped``).
        self.speed = max(0.1, float(speed))
        # The SKU this cycle is for. Taken once: the active garment is
        # process-wide state, and the QC decision must not follow a later
        # change (the bridge runs several cycles at a time).
        self.garment = garment or shirt_config().garment
        self.on_event = on_event
        self.phase = "LOAD"
        self.skewed = skewed
        self.flat = flat
        self.seed = int(seed)
        self._rng = np.random.default_rng(self.seed if self.seed else None)
        self._place: OperatorPlace | None = None
        self._skew_yaw = 0.0
        self._skew_y = 0.0
        # Called once, at the top of the flash, to take the product shot.
        # None (the windowed run) still fires the flash; nothing records it.
        self.on_photo = on_photo
        self._flash = [int(model.light(n).id) for n in ("qc_flash_l", "qc_flash_r")]
        self._flash_level = 0.0
        self._bulb = [int(model.geom(n).id) for n in ("qc_bulb_l", "qc_bulb_r")]
        self._bulb_rgba = model.geom_rgba[self._bulb].copy()
        self._scene_lights = [i for i in range(model.nlight) if i not in self._flash]
        self._light0 = model.light_diffuse.copy()
        self._head0 = (
            np.array(model.vis.headlight.diffuse, dtype=float).copy(),
            np.array(model.vis.headlight.ambient, dtype=float).copy(),
        )
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
        self._align = AlignStation(
            model, data, qadr=self._qadr, rest=self._rest, dadr=self._dadr
        )

        self._slats2 = [
            model.geom(i).id
            for i in range(model.ngeom)
            if model.geom(i).name.startswith("belt2_slat_")
        ]
        self._slat2_x0 = model.geom_pos[self._slats2, 0].copy()
        mocap = {
            name: int(model.body(name).mocapid[0])
            for name in (
                "peel",
                "seal_bar",
                "stamp",
                "picker_head",
                "picker_carriage",
                "mouth_cup",
                "finger_l",
                "finger_r",
            )
        }
        self._peel = mocap["peel"]
        self._seal_bar = mocap["seal_bar"]
        self._stamp = mocap["stamp"]
        self._qc_cup = int(model.body("qc_cup").mocapid[0])
        self._qc_yaw = int(model.body("qc_arm_yaw").mocapid[0])
        self._qc_upper = int(model.body("qc_arm_upper").mocapid[0])
        self._qc_fore = int(model.body("qc_arm_fore").mocapid[0])
        self._qc_local: np.ndarray | None = None
        self._qc_ids: np.ndarray | None = None
        self._picker = mocap["picker_head"]
        self._carriage = mocap["picker_carriage"]
        self._mouth_cup = mocap["mouth_cup"]
        self._fingers = ((mocap["finger_l"], 1.0), (mocap["finger_r"], -1.0))
        self._slide = int(model.body("peel_slide").mocapid[0])
        self._peel_home = model.body("peel").pos.copy()
        self._slide_home = model.body("peel_slide").pos.copy()
        self._peel_pivot = self._peel_home + (PEEL_HALF, 0.0, -PEEL_UNDER)
        self._peel_shift = 0.0
        self._peel_tilt = 0.0
        self._lifter_rods = [model.geom(name).id for name in ("peel_lifter_rod_l", "peel_lifter_rod_r")]
        bag = model.body("bag")
        joint = int(bag.jntadr[0])
        self._bag = bag.id
        self._bag_qadr = int(model.jnt_qposadr[joint])
        self._bag_dadr = int(model.jnt_dofadr[joint])
        self._g = {
            name: model.geom(name).id
            for name in (
                *(f"bag_roof_{i}" for i in range(BAG_PANELS)),
                *(f"bag_side_l_{i}" for i in range(BAG_PANELS)),
                *(f"bag_side_r_{i}" for i in range(BAG_PANELS)),
                *(f"bag_crimp_{i}" for i in range(4)),
                "bag_floor",
                "bag_end",
                "bag_weld_end",
                "bag_hang_patch",
                "bag_hang_hole",
                "bag_tail",
                "bag_lip",
                "bag_tail_side_l",
                "bag_tail_side_r",
                "bag_seam",
                "bag_sticker",
                "stamp_sticker",
                "seal_bar_head",
                "air_jet",
            )
        }
        # Roof and gusset rings, mouth end first, and their x edges.
        self._panels = [
            (
                self._g[f"bag_roof_{i}"],
                self._g[f"bag_side_l_{i}"],
                self._g[f"bag_side_r_{i}"],
            )
            for i in range(BAG_PANELS)
        ]
        self._panel_edges = np.linspace(*BAG_ROOF_X, BAG_PANELS + 1)
        # Every geom made of the plain film, so the whole bag tightens
        # together. Writing rgba would otherwise drop these geoms off their
        # material and render them MuJoCo's default grey, so the material's
        # own colour is carried over and only the alpha is driven.
        self._film_alpha = [self._g[f"bag_roof_{i}"] for i in range(BAG_PANELS)]
        self._film_alpha += [self._g[f"bag_side_l_{i}"] for i in range(BAG_PANELS)]
        self._film_alpha += [self._g[f"bag_side_r_{i}"] for i in range(BAG_PANELS)]
        self._film_alpha += [
            self._g[n] for n in
            ("bag_floor", "bag_end", "bag_tail", "bag_lip",
             "bag_tail_side_l", "bag_tail_side_r")
        ]
        self._film_rgb = np.array(
            model.mat_rgba[int(model.geom_matid[self._g["bag_roof_0"]])][:3], dtype=float
        )
        self._rgba0 = {name: model.geom_rgba[gid].copy() for name, gid in self._g.items()}
        self._bag_local: np.ndarray | None = None  # shirt vertices in the bag's frame
        # Where the bag's centre is held while it is not on the belt, or None.
        self._bag_held: np.ndarray | None = None
        # Film height per panel; _bag_h is the height at the mouth, which is
        # what the tail hinges off and what the seal bar has to close.
        self._bag_film = np.full(BAG_PANELS, BAG_FLAT)
        self._bag_h = BAG_FLAT
        self._bag_tail = 0.0
        self._bagger = None  # the bagger's own sequence, run alongside the cycle
        self._bag_ready = False

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
        # packed | stained | broken — where the shirt went, not process success.
        self.outcome: str | None = None
        self._set_arm(QC_CUP_HOME)
        self._program = self._run()

    # --- stepping -----------------------------------------------------

    def step(self) -> None:
        """Advance the line by one physics step."""
        if not self.finished:
            try:
                next(self._program)
            except StopIteration:
                self.finished = True
            if not self.finished and self._dropped():
                pos = self.positions()
                self._enter(
                    "DONE",
                    f"garment off the line at {self.speed:g}x, {pos[:, 2].max() - SURFACE_Z:+.2f} m "
                    f"from the surface; cycle abandoned",
                    phase="DONE",
                    operation="DROPPED",
                )
                self.outcome = "dropped"
                self.finished = True
        if self._bagger is not None:
            try:
                next(self._bagger)
            except StopIteration:
                self._bagger = None
        if self.belt_speed != 0.0 and self._align._world is not None:
            dx = self.belt_speed * self.dt
            self._align._world[:, 0] += dx
            self._align._center[0] += dx
        self._align.apply()
        self._drive_belt()
        self._drive_belt2()
        self._steam.follow(self.data)
        self._mujoco.mj_step(self.model, self.data)
        self._hold_bag()
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
        span = BELT_SLAT_X[1] - BELT_SLAT_X[0]
        self.model.geom_pos[self._slats, 0] = (
            BELT_SLAT_X[0] + (self._slat_x0 - BELT_SLAT_X[0] + self._belt_travel) % span
        )
        if self._align._world is not None or self._align.holding:
            return
        pos = self.positions()
        riding = (
            (pos[:, 0] >= BELT_X[0])
            & (pos[:, 0] <= self._drive_to)
            & (pos[:, 2] < SURFACE_Z + ON_BELT)
        )
        self.data.qvel[self._dadr[riding]] = self.belt_speed
        self.data.qvel[self._dadr[riding] + 1] = 0.0

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

    def _hold_bag(self) -> None:
        """Keep the bag where the magazine or the picker has it, level and still."""
        if self._bag_held is None:
            return
        adr, dadr = self._bag_qadr, self._bag_dadr
        self.data.qpos[adr : adr + 3] = self._bag_held
        self.data.qpos[adr + 3 : adr + 7] = (1.0, 0.0, 0.0, 0.0)
        self.data.qvel[dadr : dadr + 6] = 0.0

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

    def _settled_profile(self) -> np.ndarray:
        """Film height per roof ring once it lies on the pack.

        The pack's own top under each ring, plus a clearance, is where the
        film would sit if it followed the cloth exactly. It does not: a sheet
        bridges a dip between two high points rather than dropping into it,
        so every ring is pulled back up to within BAG_FILM_SAG of the lower
        of its two neighbours, and the result is smoothed once — film creases
        over a fold, it does not step.
        """
        local = self._bag_local
        top = np.full(BAG_PANELS, BAG_SETTLED_MIN)
        for index in range(BAG_PANELS):
            lo, hi = self._panel_edges[index], self._panel_edges[index + 1]
            band = (local[:, 0] >= lo) & (local[:, 0] < hi)
            if band.any():
                height = float(local[band, 2].max()) + SHIRT_RADIUS - BAG_FLOOR
                top[index] = height + BAG_FILM_LIFT
        top = np.clip(top, BAG_SETTLED_MIN, BAG_OPEN)
        for _ in range(BAG_PANELS):
            bridge = np.minimum(
                np.concatenate([top[:1], top[:-1]]),
                np.concatenate([top[1:], top[-1:]]),
            )
            top = np.maximum(top, bridge - BAG_FILM_SAG)
        smooth = top.copy()
        smooth[1:-1] = 0.25 * top[:-2] + 0.5 * top[1:-1] + 0.25 * top[2:]
        return np.clip(smooth, BAG_SETTLED_MIN, BAG_OPEN)

    def _film_at(self, x: float) -> float:
        """Film height above the bag's floor at local ``x``."""
        index = int(np.clip(np.searchsorted(self._panel_edges, x) - 1, 0, BAG_PANELS - 1))
        return float(self._bag_film[index])

    # --- the cycle ----------------------------------------------------

    def _run(self):
        while True:
            self.cycles += 1
            yield from self._cycle()
            if not self.repeat:
                return

    def _cycle(self):
        self._load()
        self.phase = "LOAD"
        if self.skewed and not self.flat:
            place = self._place
            if place is not None:
                wrinkle_mm = (
                    float(place.world[:, 2].max() - place.world[:, 2].min()) * 1000.0
                )
                load_msg = (
                    f"operator place  {math.degrees(place.yaw):+.0f} deg, "
                    f"{place.dy * 100:+.1f} cm aside, {place.dx * 100:+.1f} cm along, "
                    f"{wrinkle_mm:.0f} mm crumple"
                )
            else:
                load_msg = "operator placed the shirt a bit off"
            yield from self._hold(
                "LOAD",
                load_msg,
                0.7,
                measurements={
                    "spawnYawRad": self._skew_yaw,
                    "spawnOffsetYM": self._skew_y,
                },
            )
            self._enter(
                "ORIENT",
                "two arms pick the garment up and square its heading",
                phase="ORIENT",
            )
            yield from self._align.cycle(self)
            pos = self.positions()
            span = pos.max(axis=0) - pos.min(axis=0)
            z_span = float(span[2])
            heading = math.degrees(_heading(pos, self._align._rest_local))
            self._enter(
                "ORIENT",
                f"collar downstream ({heading:+.0f} deg), still wrinkled "
                f"({span[0] * 100:.0f} x {span[1] * 100:.0f} cm, "
                f"{z_span * 1000:.0f} mm crumple)",
                measurements={"headingRad": float(math.radians(heading))},
            )
            yield from self._hold("ORIENT", "", 0.4, quiet=True)
        else:
            wrinkle_mm = 0.0
            if self._place is not None:
                wrinkle_mm = (
                    float(self._place.world[:, 2].max() - self._place.world[:, 2].min())
                    * 1000.0
                )
            yield from self._hold(
                "LOAD",
                f"shirt square on the belt, {wrinkle_mm:.0f} mm crumple",
                0.6,
                measurements={
                    "spawnYawRad": self._skew_yaw,
                    "spawnOffsetYM": self._skew_y,
                },
            )
            yield from self._hold(
                "ORIENT",
                "align arms idle, heading already square",
                0.3,
                phase="ORIENT",
            )

        self._enter("BELT", "carry the shirt under the press", phase="TO_PRESS")
        yield from self._belt_until(lambda pos: PRESS_X - float(pos[:, 0].mean()))

        self._enter("PRESS", "platen down on the belt", phase="PRESS",
                    measurements={"flatnessPreM": float(np.std(self.positions()[:, 2]))})
        yield from self._press_down(2.5)
        self._enter("STEAM", "steam irons the wrinkles out")
        yield from self._iron_to_flat(3.0)
        self._enter("LIFT", "platen up")
        yield from self._ramp_stroke(STROKE_OPEN, 2.0)
        self._align.release()

        self._enter("BELT", "carry the pressed shirt to the inspection station", phase="TO_QC",
                    measurements={"flatnessPostM": float(np.std(self.positions()[:, 2]))})
        yield from self._belt_until(lambda pos: QC_X - float(pos[:, 0].mean()))
        yield from self._shoot()

        reject = qc_reject_bin(self.garment)
        if reject:
            self.outcome = reject
            yield from self._reject(reject)
            yield from self._hold(
                "DONE",
                f"rejected at QC ({reject}); not folded",
                1.2,
                phase="DONE",
            )
            return

        self._enter("SORT", "QC pass, continue to folder", phase="SORT")
        yield from self._hold("SORT", "", 0.25, quiet=True)

        self._enter("BELT", "run the shirt off the belt onto the folder", phase="TO_FOLDER")
        self._drive_to = FOLDER_X[1]
        yield from self._belt_until(lambda pos: FOLDER_X[0] + HEM_INSET - float(pos[:, 0].min()))
        self._drive_to = BELT_X[1]
        # The bagger gets a bag ready while the folder works.
        self._bagger = self._prepare_bag()
        yield from self._hold("SETTLE", "shirt on the folder", 0.3, phase="FOLD")

        self._layers = _Layers(self.model, self.data, thickness=0.5 * LAYER_GAP)
        for flap in FLAPS:
            self._enter("FOLD", flap.body.replace("flap_", "") + " flap over",
                        operation=flap.body.upper())
            yield from self._flip(flap)
            yield from self._hold("FOLD", "", 0.12, quiet=True)

        pos = self.positions()
        size = pos.max(axis=0) - pos.min(axis=0)
        self._enter(
            "FOLD",
            f"folded pack {size[0] * 100:.0f} x {size[1] * 100:.0f} cm, "
            f"{size[2] * 1000:.0f} mm tall",
            operation="PACK_MEASURED",
            measurements={"packLengthM": float(size[0]), "packWidthM": float(size[1]), "packHeightM": float(size[2])},
        )
        yield from self._hold("FOLD", "", 0.3, quiet=True)

        if not self._bag_ready:
            self._enter("WAIT", "the pack waits for the bagger to open a bag")
            while not self._bag_ready:
                yield

        self._enter("BAG", "peel runs out on its slides and carries the pack into the open bag", phase="INSERT")
        travel = BAG_X + BAG_HALF_LENGTH - BAG_END_MARGIN - float(pos[:, 0].max())
        yield from self._move_peel(travel, 0.0, 2.4, carry=True)
        self._enter(
            "TILT",
            f"lifters push the drawer's back end up, the peel tips {math.degrees(PEEL_TILT):.0f} deg "
            "on its nose and the pack's front lands on the bag floor",
        )
        yield from self._move_peel(travel, PEEL_TILT, 0.8, carry=True)
        self._enter("PEEL", "peel slides back out from under the pack, levelling off on the way")
        yield from self._withdraw_peel(travel, 2.2)
        yield from self._hold("PEEL", "", 0.5, quiet=True)
        # The shirt lies still in the bag now. Fix it there: it cannot sag while
        # the bag closes, and it goes wherever the bag goes.
        self._layers = None
        self._seal_in()

        self._enter("RELEASE", "fingers and mouth cup let go, the film settles on the pack")
        yield from self._release_bag(self._settled_profile())
        self._enter("INDEX", "belt 2 moves the bag on to the seal station", phase="TO_SEAL")
        yield from self._index_bag(SEAL_X)
        self._enter("SEAL", "seal bar presses the mouth flat and welds it, stamp puts the label on", phase="SEAL")
        yield from self._seal_and_tag()

        self._enter("BELT", "belt 2 carries the bag to the carton", phase="TO_CARTON")
        yield from self._convey()
        self.outcome = "packed"
        yield from self._hold("DONE", "sequence complete; packaging quality not validated", 2.5, phase="DONE")

    def _set_flash(self, level: float) -> None:
        """0 dark, 1 full. Lamps, bulbs and the station's dip move together."""
        model = self.model
        model.light_diffuse[self._flash] = np.array(FLASH_DIFFUSE) * level
        rgba = self._bulb_rgba.copy()
        rgba[:, :3] += (1.0 - rgba[:, :3]) * level
        model.geom_rgba[self._bulb] = rgba
        self._flash_level = float(level)
        # The station's lamps ease toward QC_DIP as the flash comes up; the
        # headlight is left alone, so the rest of the picture does not go out.
        self._set_lighting(1.0 - (1.0 - QC_DIP) * level, 1.0)

    def _set_lighting(self, scene: float, headlight: float) -> None:
        """Scale the named lights and the headlight off their normal levels."""
        model = self.model
        model.light_diffuse[self._scene_lights] = self._light0[self._scene_lights] * scene
        model.vis.headlight.diffuse[:] = self._head0[0] * headlight
        model.vis.headlight.ambient[:] = self._head0[1] * headlight

    @contextmanager
    def _photo_exposure(self):
        """Stop the lights down for one capture, then put them back.

        The product shot needs a much deeper dip than the screen should ever
        see. Both the MuJoCo bridge and the Isaac run take the shot inside
        ``on_photo``, synchronously and holding whatever lock the renderer
        needs, so the stopped-down state exists only between these two lines
        and no live frame is composed while it does.
        """
        self._set_lighting(QC_PHOTO_DIP, QC_PHOTO_DIP)
        try:
            yield
        finally:
            self._set_flash(self._flash_level)

    def _shoot(self):
        """Stop, let the cloth settle, fire the flash, take the product shot.

        The belt has already braked to a stop at QC_X. The shot is taken at
        the top of the flash, so what the camera sees is what the dashboard
        shows. `on_photo` is optional: without it the flash still fires, which
        is what makes the stop legible in the live viewport.
        """
        self._enter("PHOTO", "shirt stopped square under the QC camera", phase="PHOTO")
        yield from self._hold("PHOTO", "", 0.45, quiet=True)
        for blend in self._tween(FLASH_RISE):
            self._set_flash(blend)
            yield
        self._set_flash(1.0)
        taken = False
        for _ in range(self._steps(FLASH_HOLD)):
            if not taken:
                # One step in, so the renderer sees the lit frame.
                taken = True
                if self.on_photo is not None:
                    try:
                        with self._photo_exposure():
                            self.on_photo()
                    except Exception as exc:  # noqa: BLE001 — a bad shot is not a bad cycle
                        self._observe("PHOTO_FAILED", f"camera failed: {exc}", level="warning")
                        self.log(f"[line {self.cycles}] PHOTO  camera failed: {exc}")
            yield
        for blend in self._tween(FLASH_FALL):
            self._set_flash(1.0 - blend)
            yield
        self._set_flash(0.0)

    def _set_arm(self, cup_xyz) -> None:
        """Pose the QC pedestal arm so its suction cup sits at ``cup_xyz``."""
        cup, s, elbow, wrist, yaw = _qc_ik(cup_xyz)
        half = 0.5 * yaw
        data = self.data
        data.mocap_pos[self._qc_yaw] = s
        data.mocap_quat[self._qc_yaw] = (math.cos(half), 0.0, 0.0, math.sin(half))
        data.mocap_pos[self._qc_upper] = s
        data.mocap_quat[self._qc_upper] = _quat_z_to(elbow - s)
        data.mocap_pos[self._qc_fore] = elbow
        data.mocap_quat[self._qc_fore] = _quat_z_to(wrist - elbow)
        data.mocap_pos[self._qc_cup] = cup
        data.mocap_quat[self._qc_cup] = (1.0, 0.0, 0.0, 0.0)

    def _suction_ids(self, cup: np.ndarray) -> np.ndarray:
        """Vertices the cup actually holds; the rest of the sheet hangs."""
        dist = np.linalg.norm(self.positions() - cup, axis=1)
        ids = np.flatnonzero(dist <= QC_SUCTION_R)
        if ids.size < 8:
            ids = np.argsort(dist)[:16]
        return np.asarray(ids, dtype=int)

    def _move_cup(self, xyz, seconds: float, *, carry: bool = False):
        """Lerp the cup to ``xyz``. With ``carry`` only the held patch goes with it.

        The shoulder is on the camera post itself, so a straight line from
        anywhere the arm works to anywhere else stays clear of the plant: no
        waypoints, no keep-out to respect.
        """
        yield from self._lerp_cup(xyz, seconds, carry=carry)

    def _lerp_cup(self, xyz, seconds: float, *, carry: bool):
        start = np.array(self.data.mocap_pos[self._qc_cup], dtype=float)
        target = np.asarray(xyz, dtype=float)
        ids = self._qc_ids
        previous = self.positions()[ids] if carry and ids is not None else None
        for blend in self._tween(max(seconds, self.dt)):
            pos = start + (target - start) * blend
            self._set_arm(pos)
            if carry and ids is not None and self._qc_local is not None:
                world = pos + self._qc_local
                vel = (world - previous) / self.dt
                self._pin(ids, world, vel)
                previous = world
            yield

    def _release_suction(self) -> None:
        """Let go of the patch without throwing it; the rest of the sheet falls."""
        ids = self._qc_ids
        if ids is not None:
            vel = self.data.qvel[self._dadr[ids, None] + self._xyz]
            vel *= 0.2
            vel[:, 2] = np.minimum(vel[:, 2], -0.08)
            self.data.qvel[self._dadr[ids, None] + self._xyz] = vel
        self._qc_ids = None
        self._qc_local = None

    def _reject(self, kind: str):
        """Pick up a stained or torn shirt and drop it into the matching tote."""
        bin_xy = QC_BIN_XY[kind]
        tote = "stained bin" if kind == "stained" else "broken bin"
        self._enter(
            "SORT",
            f"{'stained' if kind == 'stained' else 'torn'} garment · suction to {tote}",
            phase="SORT",
            operation="REJECT_STAINED" if kind == "stained" else "REJECT_BROKEN",
        )
        cloth = self.positions()
        center = cloth.mean(axis=0)
        grab = np.array([center[0], center[1], QC_CUP_GRAB_Z])
        hover = np.array([center[0], center[1], QC_CUP_LIFT_Z])
        over_bin = np.array([bin_xy[0], bin_xy[1], QC_CUP_LIFT_Z])
        dangle = np.array([bin_xy[0], bin_xy[1], QC_BIN_HOVER_Z])
        drop = np.array([bin_xy[0], bin_xy[1], QC_BIN_DROP_Z])

        yield from self._move_cup(hover, 0.5)
        yield from self._move_cup(grab, 0.4)
        self._qc_ids = self._suction_ids(grab)
        self._qc_local = self.positions()[self._qc_ids] - grab
        # Hold the patch still so the rest of the sheet can drape.
        yield from self._lerp_cup(grab, 0.3, carry=True)
        yield from self._move_cup(hover, 0.9, carry=True)
        yield from self._move_cup(over_bin, 1.2, carry=True)
        yield from self._move_cup(dangle, 0.8, carry=True)
        # Kill carry speed so the let-go is a drop, not a slam.
        yield from self._lerp_cup(dangle, 0.35, carry=True)
        yield from self._move_cup(drop, 0.9, carry=True)
        yield from self._lerp_cup(drop, 0.25, carry=True)
        self._release_suction()
        yield from self._lerp_cup(drop, 0.55, carry=False)
        yield from self._move_cup(over_bin, 0.9)
        yield from self._hold("SORT", f"dropped in {tote}", QC_DROP_WATCH_S)
        yield from self._move_cup(QC_CUP_HOME, 0.7)

    def _load(self) -> None:
        mujoco = self._mujoco
        mujoco.mj_resetData(self.model, self.data)
        self._layers = None
        self._bag_local = None
        self.outcome = None
        self.belt_speed = 0.0
        self.belt2_speed = 0.0
        self._steam.reset()
        set_steam(self.model, False)
        self.data.ctrl[self._stroke] = STROKE_OPEN
        self._align.reset()
        self._place = None
        if self.skewed:
            place = operator_shirt(SPAWN_X, self._rng)
        else:
            world = _crumple_shirt(
                flat_shirt(SPAWN_X),
                self._rng,
                amount=float(self._rng.uniform(0.35, 0.60)),
            )
            place = OperatorPlace(_slide_onto_belt(world), 0.0, 0.0, 0.0)
        self._place = place
        world = place.world
        self._skew_yaw = place.yaw
        self._skew_y = place.dy
        self._align._world = world.copy()
        self._align._prev = world.copy()
        ids = np.arange(len(world))
        self._pin(ids, world, None)
        for name, gid in self._g.items():
            self.model.geom_rgba[gid] = self._rgba0[name]
        self.model.geom_rgba[self._g["bag_seam"], 3] = 0.0
        self.model.geom_rgba[self._g["bag_sticker"], 3] = 0.0
        # The next bag waits flat on top of the magazine.
        self._bagger = None
        self._bag_ready = False
        self._bag_held = np.array([BAG_X, MAG_Y, MAG_BAG_Z])
        self._hold_bag()
        self._shape_bag(BAG_FLAT, 0.0)
        self._set_peel(0.0, 0.0)
        self._set_flash(0.0)
        self._qc_local = None
        self._qc_ids = None
        self._set_arm(QC_CUP_HOME)
        mujoco.mj_forward(self.model, self.data)

    def _observe(self, operation: str, message: str, *, station: str | None = None,
                 parallel: bool = False, measurements: dict[str, float] | None = None,
                 level: str = "info") -> None:
        if self.on_event is not None:
            self.on_event({
                "state": self.phase,
                "operation": operation,
                "station": station or _PHASES[self.phase]["station"],
                "parallel": parallel,
                "message": message,
                "level": level,
                "t": float(self.data.time),
                "measurements": measurements or {},
            })

    def _enter(self, stage: str, message: str, *, phase: str | None = None,
               operation: str | None = None, measurements: dict[str, float] | None = None) -> None:
        if phase is not None:
            if phase not in _PHASES:
                raise ValueError(f"Unknown line phase: {phase}")
            self.phase = phase
        self.stage = stage
        self._observe(operation or stage, message, measurements=measurements)
        if message:
            self.log(f"[line {self.cycles}] {stage:<6} {message}")

    def _hold(self, stage: str, message: str, seconds: float, quiet: bool = False, *,
              phase: str | None = None, measurements: dict[str, float] | None = None):
        if not quiet:
            self._enter(stage, message, phase=phase, measurements=measurements)
        for _ in range(self._steps(seconds)):
            yield

    def _belt_until(self, remaining):
        """Run the belt until ``remaining(positions)`` metres reach zero.

        The belt brakes on the way in so the shirt stops right there, the way
        a line stops a part at a station.
        """
        while True:
            pos = (
                self._align._world
                if self._align._world is not None
                else self.positions()
            )
            left = remaining(pos)
            if left <= 0.002:
                break
            top = BELT_SPEED * self.speed
            accel = BELT_ACCEL * self.speed * self.speed
            self.belt_speed = min(
                top,
                self.belt_speed + accel * self.dt,
                max(0.02, math.sqrt(2.0 * accel * left)),
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

    def _press_down(self, seconds: float):
        """Close the platen; squash Z folds under it, keep the XY crumple."""
        start = np.asarray(self.positions(), dtype=float)
        z0 = SURFACE_Z + SHIRT_RADIUS
        start_stroke = float(self.data.ctrl[self._stroke])
        steps = self._steps(seconds)
        pin = self._align._world is not None or self.skewed
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            self.data.ctrl[self._stroke] = start_stroke + (
                STROKE_PRESSED - start_stroke
            ) * blend
            if pin:
                world = start.copy()
                world[:, 2] = start[:, 2] + blend * (z0 - start[:, 2])
                self._align._world = world
            yield

    def _iron_to_flat(self, seconds: float):
        """Steam + morph the crumpled sheet onto the square T under the press."""
        start = np.asarray(self.positions(), dtype=float)
        target = flat_shirt(PRESS_X)
        set_steam(self.model, True)
        steps = self._steps(seconds)
        ids = np.arange(len(start))
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            world = start + blend * (target - start)
            self._align._world = world
            vel = (target - start) / max(seconds, self.dt)
            self._pin(ids, world, vel)
            self._steam.puff(index * self.dt, seconds)
            yield
        self._align._world = target.copy()
        self._pin(ids, target, None)
        z_span = float(target[:, 2].max() - target[:, 2].min())
        self._enter(
            "STEAM",
            f"pressed flat, {z_span * 1000:.0f} mm thick",
        )
        yield from self._hold("STEAM", "", 0.2, quiet=True)
        self._steam.reset()
        set_steam(self.model, False)

    def _steam_for(self, seconds: float):
        set_steam(self.model, True)
        for index in range(self._steps(seconds)):
            self._steam.puff(index * self.dt, seconds)
            yield
        self._steam.reset()
        set_steam(self.model, False)

    def _tween(self, seconds: float):
        """Blend 0 -> 1 over ``seconds``, eased, one value per step."""
        steps = self._steps(seconds)
        for index in range(steps):
            yield smoothstep((index + 1) / steps)

    # --- the peel ------------------------------------------------------

    def _set_peel(self, shift: float, tilt: float) -> None:
        """Put the peel ``shift`` metres downstream, nose down by ``tilt``.

        The drawer is rigid: the middle slide is out half as far, and both
        tip about the bottom of the peel's front edge, so the nose stays on
        whatever it rests on and the back end rises. The lifters' rods reach
        up to the middle slide's underside.
        """
        data = self.data
        pivot = self._peel_pivot + (shift, 0.0, 0.0)
        quat = _pitch_quat(tilt)
        for mocap, home, out in (
            (self._peel, self._peel_home, shift),
            (self._slide, self._slide_home, 0.5 * shift),
        ):
            arm = home + (out, 0.0, 0.0) - pivot
            data.mocap_pos[mocap] = pivot + _pitch(arm[None, :], tilt)[0]
            data.mocap_quat[mocap] = quat
        # Rise of the drawer's underside above the lifters, behind the nose.
        top = LIFTER_REST_Z + max(0.0, (pivot[0] - LIFTER_X) * math.tan(tilt))
        half = 0.5 * (top - LIFTER_BASE_Z)
        self.model.geom_size[self._lifter_rods, 1] = half
        self.model.geom_pos[self._lifter_rods, 2] = LIFTER_BASE_Z + half
        self._peel_shift, self._peel_tilt = shift, tilt

    def _move_peel(self, shift: float, tilt: float, seconds: float, carry: bool):
        """Slide and tip the peel from where it is to ``shift`` and ``tilt``.

        With ``carry`` the shirt goes with it, rigidly. Without, the peel just
        goes: nothing in the solver drags the shirt, which is the point.
        """
        shift0, tilt0 = self._peel_shift, self._peel_tilt
        cloth = self.positions()
        # The shirt in the peel's frame at the start, about its pivot.
        local = cloth - (self._peel_pivot + (shift0, 0.0, 0.0))
        everything = np.arange(self.model.nflexvert)
        previous = cloth
        for blend in self._tween(seconds):
            now_shift = shift0 + (shift - shift0) * blend
            now_tilt = tilt0 + (tilt - tilt0) * blend
            self._set_peel(now_shift, now_tilt)
            if carry:
                # Absolute positions, and the velocity that got them there: an
                # increment would be counted twice by the step that follows.
                pivot = self._peel_pivot + (now_shift, 0.0, 0.0)
                world = pivot + _pitch(local, now_tilt - tilt0)
                self._pin(everything, world, (world - previous) / self.dt)
                previous = world
            yield

    def _withdraw_peel(self, travel: float, seconds: float):
        """Slide the peel home from ``travel``, tipped while it leaves the pack.

        It stays tipped for the first part, then the lifters let it down so it
        is level by PEEL_LEVEL_AT, before its back end is in the folder again.
        Nothing drags the shirt: it stays on the bag floor.
        """
        high = max(PEEL_LEVEL_AT + 0.05, 0.6 * travel)
        for blend in self._tween(seconds):
            shift = travel * (1.0 - blend)
            up = min(1.0, max(0.0, (shift - PEEL_LEVEL_AT) / (high - PEEL_LEVEL_AT)))
            self._set_peel(shift, PEEL_TILT * smoothstep(up))
            yield

    # --- the bagger ----------------------------------------------------

    def _prepare_bag(self):
        """The bagger's own sequence, alongside the fold: pick, place, open.

        Leaves ``_bag_ready`` set, with the bag on belt 2 blown open and its
        mouth held square.
        """
        model, data = self.model, self.data

        def log(operation: str, message: str) -> None:
            self._observe(operation, message, station="bagger", parallel=True)
            self.log(f"[line {self.cycles}] BAGGER {message}")

        log("BAG_PICK", "picker takes the top bag off the magazine")
        grip_mag = MAG_BAG_Z + BAG_FLOOR + BAG_FLAT + FILM
        yield from self._move_picker(MAG_Y, PICKER_PARK_Z, grip_mag, 0.6)
        yield from self._hold("", "", 0.25, quiet=True)  # vacuum builds
        grip = BAG_FLOOR + BAG_FLAT + FILM  # cups' lips above the bag's centre
        yield from self._move_picker(MAG_Y, grip_mag, CARRY_BAG_Z + grip, 0.6, carry=True)
        log("BAG_PLACE", "picker carries it over belt 2 and lays it down, mouth toward the folder")
        yield from self._move_picker(MAG_Y, CARRY_BAG_Z + grip, CARRY_BAG_Z + grip, 1.2,
                                     carry=True, to_y=0.0)
        yield from self._move_picker(0.0, CARRY_BAG_Z + grip, BELT2_BAG_Z + grip, 0.6, carry=True)
        # Vacuum off: the bag lies on the belt, and the belt's vacuum box holds
        # its bottom film.
        self._bag_held = None
        yield from self._hold("", "", 0.2, quiet=True)
        yield from self._move_picker(0.0, BELT2_BAG_Z + grip, PICKER_PARK_Z, 0.5)

        log("BAG_OPEN", "mouth cup lifts the top lip, air knife blows the bag open")
        cup = self._mouth_cup
        bag_z = float(data.qpos[self._bag_qadr + 2])
        park_back = self._move_picker(0.0, PICKER_PARK_Z, PICKER_PARK_Z, 1.2, to_y=MAG_Y)
        for blend in self._tween(0.5):
            data.mocap_pos[cup][2] = MOUTH_CUP_PARK_Z + (self._mouth_cup_z(bag_z) - MOUTH_CUP_PARK_Z) * blend
            next(park_back, None)
            yield
        jet = self._g["air_jet"]
        for index, blend in enumerate(self._tween(1.4)):
            self._shape_bag(BAG_FLAT + (BAG_OPEN - BAG_FLAT) * blend, TAIL_FLARE * blend)
            data.mocap_pos[cup][2] = self._mouth_cup_z(bag_z)
            model.geom_rgba[jet, 3] = 0.16 + 0.08 * math.sin(0.35 * index)
            next(park_back, None)
            yield
        for _ in park_back:
            yield

        log("BAG_HOLD", "spreader fingers drop into the mouth's corners and hold it square")
        for blend in self._tween(0.5):
            self._set_fingers(FINGER_IN_Y, FINGER_PARK_Z + (FINGER_DOWN_Z - FINGER_PARK_Z) * blend)
            yield
        for blend in self._tween(0.4):
            self._set_fingers(FINGER_IN_Y + (FINGER_OUT_Y - FINGER_IN_Y) * blend, FINGER_DOWN_Z)
            yield
        model.geom_rgba[jet, 3] = 0.0
        log("BAG_READY", "bag open, ready for the pack")
        self._bag_ready = True

    def _move_picker(self, y: float, z0: float, z1: float, seconds: float,
                     carry: bool = False, to_y: float | None = None):
        """Move the picker's head from height ``z0`` to ``z1`` (and along the
        beam from ``y`` to ``to_y``); with ``carry`` the bag hangs on its cups."""
        data = self.data
        y1 = y if to_y is None else to_y
        grip = BAG_FLOOR + BAG_FLAT + FILM
        for blend in self._tween(seconds):
            now_y = y + (y1 - y) * blend
            now_z = z0 + (z1 - z0) * blend
            data.mocap_pos[self._picker] = (BAG_X, now_y, now_z)
            data.mocap_pos[self._carriage] = (BAG_X, now_y, PICKER_CARRIAGE_Z)
            if carry:
                self._bag_held = np.array([BAG_X, now_y, now_z - grip])
            yield

    def _mouth_cup_z(self, bag_z: float) -> float:
        """Height of the mouth cup's lip on the bag's tail, as the bag is now."""
        return (
            bag_z + BAG_FLOOR + self._bag_h + FILM
            + MOUTH_CUP_ON_TAIL * math.sin(self._bag_tail)
        )

    def _set_fingers(self, y: float, z: float) -> None:
        for mocap, side in self._fingers:
            self.data.mocap_pos[mocap][1:] = (side * y, z)

    def _release_bag(self, settled: np.ndarray):
        """Fingers in and up, mouth cup off: the film settles on the pack.

        ``settled`` is one height per roof ring, so the film comes down onto
        the pack's own shape rather than to one flat lid height.
        """
        data = self.data
        for blend in self._tween(0.4):
            self._set_fingers(FINGER_OUT_Y + (FINGER_IN_Y - FINGER_OUT_Y) * blend, FINGER_DOWN_Z)
            yield
        for blend in self._tween(0.5):
            self._set_fingers(FINGER_IN_Y, FINGER_DOWN_Z + (FINGER_PARK_Z - FINGER_DOWN_Z) * blend)
            yield
        cup_z = float(data.mocap_pos[self._mouth_cup][2])
        film0, tail0 = self._bag_film.copy(), self._bag_tail
        settled = np.asarray(settled, dtype=float)
        for blend in self._tween(1.0):
            self._shape_bag(film0 + (settled - film0) * blend, tail0 * (1.0 - blend))
            data.mocap_pos[self._mouth_cup][2] = cup_z + (MOUTH_CUP_PARK_Z - cup_z) * blend
            yield

    def _index_bag(self, target: float):
        """Run belt 2 until the bag's centre is at ``target``, braking in."""
        while True:
            left = target - float(self.data.qpos[self._bag_qadr])
            if left <= 0.002:
                break
            top = BELT2_SPEED * self.speed
            accel = BELT_ACCEL * self.speed * self.speed
            self.belt2_speed = min(
                top,
                self.belt2_speed + accel * self.dt,
                max(0.02, math.sqrt(2.0 * accel * left)),
            )
            yield
        self.belt2_speed = 0.0
        self.data.qvel[self._bag_dadr : self._bag_dadr + 6] = 0.0

    def _shape_bag(self, height, tail: float) -> None:
        """Shape the bag's films: ``height`` floor to roof, and the tail
        ``tail`` radians off the roof's line (up is positive).

        ``height`` is one number while the bag is flat, being blown open or
        being closed — every ring the same. Once the film settles it is one
        height per ring (``_settled_profile``), and the roof and both gussets
        step down over the pack's shoulders instead of staying a flat lid.

        The tail hinges off the ring at the mouth, so it follows that ring,
        not the tallest one. The tail's sides follow it while it is flared or
        flat; pressed down, the gussets fold in and they go.
        """
        g, pos, size, quat = self._g, self.model.geom_pos, self.model.geom_size, self.model.geom_quat
        film = np.broadcast_to(np.asarray(height, dtype=float), (BAG_PANELS,)).copy()
        self._bag_film = film
        for (roof_id, left_id, right_id), panel in zip(self._panels, film):
            pos[roof_id, 2] = BAG_FLOOR + panel
            for gid in (left_id, right_id):
                pos[gid, 2] = BAG_FLOOR + 0.5 * panel
                size[gid, 2] = max(0.5 * panel, FILM)
        far = float(film[-1])
        for name in ("bag_end", "bag_weld_end"):
            pos[g[name], 2] = BAG_FLOOR + 0.5 * far
            size[g[name], 2] = max(0.5 * far, FILM)
        for name, dz in (("bag_hang_patch", FILM + 0.0004), ("bag_hang_hole", FILM + 0.0008)):
            pos[g[name], 2] = BAG_FLOOR + far + dz
        pos[g["bag_sticker"], 2] = (
            BAG_FLOOR + self._film_at(float(pos[g["bag_sticker"], 0])) + FILM + 0.0006
        )
        # Film pulled onto a product reads denser than film standing empty.
        span = max(BAG_OPEN - BAG_SETTLED_MIN, 1e-6)
        tight = float(np.clip((BAG_OPEN - film.mean()) / span, 0.0, 1.0))
        lo, hi = BAG_FILM_ALPHA
        self.model.geom_rgba[self._film_alpha, :3] = self._film_rgb
        self.model.geom_rgba[self._film_alpha, 3] = lo + (hi - lo) * tight

        mouth = float(film[0])
        hinge = np.array([TAIL_HINGE_X, 0.0, BAG_FLOOR + mouth])
        along = np.array([-math.cos(tail), 0.0, math.sin(tail)])
        normal = np.array([math.sin(tail), 0.0, math.cos(tail)])
        middle = hinge + 0.5 * TAIL_LENGTH * along
        pos[g["bag_tail"]] = middle
        quat[g["bag_tail"]] = _pitch_quat(tail)
        # The lip runs on from the seal line: flared with the tail, else flat.
        lip = max(tail, 0.0)
        pos[g["bag_lip"]] = hinge + TAIL_LENGTH * along + 0.5 * LIP_LENGTH * np.array(
            [-math.cos(lip), 0.0, math.sin(lip)]
        )
        quat[g["bag_lip"]] = _pitch_quat(lip)
        depth = max(0.0, min(mouth, mouth + TAIL_LENGTH * math.sin(tail))) * math.cos(tail)
        for name, y in (("bag_tail_side_l", 0.2442), ("bag_tail_side_r", -0.2442)):
            gid = g[name]
            pos[gid] = middle - 0.5 * depth * normal
            pos[gid, 1] = y
            size[gid, 2] = max(0.5 * depth, 1e-4)
            quat[gid] = _pitch_quat(tail)
        self._bag_h, self._bag_tail = mouth, tail

    def _seal_and_tag(self):
        """Lower the seal bar and the stamp together, dwell, lift.

        The bar presses the tail down to the floor on its way. On contact the
        mouth seam shows, and the label moves from the stamp to the bag.
        """
        model = self.model
        g = self._g
        bag_z = float(self.data.qpos[self._bag_qadr + 2])
        bar_z = bag_z + BAG_FLOOR + 3.0 * FILM + SEAL_BAR_HALF
        label_x = float(model.geom_pos[g["bag_sticker"], 0])
        stamp_z = bag_z + BAG_FLOOR + self._film_at(label_x) + FILM + STAMP_UNDER
        yield from self._move_presses(bar_z, stamp_z, 1.2, press_tail=True)

        model.geom_rgba[g["bag_seam"]] = (0.70, 0.84, 0.95, 0.85)
        for index in range(4):
            model.geom_rgba[g[f"bag_crimp_{index}"], 3] = 0.9
        model.geom_rgba[g["stamp_sticker"], 3] = 0.0
        model.geom_rgba[g["bag_sticker"], 3] = 1.0
        cold = self._rgba0["seal_bar_head"]
        hot = np.array([1.0, 0.45, 0.15, 1.0])
        dwell = 1.6
        for index in range(self._steps(dwell)):
            glow = math.sin(math.pi * min(1.0, index * self.dt / dwell))
            model.geom_rgba[g["seal_bar_head"]] = cold + (hot - cold) * glow
            yield
        model.geom_rgba[g["seal_bar_head"]] = cold

        yield from self._move_presses(PRESS_HOVER_Z, PRESS_HOVER_Z, 1.0)

    def _move_presses(self, bar_z: float, stamp_z: float, seconds: float, press_tail: bool = False):
        bar, stamp = self._seal_bar, self._stamp
        bar0, stamp0 = float(self.data.mocap_pos[bar][2]), float(self.data.mocap_pos[stamp][2])
        bag_z = float(self.data.qpos[self._bag_qadr + 2])
        for blend in self._tween(seconds):
            self.data.mocap_pos[bar][2] = bar0 + (bar_z - bar0) * blend
            self.data.mocap_pos[stamp][2] = stamp0 + (stamp_z - stamp0) * blend
            if press_tail:
                self._press_tail(float(self.data.mocap_pos[bar][2]) - bag_z)
            yield

    def _press_tail(self, bar_z: float) -> None:
        """Push the tail's end down to just under the seal bar at ``bar_z``,
        in the bag's frame, if the bar is lower than it."""
        height = self._bag_h
        closed = -math.asin(min(1.0, (height - 2.0 * FILM) / TAIL_LENGTH))
        drop = (bar_z - SEAL_BAR_HALF - FILM) - (BAG_FLOOR + height)
        angle = math.asin(float(np.clip(drop / TAIL_LENGTH, -1.0, 0.0)))
        angle = max(angle, closed)
        if angle < self._bag_tail:
            # Only the tail moves: the film over the pack keeps its shape.
            self._shape_bag(self._bag_film, angle)

    def _convey(self):
        """Run belt 2 until the bag is in the carton."""
        while self.data.qpos[self._bag_qadr + 2] > BOXED_Z:
            self.belt2_speed = min(
                BELT2_SPEED * self.speed,
                self.belt2_speed + BELT_ACCEL * self.speed * self.speed * self.dt,
            )
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
        return max(1, int(round(seconds / (self.dt * self.speed))))

    def _dropped(self) -> bool:
        """Has the garment left the machine? Then the cycle is over."""
        if self.phase not in CARRIED_PHASES:
            return False
        return bool(self.positions()[:, 2].max() < DROPPED_Z)


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


def _pitch(points: np.ndarray, angle: float) -> np.ndarray:
    """Rotate points about +y by ``angle``: positive takes +x down."""
    cos, sin = math.cos(angle), math.sin(angle)
    out = points.copy()
    out[:, 0] = cos * points[:, 0] + sin * points[:, 2]
    out[:, 2] = -sin * points[:, 0] + cos * points[:, 2]
    return out


def _pitch_quat(angle: float) -> list[float]:
    return [math.cos(0.5 * angle), 0.0, math.sin(0.5 * angle), 0.0]


def _qc_ik(cup_xyz):
    """2-link IK for the QC reject arm: cup, shoulder, elbow, wrist and yaw.

    The shoulder is a collar on the camera post, above everything the arm
    reaches over, so the elbow is always taken up and there is no second
    solution to pick between.
    """
    cup = np.asarray(cup_xyz, dtype=float)
    wrist_target = cup + np.array([0.0, 0.0, QC_ARM_WRIST])
    shoulder, elbow, wrist, yaw = two_link_ik(
        wrist_target, QC_ARM_S, QC_ARM_L1, QC_ARM_L2
    )
    return cup, shoulder, elbow, wrist, yaw


def _qc_reach(cup_xyz) -> float:
    """Wrist distance from the shoulder for ``cup_xyz``, in metres.

    Under QC_ARM_L1 + QC_ARM_L2 - 0.03 the arm actually gets there; past it
    the IK clamps and the cup falls short of where it was asked for. The
    station's poses are all inside it — this is what a test asserts on.
    """
    _cup, shoulder, _elbow, wrist, _yaw = _qc_ik(cup_xyz)
    return float(np.linalg.norm(wrist - shoulder))


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
    parser = argparse.ArgumentParser(description="XFOLD line: dual-belt turner, belt, press, folder")
    parser.add_argument("--cycles", type=int, default=0, help="0 keeps going")
    parser.add_argument("--headless", action="store_true", help="no window, as fast as it can")
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="reproducible random draws (stain variant, skewed heading)",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="skip the dual-belt turner even if --skewed",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="machinery speed: 1 is nominal, 20 is twenty times (fast enough and "
             "the garment is left behind and the cycle is abandoned)",
    )
    add_garment_arguments(parser)
    parser.add_argument(
        "--shots", default="", help="headless: save a frame per stage into this directory"
    )
    parser.add_argument(
        "--camera",
        default="follow",
        help="follow (tracks the shirt) or a fixed one: overview, orient_cam, align_cam, "
        "press_cam, fold_cam, bagger_cam, bag_cam",
    )
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
    line = Line(
        model,
        data,
        repeat=args.cycles == 0,
        skewed=bool(args.skewed),
        flat=bool(args.flat),
        seed=int(args.seed),
        speed=float(args.speed),
    )
    pose = "operator-skewed" if args.skewed and not args.flat else "square"
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
