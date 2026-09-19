"""Run xfold.line.Line on a physics engine other than MuJoCo.

Line only reaches MuJoCo through ``self._mujoco``: mj_resetData, mj_forward,
mj_step and a couple of quaternion helpers. Everything else it does is read
and write model/data arrays: cloth vertex qpos/qvel, mocap poses, the press
actuator's ctrl, the bag's free joint, geom colours and sizes, light levels.

EngineShim takes the place of that module. The MjModel/MjData stay what they
are for the MuJoCo line, the plant's description and the controller's state,
but each mj_step hands what the controller wrote to a Backend, lets the
backend's engine take the step, and copies the result back. So the phases,
timings and measurements come from the same Line the dashboard runs; only
the physics underneath changes.

What the backend owns:
  * the cloth, both ways: Line pins and drives vertices by writing qpos/qvel,
    the engine moves the free ones;
  * the bag, both ways: Line holds it and belt 2 drives it, the engine drops
    it into the carton;
  * every mocap or jointed body, one way: the engine only sees where they are.

The press stroke is the one actuated joint. The engine sees the platen as a
kinematic body, so the servo is integrated here with MuJoCo's own gains
(``_Servo``).
"""

from __future__ import annotations

from typing import Protocol

import mujoco
import numpy as np

# MuJoCo's default geom rgba: a geom left at it shows its material's colour.
DEFAULT_RGBA = np.array([0.5, 0.5, 0.5, 1.0])
# The renderer's default geom groups; 3 and up are hidden (collision boxes,
# the cloth's contact spheres).
VISIBLE_GROUPS = 3


class Backend(Protocol):
    """The physics a Line runs on, as EngineShim needs it."""

    def write_kinematics(self, model, data) -> None:
        """Pose every mocap or jointed body; data's xpos/xquat are current."""

    def write_cloth(self, pos: np.ndarray, vel: np.ndarray) -> None:
        """World positions and velocities of every cloth vertex, (n, 3) each."""

    def read_cloth(self) -> tuple[np.ndarray, np.ndarray]:
        """Cloth vertex positions and velocities after the last step."""

    def write_bag(self, qpos: np.ndarray, qvel: np.ndarray) -> None:
        """The bag's free joint, in MuJoCo's convention: origin + wxyz quat,
        origin velocity in world, angular velocity in the body frame."""


    def read_bag(self) -> tuple[np.ndarray, np.ndarray]:
        """The bag's free joint after the last step, same convention."""

    def set_collisions(self, geoms: np.ndarray, enabled: np.ndarray) -> None:
        """Turn these geoms' colliders on or off."""

    def sync_visuals(self, model, data, geoms: np.ndarray, lights: bool, cloth: np.ndarray) -> None:
        """Bring the picture up to date: moving bodies from data, these geoms'
        pose, size and colour, the lights if ``lights``, the cloth at ``cloth``."""

    def step(self, render: bool) -> None:
        """Advance one physics step; ``render`` if a frame is due."""


def geom_color(model, geom: int) -> np.ndarray:
    """The colour MuJoCo draws a geom in: its material's unless rgba was set."""
    rgba = model.geom_rgba[geom]
    mat = int(model.geom_matid[geom])
    if mat >= 0 and np.allclose(rgba, DEFAULT_RGBA):
        return model.mat_rgba[mat].copy()
    return rgba.copy()


def cloth_geoms(model) -> np.ndarray:
    """Ids of the per-vertex contact spheres, which are the cloth, not the plant."""
    flex_bodies = np.asarray(model.flex_vertbodyid)
    return np.flatnonzero(np.isin(model.geom_bodyid, flex_bodies))


def _collides(ct_a, ca_a, ct_b, ca_b):
    return ((ct_a & ca_b) | (ct_b & ca_a)) != 0


def collision_mask(model, bag_body: int | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Which plant geoms need a collider, by MuJoCo's contype/conaffinity rule.

    Only two things move under physics: the cloth and the bag. A geom needs a
    collider if MuJoCo would let it touch either. Returns (collider, with
    cloth, with bag), each a bool per geom; cloth spheres are all False.
    """
    ct = model.geom_contype.astype(int)
    ca = model.geom_conaffinity.astype(int)
    sphere = cloth_geoms(model)
    plant = np.ones(model.ngeom, dtype=bool)
    plant[sphere] = False
    if sphere.size:
        cloth_ct, cloth_ca = int(ct[sphere[0]]), int(ca[sphere[0]])
    else:
        cloth_ct = cloth_ca = 0
    with_cloth = _collides(ct, ca, cloth_ct, cloth_ca) & plant
    with_bag = np.zeros(model.ngeom, dtype=bool)
    is_bag = np.zeros(model.ngeom, dtype=bool)
    if bag_body is not None:
        is_bag = model.geom_bodyid == bag_body
        for geom in np.flatnonzero(is_bag & ((ct | ca) != 0)):
            with_bag |= _collides(ct, ca, ct[geom], ca[geom])
        with_bag &= plant & ~is_bag
    collider = with_cloth | with_bag | (is_bag & ((ct | ca) != 0))
    return collider, with_cloth, with_bag


class _Servo:
    """A MuJoCo position actuator on a slide or hinge joint, integrated here.

    The press stroke is the only one in line.xml. The engine sees the platen as
    a kinematic body, so this reproduces MuJoCo's servo: same gain and bias,
    joint damping taken implicitly as MuJoCo's Euler integrator does, gravity
    less the body's gravcomp, the joint range. What it does not feel is the
    cloth under it: at full stroke the platen stops 1 mm above the belt, and
    the cloth is pinned while it is down.
    """

    def __init__(self, model, actuator: int) -> None:
        if int(model.actuator_trntype[actuator]) != int(mujoco.mjtTrn.mjTRN_JOINT):
            raise NotImplementedError("only joint actuators are supported")
        if int(model.actuator_dyntype[actuator]) != int(mujoco.mjtDyn.mjDYN_NONE):
            raise NotImplementedError("only actuators without activation dynamics")
        if int(model.actuator_gaintype[actuator]) != int(mujoco.mjtGain.mjGAIN_FIXED):
            raise NotImplementedError("only fixed-gain actuators")
        if int(model.actuator_biastype[actuator]) != int(mujoco.mjtBias.mjBIAS_AFFINE):
            raise NotImplementedError("only affine-bias (position) actuators")
        joint = int(model.actuator_trnid[actuator, 0])
        kind = int(model.jnt_type[joint])
        if kind not in (int(mujoco.mjtJoint.mjJNT_SLIDE), int(mujoco.mjtJoint.mjJNT_HINGE)):
            raise NotImplementedError("only slide and hinge joints")
        self.actuator = actuator
        self.joint = joint
        self.slide = kind == int(mujoco.mjtJoint.mjJNT_SLIDE)
        self.qadr = int(model.jnt_qposadr[joint])
        self.dadr = int(model.jnt_dofadr[joint])
        self.gear = float(model.actuator_gear[actuator, 0])
        self.gain = float(model.actuator_gainprm[actuator, 0])
        self.bias = model.actuator_biasprm[actuator, :3].astype(float).copy()
        self.mass = float(model.dof_M0[self.dadr])
        self.damping = float(model.dof_damping[self.dadr])
        self.ctrl_range = (
            model.actuator_ctrlrange[actuator].copy() if model.actuator_ctrllimited[actuator] else None
        )
        self.range = model.jnt_range[joint].copy() if model.jnt_limited[joint] else None
        body = int(model.jnt_bodyid[joint])
        self.weight = float(model.body_subtreemass[body]) * (1.0 - float(model.body_gravcomp[body]))
        self.gravity = np.asarray(model.opt.gravity, dtype=float)

    def step(self, data, dt: float) -> None:
        ctrl = float(data.ctrl[self.actuator])
        if self.ctrl_range is not None:
            ctrl = float(np.clip(ctrl, *self.ctrl_range))
        q = float(data.qpos[self.qadr])
        qd = float(data.qvel[self.dadr])
        force = self.gear * (self.gain * ctrl + self.bias[0] + self.bias[1] * q + self.bias[2] * qd)
        if self.slide and self.weight:
            force += self.weight * float(self.gravity @ data.xaxis[self.joint])
        qd = (qd + dt * force / self.mass) / (1.0 + dt * self.damping / self.mass)
        q += dt * qd
        if self.range is not None and not self.range[0] <= q <= self.range[1]:
            q = float(np.clip(q, *self.range))
            qd = 0.0
        data.qpos[self.qadr] = q
        data.qvel[self.dadr] = qd


class _VisualState:
    """What the backend was last told about geom visuals and lights."""

    def __init__(self, model, geoms: np.ndarray) -> None:
        self.geoms = geoms
        self._geom: np.ndarray | None = None
        self._light: np.ndarray | None = None

    @staticmethod
    def _geom_rows(model, geoms: np.ndarray) -> np.ndarray:
        color = np.array([geom_color(model, g) for g in geoms]).reshape(len(geoms), 4)
        return np.concatenate(
            [model.geom_pos[geoms], model.geom_quat[geoms], model.geom_size[geoms], color], axis=1
        )

    @staticmethod
    def _light_row(model) -> np.ndarray:
        return np.concatenate(
            [
                model.light_diffuse.ravel(),
                np.asarray(model.vis.headlight.diffuse, dtype=float),
                np.asarray(model.vis.headlight.ambient, dtype=float),
            ]
        )

    def changes(self, model) -> tuple[np.ndarray, bool]:
        rows = self._geom_rows(model, self.geoms)
        lights = self._light_row(model)
        if self._geom is None:
            changed = self.geoms
            lit = True
        else:
            changed = self.geoms[np.any(rows != self._geom, axis=1)]
            lit = bool(np.any(lights != self._light))
        self._geom, self._light = rows, lights
        return changed, lit


class EngineShim:
    """Stands in for the ``mujoco`` module inside a Line; see the module doc.

    Build the Line first (its constructor resets the real MjData), then wrap
    it: ``EngineShim(line, backend)``. From then on ``line.step()`` steps the
    backend. ``render_every`` physics steps, the backend is asked to render.
    """

    def __init__(self, line, backend: Backend, *, render_every: int = 0) -> None:
        self.line = line
        self.model = line.model
        self.data = line.data
        self.backend = backend
        self.render_every = int(render_every)
        self.dt = float(self.model.opt.timestep)
        self.steps = 0
        self._qadr = line._qadr
        self._dadr = line._dadr
        self._rest = line._rest
        self._xyz = np.arange(3)
        self._bag_q = slice(line._bag_qadr, line._bag_qadr + 7)
        self._bag_v = slice(line._bag_dadr, line._bag_dadr + 6)
        self._bag_body = int(line._bag)
        self._servos = [_Servo(self.model, a) for a in range(self.model.nu)]
        self._collider = collision_mask(self.model, self._bag_body)[0]
        plant = np.setdiff1d(np.arange(self.model.ngeom), cloth_geoms(self.model))
        self._visual = _VisualState(self.model, plant)
        # What the backend holds, as of the last read, so an untouched cloth or
        # bag is not written back every step.
        self._held: tuple[np.ndarray, ...] | None = None
        self._bag_held = False
        line._mujoco = self

    def __getattr__(self, name: str):
        return getattr(mujoco, name)

    # --- the three calls Line makes ------------------------------------

    def mj_resetData(self, model, data) -> None:  # noqa: N802 — MuJoCo's name
        mujoco.mj_resetData(model, data)
        self._held = None

    def mj_step(self, model, data) -> None:  # noqa: N802 — MuJoCo's name
        for servo in self._servos:
            servo.step(data, self.dt)
        mujoco.mj_kinematics(model, data)
        self.backend.write_kinematics(model, data)
        self._write_state()
        collider = collision_mask(model, self._bag_body)[0]
        flipped = np.flatnonzero(collider != self._collider)
        if flipped.size:
            self.backend.set_collisions(flipped, collider[flipped])
            self._collider = collider
        render = self.render_every > 0 and self.steps % self.render_every == 0
        if render:
            self.sync_visuals()
        self.backend.step(render)
        self.steps += 1
        self._read_state()
        data.time += self.dt
        # Body poses are recomputed at the top of the next step, once the
        # controller has written this step's mocap and ctrl: xpos a step old
        # is what Line's next pass reads (a couple of millimetres on the belt)
        # and what the picture is posed from.

    # --- helpers -------------------------------------------------------

    def sync_visuals(self) -> None:
        """Send the backend the frame: body poses, cloth, and whatever geoms
        and lights changed since last time."""
        geoms, lights = self._visual.changes(self.model)
        self.backend.sync_visuals(self.model, self.data, geoms, lights, self.cloth()[0])

    def cloth(self) -> tuple[np.ndarray, np.ndarray]:
        data = self.data
        pos = self._rest + data.qpos[self._qadr[:, None] + self._xyz]
        vel = data.qvel[self._dadr[:, None] + self._xyz].copy()
        return pos, vel

    def _state(self) -> tuple[np.ndarray, ...]:
        pos, vel = self.cloth()
        return pos, vel, self.data.qpos[self._bag_q].copy(), self.data.qvel[self._bag_v].copy()

    def _write_state(self) -> None:
        pos, vel, bag_q, bag_v = self._state()
        held = self._held
        if held is None or not (np.array_equal(pos, held[0]) and np.array_equal(vel, held[1])):
            self.backend.write_cloth(pos, vel)
        # A bag pose that is not the one the engine gave back means Line is
        # holding the bag (the magazine, the picker, the opener): it re-asserts
        # that pose after every step, so reading the engine's is pointless.
        self._bag_held = held is not None and not np.array_equal(bag_q, held[2])
        if held is None or self._bag_held or not np.array_equal(bag_v, held[3]):
            self.backend.write_bag(bag_q, bag_v)

    def _read_state(self) -> None:
        data = self.data
        pos, vel = self.backend.read_cloth()
        data.qpos[self._qadr[:, None] + self._xyz] = pos - self._rest
        data.qvel[self._dadr[:, None] + self._xyz] = vel
        if not self._bag_held:
            bag_q, bag_v = self.backend.read_bag()
            data.qpos[self._bag_q] = bag_q
            data.qvel[self._bag_v] = bag_v
        self._held = self._state()
