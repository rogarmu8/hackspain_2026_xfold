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
    apply_shirt_config,
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
HELPER_PREFIX = "ur5e_b/"
HELPER_MOUNT_BODY = "arm2_mount"

HAND_ENTRY = ("robotiq_2f85", "2f85")
HAND_PREFIX = "hand/"

PINCH_SITE = f"{ARM_PREFIX}{HAND_PREFIX}pinch"
HAND_ACTUATOR = f"{ARM_PREFIX}{HAND_PREFIX}fingers_actuator"
INSPECT_CAMERA = f"{ARM_PREFIX}inspect_cam"
_ARM_ACTUATOR_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow",
    "wrist_1",
    "wrist_2",
    "wrist_3",
)
_ARM_JOINT_NAMES = (
    "shoulder_pan_joint",
    "shoulder_lift_joint",
    "elbow_joint",
    "wrist_1_joint",
    "wrist_2_joint",
    "wrist_3_joint",
)

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

ARM_ACTUATORS = tuple(f"{ARM_PREFIX}{name}" for name in _ARM_ACTUATOR_NAMES)
ARM_JOINTS = tuple(f"{ARM_PREFIX}{name}" for name in _ARM_JOINT_NAMES)

# Menagerie's home, facing the aisle (-y). The crate and the open C-frame both
# sit on that side of the pedestal, so this is the basin every solve starts in.
ARM_SEED_Q = np.array([-1.5708, -1.5708, 1.5708, -1.5708, -1.5708, 0.0])

# The press dumps along its own +x. Yawed -90° so that edge faces the arm
# (world -y) instead of the empty side of the cell.
PRESS_YAW = -0.5 * math.pi


@dataclass(frozen=True)
class ArmKit:
    """One mounted UR5e: ids in the full cell plus a private IK model."""

    prefix: str
    pinch_site_name: str
    base: np.ndarray
    ik_model: object
    actuators: np.ndarray
    qposadr: np.ndarray
    hand_actuator: int
    hand_qposadr: int
    pinch_site: int
    empty_close: float
    finger_reach: float
    seed_q: np.ndarray


@dataclass(frozen=True)
class Cell:
    """Compiled models plus the handful of ids and poses the demo needs."""

    model: object
    ik_model: object
    picker: ArmKit
    helper: ArmKit
    bed_center: np.ndarray
    bed_half: np.ndarray
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

    def bed_corner(self, sign_x: float, sign_y: float, inset: float = 0.10) -> np.ndarray:
        """World xy of a bed corner, pulled in so the pads land on the plate."""
        return self.bed_center + np.array(
            [
                float(sign_x) * (float(self.bed_half[0]) - inset),
                float(sign_y) * (float(self.bed_half[1]) - inset),
            ]
        )


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


def _ik_model(hand: _Hand, mount_pos, mount_quat, integrator, prefix: str, mount_name: str):
    """The same arm on the same mount, with nothing else in the world."""
    import mujoco

    spec = mujoco.MjSpec()
    spec.option.integrator = integrator
    mount = spec.worldbody.add_body(name=mount_name, pos=mount_pos, quat=mount_quat)
    spec.attach(_arm_spec(stand_in=hand), prefix=prefix, frame=mount.add_frame())
    return spec.compile()


def _bind_kit(model, hand: _Hand, mount_pos, mount_quat, prefix: str, mount_name: str) -> ArmKit:
    """Read one attached arm out of the compiled cell."""
    return ArmKit(
        prefix=prefix,
        pinch_site_name=f"{prefix}{HAND_PREFIX}pinch",
        base=np.asarray(mount_pos[:2], dtype=float).copy(),
        ik_model=_ik_model(
            hand, mount_pos, mount_quat, model.opt.integrator, prefix, mount_name
        ),
        actuators=np.array([model.actuator(f"{prefix}{name}").id for name in _ARM_ACTUATOR_NAMES]),
        qposadr=np.array(
            [
                int(np.atleast_1d(model.joint(f"{prefix}{name}").qposadr)[0])
                for name in _ARM_JOINT_NAMES
            ]
        ),
        hand_actuator=model.actuator(f"{prefix}{HAND_PREFIX}fingers_actuator").id,
        hand_qposadr=int(
            np.atleast_1d(model.joint(f"{prefix}{HAND_JOINT}").qposadr)[0]
        ),
        pinch_site=model.site(f"{prefix}{HAND_PREFIX}pinch").id,
        empty_close=hand.empty_close,
        finger_reach=hand.finger_reach,
        seed_q=ARM_SEED_Q.copy(),
    )


def _world_box_half_xy(model, data, geom_name: str) -> np.ndarray:
    """World-xy half-extents of a box geom, after body yaw."""
    size = np.asarray(model.geom(geom_name).size, dtype=float)
    rot = np.asarray(data.geom(geom_name).xmat, dtype=float).reshape(3, 3)
    return (np.abs(rot) @ size)[:2]


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


# Collision bits. The cloth only touches geoms that carry CLOTH_BIT in their
# affinity; the hands carry HAND_BIT instead, so they still hit the press,
# the arms and each other but pass through the shirt.
WORLD_BIT = 1
CLOTH_BIT = 2
HAND_BIT = 4


def _keep_hands_off_cloth(model) -> None:
    """Let the shirt collide with everything except the two grippers.

    The hands hold cloth through PinchHold, not through finger contact. With
    contact on as well, the fingers close on vertices the spring is pulling
    into them, and the 2F-85's stiff, tiny-mass linkage takes the solver
    with it. Vertex spheres stay (cloth, world) so they hit the press and
    floor but not each other; flex-element contacts stay off (50-pair cap).
    """
    import mujoco

    hand_bodies = {
        index
        for index in range(model.nbody)
        if model.body(index).name.startswith((ARM_PREFIX + HAND_PREFIX, HELPER_PREFIX + HAND_PREFIX))
    }
    for index in range(model.ngeom):
        if model.geom_contype[index] == 0 and model.geom_conaffinity[index] == 0:
            continue
        body = int(model.geom_bodyid[index])
        body_name = model.body(body).name
        if body_name.startswith("shirt_") and model.geom_type[index] == mujoco.mjtGeom.mjGEOM_SPHERE:
            model.geom_contype[index] = CLOTH_BIT
            model.geom_conaffinity[index] = WORLD_BIT
            continue
        if body in hand_bodies:
            model.geom_contype[index] = HAND_BIT
            model.geom_conaffinity[index] = HAND_BIT | WORLD_BIT
        else:
            model.geom_conaffinity[index] |= CLOTH_BIT
    model.flex_contype[:] = 0
    model.flex_conaffinity[:] = 0
    # The broadphase prunes on per-body masks the compiler ORed together from
    # the geoms; rebuild them or the new bits are ignored.
    model.body_contype[:] = 0
    model.body_conaffinity[:] = 0
    for index in range(model.ngeom):
        body = int(model.geom_bodyid[index])
        model.body_contype[body] |= model.geom_contype[index]
        model.body_conaffinity[body] |= model.geom_conaffinity[index]


def build() -> Cell:
    """Compile the cell and the matching IK-only arm model."""
    import mujoco

    if not CELL_PATH.is_file():
        raise SystemExit(f"Missing scene: {CELL_PATH}")

    load_mujoco_plugins()
    hand = _measure_hand()
    spec = mujoco.MjSpec.from_file(CELL_PATH.as_posix())
    apply_shirt_config(spec, claws=False)
    half = 0.5 * PRESS_YAW
    spec.body("press_origin").quat = [math.cos(half), 0.0, 0.0, math.sin(half)]
    mounts = []
    for body_name, prefix in (
        (ARM_MOUNT_BODY, ARM_PREFIX),
        (HELPER_MOUNT_BODY, HELPER_PREFIX),
    ):
        mount = spec.body(body_name)
        mount_pos = np.array(mount.pos, dtype=float)
        mount_quat = np.array(mount.quat, dtype=float)
        spec.attach(_arm_spec(), prefix=prefix, frame=mount.add_frame())
        mounts.append((body_name, prefix, mount_pos, mount_quat))
    model = spec.compile()
    _keep_hands_off_cloth(model)

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
    picker = _bind_kit(model, hand, mounts[0][2], mounts[0][3], ARM_PREFIX, ARM_MOUNT_BODY)
    helper = _bind_kit(
        model, hand, mounts[1][2], mounts[1][3], HELPER_PREFIX, HELPER_MOUNT_BODY
    )

    return Cell(
        model=model,
        ik_model=picker.ik_model,
        picker=picker,
        helper=helper,
        bed_center=bed[:2].copy(),
        bed_half=_world_box_half_xy(model, data, "bed_plate"),
        bed_surface_z=bed_surface_z,
        bin_center=bin_site[:2].copy(),
        bin_surface_z=bin_surface_z,
        arm_base=picker.base.copy(),
        arm_actuators=picker.actuators,
        arm_qposadr=picker.qposadr,
        hand_actuator=picker.hand_actuator,
        hand_qposadr=picker.hand_qposadr,
        empty_close=picker.empty_close,
        press_yaw=PRESS_YAW,
        pinch_site=picker.pinch_site,
        finger_reach=picker.finger_reach,
        shirt_qposadr=shirt_vertex_qposadr(model),
        shirt_rest_world=shirt_rest_world(model, data),
        shirt_rest_local=shirt_rest_local(),
        shirt_collar_ids=shirt_collar_ids(),
        shirt_half_thickness=SHIRT_RADIUS,
        shirt_torso_half=shirt_torso_half(),
        shirt_band_local=shirt_band_local(),
    )


def spawn_shirt_in_bin(cell: Cell, data, rng: np.random.Generator) -> None:
    """Lay a shirt in the crate, folded in half down the spine.

    Flat, the T is wider than the crate. Folding the right half over the left
    along the spine gives a 0.42 x 0.57 m pack, which fits the crate's
    0.44 x 0.60 m inside once its length runs along the crate's long side.
    The fold is true to size: squeezing the mesh smaller than its rest
    lengths only makes the edge constraints spring it back out over the lip.
    The right sleeve ends up on top, at the front of the crate by the low lip,
    clear of the tall far wall.
    """
    local = cell.shirt_rest_local.copy()
    folded = local[:, 1] < 0.0
    local[folded, 1] = -local[folded, 1]
    local[folded, 2] += 0.010
    local -= local.mean(axis=0)
    local[:, 2] += 0.004 * np.sin(9.0 * local[:, 0])

    # Collar toward the front wall, near the arm; the crate leaves a
    # centimetre or two each side, so only a small twist fits.
    yaw = -0.5 * math.pi + float(rng.uniform(-0.03, 0.03))
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
