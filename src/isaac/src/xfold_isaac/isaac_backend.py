"""The Backend protocol on Isaac Sim 6.1: PhysX takes the physics steps.

  * cloth: a PhysX surface deformable on the flex mesh itself, so node i is
    flex vertex i. Read and written through DeformablePrim's nodal arrays.
  * bag: a dynamic rigid body. MuJoCo's free joint carries the velocity of
    the body origin and the spin in the body frame; PhysX wants the centre
    of mass and the world frame, so both are converted here.
  * mocap and jointed bodies with a collider: kinematic rigid bodies,
    teleported to the pose MuJoCo's kinematics give. A teleport, like a mocap
    body in MuJoCo, has no velocity for friction to use, which is what Line
    was written for: it carries the cloth on a flap or the peel explicitly.
  * a collider Line switches off (a flap swinging back empty) is not toggled
    on the GPU solver, which crashed PhysX mid-contact with the cloth: its
    kinematic body is parked PARK_DROP below the floor instead.
  * the picture is a separate, physics-free tree (usd_scene.VISUAL) posed
    from MjData on frames that render: bodies, cloth, bag films, belt slats,
    steam, lights. It never waits on PhysX publishing its state.

Import this only after SimulationApp is up (see run.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import carb
import mujoco
import numpy as np
from isaacsim.core.experimental.materials import SurfaceDeformableMaterial
from isaacsim.core.experimental.prims import DeformablePrim, RigidPrim
from isaacsim.core.simulation_manager import SimulationManager
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics

from . import usd_scene
from .usd_scene import SceneMap

# Kit steps physics itself on every app update while the timeline plays.
# Off, so app.update() only renders and physics steps exactly when Line does.
_PLAY_SIMULATIONS = "/app/player/playSimulations"
# Where a kinematic body goes while all its colliders are off.
PARK_DROP = 50.0


@dataclass(frozen=True)
class ClothPhysics:
    """PhysX surface-deformable settings for the garment.

    MuJoCo's shirt is inextensible edges (an equality per edge) plus a soft
    bend FEM. A surface deformable has no edge constraint, so stretch comes
    from a stiff membrane instead. Tune these on the box; ``run.py`` takes
    each as a flag.
    """

    mass: float = 0.18  # kg, shirt.toml
    youngs: float = 2.0e6  # Pa; membrane stiffness is youngs * thickness
    poisson: float = 0.3
    thickness: float = 0.001  # m, shirt.toml
    bend_stiffness: float = 2.0e-4
    friction: float = 0.8  # shirt.toml
    damping: float = 0.02
    # PhysX contact distance, and where the sheet rests. MuJoCo's contact
    # spheres are radius 0.003, and Line lays the cloth at SURFACE_Z + 0.003.
    rest_offset: float = 0.003
    contact_offset: float = 0.006
    self_collision: bool = True


def _set(prim: Usd.Prim, name: str, value, kind) -> None:
    attr = prim.GetAttribute(name)
    if not attr:
        attr = prim.CreateAttribute(name, kind)
    attr.Set(value)


class IsaacBackend:
    def __init__(self, app, stage: Usd.Stage, model, scene: SceneMap, cloth: ClothPhysics) -> None:
        self.app = app
        self.stage = stage
        self.scene = scene
        self._settings = carb.settings.get_settings()
        self._settings.set_bool(_PLAY_SIMULATIONS, False)

        self._setup_cloth(cloth)
        self.model = model
        self._kin_ids = np.asarray(scene.kinematic, dtype=int)
        self._kin = RigidPrim([scene.body_paths[b] for b in scene.kinematic], resolve_paths=False)
        self._kin_last: np.ndarray | None = None
        self._parked = np.zeros(len(self._kin_ids), dtype=bool)
        self._off: set[int] = set()
        self._bag = RigidPrim(scene.body_paths[scene.bag], resolve_paths=False)
        self._bag_com = np.asarray(model.body_ipos[scene.bag], dtype=float)

        self._rigid_view: Any = None
        self._cloth_view: Any = None
        self._kin_view: Any = None
        self._products: dict[tuple[str, int, int], object] = {}
        self.frames = 0

    # --- setup ---------------------------------------------------------

    def _setup_cloth(self, cfg: ClothPhysics) -> None:
        path = self.scene.cloth_path
        self.cloth = DeformablePrim(path, deformable_type="surface")
        prim = self.stage.GetPrimAtPath(path)
        _set(prim, "omniphysics:mass", float(cfg.mass), Sdf.ValueTypeNames.Float)
        _set(prim, "physxDeformableBody:selfCollision", bool(cfg.self_collision), Sdf.ValueTypeNames.Bool)
        collision = PhysxSchema.PhysxCollisionAPI.Apply(prim)
        collision.CreateRestOffsetAttr(float(cfg.rest_offset))
        collision.CreateContactOffsetAttr(float(cfg.contact_offset))
        material = SurfaceDeformableMaterial(
            f"{usd_scene.PHYSICS}/cloth_material",
            static_frictions=[cfg.friction],
            dynamic_frictions=[cfg.friction],
            youngs_moduli=[cfg.youngs],
            poissons_ratios=[cfg.poisson],
        )
        mat_prim = self.stage.GetPrimAtPath(f"{usd_scene.PHYSICS}/cloth_material")
        _set(mat_prim, "omniphysics:surfaceThickness", float(cfg.thickness), Sdf.ValueTypeNames.Float)
        _set(mat_prim, "omniphysics:surfaceBendStiffness", float(cfg.bend_stiffness), Sdf.ValueTypeNames.Float)
        _set(mat_prim, "physxDeformableMaterial:elasticityDamping", float(cfg.damping), Sdf.ValueTypeNames.Float)
        _set(mat_prim, "physxDeformableMaterial:bendDamping", float(cfg.damping), Sdf.ValueTypeNames.Float)
        self.cloth.apply_physics_materials(material)

    def start(self) -> None:
        """Play the timeline so PhysX loads the stage and the tensor views exist."""
        import isaacsim.core.experimental.utils.app as app_utils

        app_utils.play()
        self.app.update()
        SimulationManager.initialize_physics()
        self.app.update()
        if not self.cloth.is_physics_tensor_entity_valid():
            raise RuntimeError("PhysX did not create the cloth; is the GPU pipeline on?")
        self._bind_views()

    def _bind_views(self) -> None:
        """Hold the physics views, to read and write them without the wrappers.

        Every step moves the cloth and the bag both ways. The prim wrappers
        fetch the whole buffer before writing a slice of it, which measured as
        ~2.5 ms of the 8.6 ms step for the bag alone. Talking to the views
        directly halves that. Any version where the views are not reachable
        falls back to the wrappers.
        """
        import warp as wp

        self._wp = wp
        self._rigid_view = getattr(self._bag, "_physics_rigid_body_view", None)
        self._cloth_view = getattr(self.cloth, "_physics_deformable_body_view", None)
        if self._rigid_view is None or self._cloth_view is None:
            print("[isaac] physics views unavailable; using the prim wrappers", flush=True)
            return
        device = self._rigid_view.get_transforms().device
        self._one = wp.array([0], dtype=wp.int32, device=device)
        # PhysX transforms are xyz + quaternion xyzw; MuJoCo's is wxyz.
        self._tf = wp.zeros((1, 7), dtype=wp.float32, device=device)
        self._vel = wp.zeros((1, 6), dtype=wp.float32, device=device)
        nodes = int(self.cloth.num_nodes_per_body[0])
        self._nodes = wp.zeros((1, nodes, 3), dtype=wp.float32, device=device)
        self._kin_view = getattr(self._kin, "_physics_rigid_body_view", None)
        if self._kin_view is not None:
            count = len(self._kin_ids)
            self._kin_all = wp.array(np.arange(count, dtype=np.int32), dtype=wp.int32, device=device)
            self._kin_tf = wp.zeros((count, 7), dtype=wp.float32, device=device)

    # --- Backend -------------------------------------------------------

    def write_kinematics(self, model, data) -> None:
        pose = np.concatenate([data.xpos[self._kin_ids], data.xquat[self._kin_ids]], axis=1)
        pose[self._parked, 2] -= PARK_DROP
        if self._kin_last is not None and np.array_equal(pose, self._kin_last):
            return
        if self._kin_view is None:
            moved = (
                np.arange(len(pose))
                if self._kin_last is None
                else np.flatnonzero(np.any(pose != self._kin_last, axis=1))
            )
            self._kin.set_world_poses(
                positions=pose[moved, :3].astype(np.float32),
                orientations=pose[moved, 3:].astype(np.float32),
                indices=moved.astype(np.int32),
            )
        else:
            # The whole (small) view at once: an index array per moved subset
            # costs more than teleporting a body to where it already is.
            transforms = np.empty_like(pose, dtype=np.float32)
            transforms[:, :3] = pose[:, :3]
            transforms[:, 3:] = pose[:, [4, 5, 6, 3]]  # wxyz -> xyzw
            self._kin_tf.assign(transforms)
            self._kin_view.set_transforms(self._kin_tf, self._kin_all)
        self._kin_last = pose

    def write_cloth(self, pos: np.ndarray, vel: np.ndarray) -> None:
        if self._cloth_view is None:
            self.cloth.set_nodal_positions(pos[None].astype(np.float32))
            self.cloth.set_nodal_velocities(vel[None].astype(np.float32))
            return
        self._nodes.assign(pos[None].astype(np.float32))
        self._cloth_view.set_simulation_nodal_positions(self._nodes, self._one)
        self._nodes.assign(vel[None].astype(np.float32))
        self._cloth_view.set_simulation_nodal_velocities(self._nodes, self._one)

    def read_cloth(self) -> tuple[np.ndarray, np.ndarray]:
        if self._cloth_view is None:
            pos = self.cloth.get_nodal_positions()[0].numpy()[0].astype(float)
            vel = self.cloth.get_nodal_velocities().numpy()[0].astype(float)
            return pos, vel
        pos = self._cloth_view.get_simulation_nodal_positions().numpy()[0].astype(float)
        vel = self._cloth_view.get_simulation_nodal_velocities().numpy()[0].astype(float)
        return pos, vel

    def write_bag(self, qpos: np.ndarray, qvel: np.ndarray) -> None:
        rot = _rotation(qpos[3:7])
        spin = rot @ qvel[3:6]
        com_vel = qvel[:3] + np.cross(spin, rot @ self._bag_com)
        if self._rigid_view is None:
            self._bag.set_world_poses(
                positions=qpos[None, :3].astype(np.float32), orientations=qpos[None, 3:7].astype(np.float32)
            )
            self._bag.set_velocities(com_vel[None].astype(np.float32), spin[None].astype(np.float32))
            return
        transform = np.empty((1, 7), dtype=np.float32)
        transform[0, :3] = qpos[:3]
        transform[0, 3:] = (qpos[4], qpos[5], qpos[6], qpos[3])  # wxyz -> xyzw
        self._tf.assign(transform)
        self._rigid_view.set_transforms(self._tf, self._one)
        velocity = np.empty((1, 6), dtype=np.float32)
        velocity[0, :3] = com_vel
        velocity[0, 3:] = spin
        self._vel.assign(velocity)
        self._rigid_view.set_velocities(self._vel, self._one)

    def read_bag(self) -> tuple[np.ndarray, np.ndarray]:
        if self._rigid_view is None:
            pos, quat = self._bag.get_world_poses()
            lin, ang = self._bag.get_velocities()
            qpos = np.concatenate([pos.numpy()[0], quat.numpy()[0]]).astype(float)
            spin = ang.numpy()[0].astype(float)
            linear = lin.numpy()[0].astype(float)
        else:
            transform = self._rigid_view.get_transforms().numpy()[0].astype(float)
            velocity = self._rigid_view.get_velocities().numpy()[0].astype(float)
            qpos = np.empty(7)
            qpos[:3] = transform[:3]
            qpos[3:] = (transform[6], transform[3], transform[4], transform[5])  # xyzw -> wxyz
            linear, spin = velocity[:3], velocity[3:]
        qpos[3:7] /= np.linalg.norm(qpos[3:7])
        rot = _rotation(qpos[3:7])
        origin_vel = linear - np.cross(spin, rot @ self._bag_com)
        return qpos, np.concatenate([origin_vel, rot.T @ spin])

    def set_collisions(self, geoms: np.ndarray, enabled: np.ndarray) -> None:
        for geom, on in zip(geoms, enabled):
            if int(geom) in self.scene.collider_paths:
                (self._off.discard if on else self._off.add)(int(geom))
        bodies = self.model.geom_bodyid
        for index, body in enumerate(self._kin_ids):
            mine = [g for g in self.scene.collider_paths if bodies[g] == body]
            self._parked[index] = bool(mine) and all(g in self._off for g in mine)
        # A static collider, or a body only partly switched off, has nowhere
        # to be parked: toggle the shape itself.
        kinematic = set(self._kin_ids.tolist())
        for geom in geoms:
            path = self.scene.collider_paths.get(int(geom))
            if path is None or (int(bodies[geom]) in kinematic and self._parked[list(self._kin_ids).index(int(bodies[geom]))]):
                continue
            prim = self.stage.GetPrimAtPath(path)
            UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Set(int(geom) not in self._off)

    def sync_visuals(self, model, data, geoms: np.ndarray, lights: bool, cloth: np.ndarray) -> None:
        stage = self.stage
        with Sdf.ChangeBlock():
            for body in self.scene.moving:
                prim = stage.GetPrimAtPath(self.scene.visual_body_paths[body])
                prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*(float(v) for v in data.xpos[body])))
                prim.GetAttribute("xformOp:orient").Set(usd_scene._quat(data.xquat[body]))
            usd_scene.set_cloth_points(stage, self.scene, cloth)
            for geom in geoms:
                geom = int(geom)
                path = self.scene.geom_paths.get(geom)
                if path is None:
                    continue
                kind = self.scene.geom_kind[geom]
                prim = stage.GetPrimAtPath(path)
                rgba = usd_scene.geom_color(model, geom)
                usd_scene.set_material_color(stage, self.scene.material_paths[geom], rgba)
                image = UsdGeom.Imageable(prim)
                if usd_scene.geom_visible(model, geom, rgba):
                    image.MakeVisible()
                else:
                    image.MakeInvisible()
                if kind == mujoco.mjtGeom.mjGEOM_PLANE:
                    continue
                size = model.geom_size[geom]
                prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*(float(v) for v in model.geom_pos[geom])))
                prim.GetAttribute("xformOp:orient").Set(usd_scene._quat(model.geom_quat[geom]))
                prim.GetAttribute("xformOp:scale").Set(Gf.Vec3d(*usd_scene.geom_scale(kind, size)))
                usd_scene.set_geom_shape(prim, kind, size)
            if lights:
                for light, path in self.scene.light_paths.items():
                    lux = UsdLux.LightAPI(stage.GetPrimAtPath(path))
                    intensity, color = usd_scene.light_intensity(model.light_diffuse[light])
                    lux.GetIntensityAttr().Set(intensity)
                    lux.GetColorAttr().Set(color)
                dome = UsdLux.LightAPI(stage.GetPrimAtPath(self.scene.dome_path))
                dome.GetIntensityAttr().Set(usd_scene.dome_intensity(model))

    def step(self, render: bool) -> None:
        SimulationManager.step(steps=1)
        if render:
            self.render()

    def render(self) -> None:
        """One RTX frame (also what refreshes the cameras' annotators)."""
        self.app.update()
        self.frames += 1

    # --- cameras -------------------------------------------------------

    def camera_path(self, name: str) -> str:
        return self.scene.camera_paths.get(name, name)

    def capture(self, camera: str, width: int, height: int, *, fresh: bool = True) -> np.ndarray:
        """One RGB frame from a stage camera.

        ``fresh`` renders the stage as it is now (the QC photo, taken between
        physics steps); otherwise it is the frame the last rendered step made,
        which costs nothing extra (the video).
        """
        import omni.replicator.core as rep

        key = (self.camera_path(camera), width, height)
        annotator = self._products.get(key)
        if annotator is None:
            product = rep.create.render_product(key[0], (width, height))
            annotator = rep.AnnotatorRegistry.get_annotator("rgb")
            annotator.attach([product])
            self._products[key] = annotator
            # A fresh render product needs a few frames before it has pixels.
            for _ in range(4):
                self.app.update()
        if fresh:
            # Plain app updates, not rep.orchestrator.step(): after one of
            # those Replicator only refreshes annotators on its own steps, and
            # every later frame of the run came back stale. With
            # playSimulations off these render without stepping physics.
            for _ in range(3):
                self.app.update()
        frame = np.asarray(annotator.get_data())
        if frame.ndim != 3:  # no pixels yet
            return np.zeros((height, width, 3), dtype=np.uint8)
        return frame[..., :3]

    def set_camera(self, name: str, pos, forward) -> None:
        """Place (or create) a free camera looking along ``forward``."""
        path = f"/World/Cameras/{name}"
        prim = self.stage.GetPrimAtPath(path)
        if not prim:
            camera = UsdGeom.Camera.Define(self.stage, path)
            usd_scene.set_camera_fov(camera, 45.0, 16.0 / 9.0)
            usd_scene._xform_ops(camera, pos, usd_scene._look_quat(forward))
            self.scene.camera_paths[name] = path
            return
        prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*(float(v) for v in pos)))
        prim.GetAttribute("xformOp:orient").Set(usd_scene._quat(usd_scene._look_quat(forward)))


def create_backend(app, model, data, *, texture_dir: Path, cloth: ClothPhysics) -> IsaacBackend:
    """A fresh stage for ``model`` (posed as ``data``), with PhysX running.

    Also the rebuild path when the garment changes: whatever stage and
    simulation were there are stopped and replaced.
    """
    import isaacsim.core.experimental.utils.app as app_utils
    import isaacsim.core.experimental.utils.stage as stage_utils

    from .usd_scene import build_stage

    if app_utils.is_playing():
        app_utils.stop()
        app.update()
    stage_utils.create_new_stage()
    stage = stage_utils.get_current_stage(backend="usd")
    scene = build_stage(stage, model, data, texture_dir=texture_dir)
    SimulationManager.setup_simulation(dt=float(model.opt.timestep), device="cuda")
    app.update()
    backend = IsaacBackend(app, stage, model, scene, cloth)
    backend.start()
    return backend


def cloth_physics(**overrides) -> ClothPhysics:
    """ClothPhysics from shirt.toml's mass, thickness, friction and radius."""
    from xfold.shirt import shirt_config

    cfg = shirt_config()
    values = dict(
        mass=cfg.mass,
        thickness=cfg.thickness,
        friction=cfg.friction,
        rest_offset=cfg.radius,
        contact_offset=2.0 * cfg.radius,
    )
    values.update({k: v for k, v in overrides.items() if v is not None})
    return ClothPhysics(**values)


def _rotation(quat) -> np.ndarray:
    rot = np.empty(9)
    mujoco.mju_quat2Mat(rot, np.asarray(quat, dtype=float))
    return rot.reshape(3, 3)


def save_png(frame: np.ndarray, path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(frame)).save(path)
