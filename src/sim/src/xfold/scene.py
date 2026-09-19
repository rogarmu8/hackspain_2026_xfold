"""Assemble the loading cell: press_cell.xml plus a UR5e wearing a Robotiq hand.

Neither robot lives in this repo - both come from MuJoCo Menagerie - so the
scene is composed at runtime with MjSpec. Three models come out of it:

* ``model``    - the full cell that gets simulated and rendered.
* ``ik_model`` - the same arm on the same mount, alone, used for inverse
  kinematics. Solving on a model without the shirt, the press or the hand's
  eight linkage joints keeps their degrees of freedom out of the IK problem.

The hand's pinch point is rigid with respect to the wrist flange, so the IK
model can carry a bare site in its place and still be exact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .shirt import (
    SHIRT_RADIUS,
    load_mujoco_plugins,
    set_shirt_world,
    shirt_band_local,
    shirt_collar_ids,
    shirt_rest_local,
    shirt_rest_world,
    shirt_rigid_pose,
    shirt_torso_half,
    shirt_vertex_positions,
    shirt_vertex_qposadr,
)

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
CELL_PATH = MODEL_DIR / "press_cell.xml"

ARM_ENTRY = ("universal_robots_ur5e", "ur5e")
ARM_PREFIX = "ur5e/"
ARM_MOUNT_BODY = "arm_mount"

HAND_ENTRY = ("robotiq_2f85", "2f85")
HAND_PREFIX = "hand/"

PINCH_SITE = f"{ARM_PREFIX}{HAND_PREFIX}pinch"
HAND_ACTUATOR = f"{ARM_PREFIX}{HAND_PREFIX}fingers_actuator"
INSPECT_CAMERA = f"{ARM_PREFIX}inspect_cam"

# The driver joint drives both fingers through the 2F-85's linkage, so how far
# it has turned says how wide the jaws are - and therefore whether they shut on
# the garment or on thin air. A real cell reads the same signal off the gripper.
HAND_JOINT = f"{HAND_PREFIX}right_driver_joint"
EMPTY_CLOSE_MARGIN = 0.05  # radians short of an empty close still counts as held

# The 2F-85 tendon actuator takes 0 (jaws wide, 93 mm) to 255 (jaws shut).
HAND_OPEN = 0.0
HAND_SHUT = 255.0

# Silicone on cotton grips better than Menagerie's default 0.7, which is tuned
# for rigid parts. The hand has to hold a shirt by its neckband and drag it.
PAD_FRICTION = (1.4, 0.05, 0.001)

ARM_ACTUATORS = tuple(
    f"{ARM_PREFIX}{name}"
    for name in ("shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3")
)
ARM_JOINTS = tuple(
    f"{ARM_PREFIX}{name}"
    for name in (
        "shoulder_pan_joint",
        "shoulder_lift_joint",
        "elbow_joint",
        "wrist_1_joint",
        "wrist_2_joint",
        "wrist_3_joint",
    )
)

# Menagerie's home, facing the aisle (-y). The crate and the open C-frame both
# sit on that side of the pedestal, so this is the basin every solve starts in.
ARM_SEED_Q = np.array([-1.5708, -1.5708, 1.5708, -1.5708, -1.5708, 0.0])

# The press dumps along its own +x. Yawed -90° so that edge faces the arm
# (world -y) instead of the empty side of the cell.
PRESS_YAW = -0.5 * math.pi


@dataclass(frozen=True)
class Cell:
    """Compiled models plus the handful of ids and poses the demo needs."""

    model: object
    ik_model: object
    bed_center: np.ndarray
    bed_surface_z: float
    bin_center: np.ndarray
    bin_surface_z: float
    arm_base: np.ndarray
    arm_actuators: np.ndarray
    arm_qposadr: np.ndarray
    hand_actuator: int
    hand_qposadr: int
    empty_close: float
    pinch_site: int
    finger_reach: float
    press_yaw: float
    shirt_qposadr: np.ndarray  # first slide-joint address per flex vertex
    shirt_rest_world: np.ndarray  # undeformed world positions (nvert, 3)
    shirt_rest_local: np.ndarray  # rest mesh in the controller frame
    shirt_collar_ids: np.ndarray
    shirt_half_thickness: float
    shirt_torso_half: np.ndarray  # torso panel half-extents in x and y
    shirt_band_local: np.ndarray  # neck opening in the shirt's own frame

    @property
    def shirt_rest_z(self) -> float:
        """Height of the shirt body frame when it lies on the bed."""
        return self.bed_surface_z + self.shirt_half_thickness

    @property
    def shirt_top_z(self) -> float:
        """Height of the shirt's upper face when it lies on the bed."""
        return self.bed_surface_z + 2.0 * self.shirt_half_thickness


@dataclass(frozen=True)
class _Hand:
    """What the demo needs to know about the hand, measured once at build time."""

    pinch_pos: np.ndarray  # pinch point in the wrist_3 frame
    pinch_quat: np.ndarray
    finger_reach: float  # shut fingertips, past the pinch point along the tool axis
    empty_close: float  # driver angle once the fingers have shut on nothing


def _arm_spec(*, stand_in: _Hand | None = None):
    """UR5e spec wearing the real hand, or a bare arm with a stand-in site.

    By default this builds the real thing. Passing measurements instead swaps
    the eight-jointed linkage for a single site at the same place, which is what
    the IK model wants: the pinch point is rigid with respect to the wrist, so
    the stand-in is exact and costs no degrees of freedom.
    """
    import mujoco
    import mujoco_menagerie

    robot, entry = ARM_ENTRY
    spec = mujoco_menagerie.get(robot).spec(entry)

    # The shipped keyframe only covers the arm's own joints, so it cannot
    # survive being attached to a larger model.
    for key in list(spec.keys):
        spec.delete(key)

    if stand_in is not None:
        spec.body("wrist_3_link").add_site(
            name=f"{HAND_PREFIX}pinch",
            pos=stand_in.pinch_pos,
            quat=stand_in.pinch_quat,
            size=[0.006, 0.006, 0.006],
        )
        return spec

    hand_robot, hand_entry = HAND_ENTRY
    spec.attach(
        mujoco_menagerie.get(hand_robot).spec(hand_entry),
        prefix=HAND_PREFIX,
        site="attachment_site",
    )
    for geom in spec.geoms:
        if "pad" in geom.name:
            geom.friction = PAD_FRICTION

    # Eye-in-hand: a small camera on the side of the gripper, looking down
    # the tool axis. Parked over the bed it sees the shirt, not the flange.
    hand = spec.body(f"{HAND_PREFIX}base")
    hand.add_geom(
        name="inspect_housing",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=[0.018, 0.016, 0.014],
        pos=[0.058, 0.0, 0.02],
        rgba=[0.12, 0.13, 0.15, 1],
        contype=0,
        conaffinity=0,
    )
    hand.add_camera(
        name="inspect_cam",
        pos=[0.058, 0.0, 0.045],
        xyaxes=[1, 0, 0, 0, -1, 0],
        fovy=62,
    )

    # A real UR5e controller cancels gravity; without this the arm sags ~15 mm
    # under the hand's weight, which is enough to miss a 24 mm neckband.
    for body in spec.bodies:
        body.gravcomp = 1.0
    return spec


def _ik_model(hand: _Hand, mount_pos, mount_quat, integrator):
    """The same arm on the same mount, with nothing else in the world."""
    import mujoco

    spec = mujoco.MjSpec()
    spec.option.integrator = integrator
    mount = spec.worldbody.add_body(name=ARM_MOUNT_BODY, pos=mount_pos, quat=mount_quat)
    spec.attach(_arm_spec(stand_in=hand), prefix=ARM_PREFIX, frame=mount.add_frame())
    return spec.compile()


def _measure_hand() -> _Hand:
    """Compile the arm and hand alone, shut the fingers, and read the geometry.

    Measured rather than hard-coded, because the 2F-85 fingers swing inwards as
    they close: where the fingertips end up depends on the closing angle, and
    tugging a shirt across the bed needs to know where they touch down.
    """
    import mujoco

    spec = mujoco.MjSpec()
    spec.attach(_arm_spec(), prefix=ARM_PREFIX, frame=spec.worldbody.add_frame())
    model = spec.compile()
    data = mujoco.MjData(model)
    data.ctrl[model.actuator(HAND_ACTUATOR).id] = HAND_SHUT
    for _ in range(1500):
        mujoco.mj_step(model, data)

    pinch = model.site(PINCH_SITE).id
    wrist = model.body(f"{ARM_PREFIX}wrist_3_link").id
    wrist_rot = data.xmat[wrist].reshape(3, 3)
    pinch_rot = data.site_xmat[pinch].reshape(3, 3)
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, (wrist_rot.T @ pinch_rot).flatten())

    reach = 0.0
    for index in range(model.ngeom):
        geom = model.geom(index)
        if not geom.name.startswith(ARM_PREFIX + HAND_PREFIX) or model.geom_contype[index] == 0:
            continue
        offset = pinch_rot.T @ (data.geom_xpos[index] - data.site_xpos[pinch])
        axis = pinch_rot.T @ data.geom_xmat[index].reshape(3, 3)
        if geom.type == mujoco.mjtGeom.mjGEOM_BOX:
            span = float(np.abs(axis[2]) @ geom.size)
        else:
            span = float(model.geom_rbound[index])
        reach = max(reach, float(offset[2]) + span)

    return _Hand(
        pinch_pos=wrist_rot.T @ (data.site_xpos[pinch] - data.xpos[wrist]),
        pinch_quat=quat,
        finger_reach=reach,
        empty_close=float(data.qpos[model.joint(f"{ARM_PREFIX}{HAND_JOINT}").qposadr[0]]),
    )


def build() -> Cell:
    """Compile the cell and the matching IK-only arm model."""
    import mujoco

    if not CELL_PATH.is_file():
        raise SystemExit(f"Missing scene: {CELL_PATH}")

    load_mujoco_plugins()
    hand = _measure_hand()
    spec = mujoco.MjSpec.from_file(CELL_PATH.as_posix())
    half = 0.5 * PRESS_YAW
    spec.body("press_origin").quat = [math.cos(half), 0.0, 0.0, math.sin(half)]
    mount = spec.body(ARM_MOUNT_BODY)
    mount_pos = np.array(mount.pos, dtype=float)
    mount_quat = np.array(mount.quat, dtype=float)
    spec.attach(_arm_spec(), prefix=ARM_PREFIX, frame=mount.add_frame())
    model = spec.compile()

    # Read the working heights off the model so the XML stays the one source.
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    bed = data.site(model.site("bed_center").id).xpos.copy()
    bin_site = data.site(model.site("bin_center").id).xpos.copy()
    bed_surface_z = float(
        data.geom("bed_heater").xpos[2] + model.geom("bed_heater").size[2]
    )
    bin_surface_z = float(
        data.geom("bin_floor").xpos[2] + model.geom("bin_floor").size[2]
    )

    return Cell(
        model=model,
        ik_model=_ik_model(hand, mount_pos, mount_quat, model.opt.integrator),
        bed_center=bed[:2].copy(),
        bed_surface_z=bed_surface_z,
        bin_center=bin_site[:2].copy(),
        bin_surface_z=bin_surface_z,
        arm_base=mount_pos[:2].copy(),
        arm_actuators=np.array([model.actuator(n).id for n in ARM_ACTUATORS]),
        arm_qposadr=np.array(
            [int(np.atleast_1d(model.joint(n).qposadr)[0]) for n in ARM_JOINTS]
        ),
        hand_actuator=model.actuator(HAND_ACTUATOR).id,
        hand_qposadr=int(
            np.atleast_1d(model.joint(f"{ARM_PREFIX}{HAND_JOINT}").qposadr)[0]
        ),
        empty_close=hand.empty_close,
        press_yaw=PRESS_YAW,
        pinch_site=model.site(PINCH_SITE).id,
        finger_reach=hand.finger_reach,
        shirt_qposadr=shirt_vertex_qposadr(model),
        shirt_rest_world=shirt_rest_world(model, data),
        shirt_rest_local=shirt_rest_local(),
        shirt_collar_ids=shirt_collar_ids(),
        shirt_half_thickness=SHIRT_RADIUS,
        shirt_torso_half=shirt_torso_half(),
        shirt_band_local=shirt_band_local(),
    )


def spawn_shirt_in_bin(cell: Cell, data, rng: np.random.Generator) -> None:
    """Drop a folded cloth shirt in the middle of the crate.

    Flat, the T is wider than the crate. Folding one sleeve over the other
    makes a pack that fits; it sits on the crate centre with the neck on
    top so the hand can pinch it without fishing in a corner.
    """
    local = cell.shirt_rest_local.copy()
    local -= local.mean(axis=0)
    folded = local[:, 1] > 0.0
    local[folded, 1] = -local[folded, 1]
    local[folded, 2] += 0.010
    local[:, :2] *= 0.70
    local -= local.mean(axis=0)
    local[cell.shirt_collar_ids, 2] += 0.028
    local[:, 2] += 0.006 * np.sin(9.0 * local[:, 0])

    # Collar toward the press / open lip, not the back wall.
    yaw = float(rng.uniform(-0.15, 0.15))
    cos, sin = math.cos(yaw), math.sin(yaw)
    rotation = np.array([[cos, -sin, 0.0], [sin, cos, 0.0], [0.0, 0.0, 1.0]])
    world = local @ rotation.T
    world[:, 0] += cell.bin_center[0]
    world[:, 1] += cell.bin_center[1]
    world[:, 2] += (
        cell.bin_surface_z + cell.shirt_half_thickness + 0.03 - float(world[:, 2].min())
    )
    set_shirt_world(data, world, cell.shirt_rest_world, cell.shirt_qposadr)
    data.qvel[:] = 0.0
    import mujoco

    mujoco.mj_forward(cell.model, data)


def shirt_pose(cell: Cell, data) -> tuple[np.ndarray, float]:
    """Ground-truth shirt centre and yaw, used only where a real cell would
    have a bin camera."""
    live = shirt_vertex_positions(cell.model, data)
    return shirt_rigid_pose(live, cell.shirt_rest_local)


def shirt_collar(cell: Cell, data) -> np.ndarray:
    """World-frame pinch point on the neck — the highest neck vertex."""
    live = shirt_vertex_positions(cell.model, data)
    collar = live[cell.shirt_collar_ids]
    return collar[int(np.argmax(collar[:, 2]))].copy()
