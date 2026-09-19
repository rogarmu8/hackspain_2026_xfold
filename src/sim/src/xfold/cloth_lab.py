"""Isolated cloth experiments; never writes live scene assets or pins cloth during stepping."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import mujoco
import numpy as np

from .platform import reexec_under_mjpython
from .shirt import MODELS_DIR, ShirtConfig, _add_vertex_spheres, add_shirt_contact_patches, contact_patch_warnings
from .sim_loop import smoothstep

LAB_XML = MODELS_DIR / "cloth_lab.xml"
FLAP_END = 4.5
FOLDER_PANELS = ('left', 'right', 'hem')
FOLDER_ANGLE = 2.95
FOLDER_SLOT = 6.0
FOLDER_DURATION = 18.5
FOLDER_MIN_FOOTPRINT = 0.95
FOLDER_CHECKPOINTS = (('left', FOLDER_SLOT), ('right', 2 * FOLDER_SLOT), ('hem', FOLDER_DURATION))


@dataclass(frozen=True)
class LabConfig:
    scenario: str = "drop"
    mesh: str = "grid"
    resolution: int = 13
    contact: str = "hybrid"
    patch_triangles: int = 8
    material: str = "edge"
    integrator: str = "Euler"
    solver: str = "CG"
    timestep: float = 0.002
    iterations: int = 80
    duration: float | None = None
    sample_interval: float = 0.1
    seed: int = 42
    layers: int = 3
    mass: float = 0.18
    young: float = 3000.0
    thickness: float = 0.001
    radius: float = 0.003
    damping: float = 0.02
    edge_damping: float = 0.1
    edge_timeconst: float = 0.02
    contact_timeconst: float = 0.008
    friction: float = 0.8
    fold_clearance_scale: float = 1.0
    fold_return_clearance: float = 0.025
    fold_angle: float = FOLDER_ANGLE

    def __post_init__(self) -> None:
        if self.duration is None:
            object.__setattr__(self, 'duration', FOLDER_DURATION if self.scenario == 'fold' else 5.5)

    def validate(self) -> None:
        for name, values in {
            "scenario": ("drop", "layers", "flap", "fold"), "mesh": ("grid", "tee"),
            "contact": ("proxy", "hybrid", "native", "partitioned"), "material": ("edge", "vert", "elastic"),
            "integrator": ("Euler", "discrete"), "solver": ("CG", "Newton"),
        }.items():
            if getattr(self, name) not in values:
                raise ValueError(f"Invalid {name}: {getattr(self, name)}")
        for name in ("timestep", "duration", "sample_interval", "mass", "young", "thickness", "radius", "edge_timeconst", "contact_timeconst"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("damping", "edge_damping", "friction", "fold_clearance_scale", "fold_return_clearance"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not 3 <= self.resolution <= 65 or self.iterations < 1 or self.layers not in (2, 3):
            raise ValueError("Resolution must be 3–65, iterations positive and layers 2 or 3")
        if not isinstance(self.patch_triangles, int) or not 1 <= self.patch_triangles <= 128:
            raise ValueError("Patch size must be an integer between 1 and 128 triangles")
        if not math.isfinite(self.fold_angle) or not 0 < self.fold_angle <= math.pi:
            raise ValueError('Fold angle must be between zero (exclusive) and pi radians')
        if self.scenario == 'fold' and 12 * self.radius * self.fold_clearance_scale + self.fold_return_clearance > .08:
            raise ValueError('Requested fold clearance exceeds the 80 mm lift stroke')
        if self.seed < 0:
            raise ValueError("Seed must be nonnegative")
        if self.mesh != "grid" and self.scenario == "layers":
            raise ValueError("The pre-folded layers experiment requires the grid mesh")
        if tuple(map(int, mujoco.__version__.split('.')[:2])) < (3, 13):
            raise ValueError("The cloth lab requires MuJoCo 3.13 or newer")


class SurfaceMetrics:
    def __init__(self, faces: np.ndarray):
        self.faces = np.asarray(faces, dtype=int)

    def intersections(self, positions: np.ndarray) -> int:
        triangles = positions[self.faces]
        low, high = triangles.min(axis=1), triangles.max(axis=1)
        count = 0
        for start in range(0, len(triangles), 128):
            stop = min(start + 128, len(triangles))
            overlap = np.all(low[start:stop, None] <= high[None] + 1e-10, axis=2)
            overlap &= np.all(low[None] <= high[start:stop, None] + 1e-10, axis=2)
            i, j = np.nonzero(overlap)
            i += start
            i, j = i[i < j], j[i < j]
            shared = np.any(self.faces[i, :, None] == self.faces[j, None, :], axis=(1, 2))
            count += self._intersections(triangles[i[~shared]], triangles[j[~shared]])
        return count

    @staticmethod
    def _intersections(a: np.ndarray, b: np.ndarray) -> int:
        if not len(a):
            return 0
        ea, eb = np.roll(a, -1, axis=1) - a, np.roll(b, -1, axis=1) - b
        na, nb = np.cross(ea[:, 0], ea[:, 1]), np.cross(eb[:, 0], eb[:, 1])
        axes = [na, nb]
        axes.extend(np.cross(ea[:, x], eb[:, y]) for x in range(3) for y in range(3))
        axes.extend(np.cross(n, e[:, x]) for n, e in ((na, ea), (nb, eb)) for x in range(3))
        hit = (np.linalg.norm(na, axis=1) > 1e-12) & (np.linalg.norm(nb, axis=1) > 1e-12)
        for axis in axes:
            length = np.linalg.norm(axis, axis=1)
            unit = axis / np.maximum(length[:, None], 1e-30)
            pa, pb = np.einsum('nij,nj->ni', a, unit), np.einsum('nij,nj->ni', b, unit)
            separated = (pa.max(axis=1) < pb.min(axis=1) - 1e-10) | (pb.max(axis=1) < pa.min(axis=1) - 1e-10)
            hit &= ~((length > 1e-12) & separated)
        return int(hit.sum())


def flap_target(t: float) -> float:
    if t < 0.75:
        return 0.0
    if t < 2.25:
        return 2.95 * smoothstep((t - 0.75) / 1.5)
    if t < 3.0:
        return 2.95
    return 2.95 * (1.0 - smoothstep((t - 3.0) / 1.5))


def folder_target(t: float, clearance: float, return_clearance: float, target_angle: float = FOLDER_ANGLE) -> tuple[float, float]:
    if t < 2.75:
        angle = target_angle * smoothstep((t - .75) / 1.5)
        return angle, clearance * (1 - math.cos(angle)) / 2
    closed = clearance * (1 - math.cos(target_angle)) / 2
    raised = clearance + return_clearance
    if t < 3.25:
        return target_angle, closed + (raised - closed) * smoothstep((t - 2.75) / .5)
    if t < 4.75:
        return target_angle * (1 - smoothstep((t - 3.25) / 1.5)), raised
    return 0.0, raised * (1 - smoothstep((t - 4.75) / .5))


def folder_phase(t: float) -> str:
    t = round(t, 9)
    if t >= 2 * FOLDER_SLOT + 5.25:
        return 'FINAL_SETTLE'
    index = min(int(t // FOLDER_SLOT), 2)
    local = t - index * FOLDER_SLOT
    action = next(label for end, label in ((.75, 'SETTLE'), (2.25, 'CLOSE'), (2.75, 'HOLD'), (3.25, 'CLEAR'), (4.75, 'OPEN'), (5.25, 'LOWER'), (float('inf'), 'SETTLE')) if local < end)
    return f'{FOLDER_PANELS[index].upper()}_{action}'


def _configure_folder(spec) -> tuple[np.ndarray, np.ndarray]:
    cloth = spec.flex('shirt')
    pos = np.asarray([spec.body(name).pos for name in cloth.vertbody])
    if len(cloth.vert):
        pos += np.asarray(cloth.vert).reshape(-1, 3)
    low, high = pos[:, :2].min(axis=0), pos[:, :2].max(axis=0)
    center, half = (low + high) / 2, (high - low) / [6, 2]
    x, y = half
    spec.body('folder').pos = [*center, 0]
    spec.geom('folder_table').pos = [0, y / 2 + .005, -.003]
    spec.geom('folder_table').size = [x - .0005, y / 2 + .005, .003]
    for name, sign in (('left', -1), ('right', 1)):
        spec.body(f'fold_{name}').pos = [sign * x, 0, 0]
        spec.geom(f'fold_{name}_plate').pos = [sign * (x + .005), 0, -.003]
        spec.geom(f'fold_{name}_plate').size = [x + .005, y + .01, .003]
    spec.geom('fold_hem_plate').pos = [0, -y / 2 - .0055, -.003]
    spec.geom('fold_hem_plate').size = [x - .0005, y / 2 + .005, .003]
    return center, half


class ClothLab:
    def __init__(self, config: LabConfig):
        config.validate()
        self.config = config
        root = ET.parse(LAB_XML).getroot()
        option = root.find('option')
        option.set('integrator', config.integrator)
        option.set('solver', config.solver)
        option.set('timestep', str(config.timestep))
        option.set('iterations', str(config.iterations))
        world = root.find('worldbody')
        flex = world.find('flexcomp')
        spacing = 0.48 / (config.resolution - 1)
        flex.set('count', f'{config.resolution} {config.resolution} 1')
        flex.set('spacing', f'{spacing} {spacing} {spacing}')
        if config.mesh == 'tee':
            flex.set('type', 'mesh')
            flex.set('file', str(MODELS_DIR / 'shirt_t.obj'))
            del flex.attrib['count']
            del flex.attrib['spacing']
        height = 0.25 if config.scenario == 'drop' else 0.05 if config.scenario == 'layers' else config.radius + 0.015
        flex.set('pos', f'0 0 {height}')
        flex.set('mass', str(config.mass))
        flex.set('radius', str(config.radius))
        edge, elastic, contact = flex.find('edge'), flex.find('elasticity'), flex.find('contact')
        edge.set('equality', {'edge': 'true', 'vert': 'vert', 'elastic': 'false'}[config.material])
        edge.set('damping', str(config.edge_damping))
        edge.set('solref', f'{config.edge_timeconst} 1')
        elastic.set('elastic2d', 'both' if config.material == 'elastic' else 'bend')
        for name in ('young', 'thickness', 'damping'):
            elastic.set(name, str(getattr(config, name)))
        mask = {'proxy': 0, 'hybrid': 4, 'native': 1, 'partitioned': 4}[config.contact]
        contact.set('contype', str(mask))
        contact.set('conaffinity', str(mask))
        contact.set('selfcollide', 'none' if config.contact == 'proxy' else 'auto')
        for element in (contact, root.find('default/geom')):
            element.set('friction', f'{config.friction} 0.005 0.0001')
            element.set('solref', f'{config.contact_timeconst} 1')
            element.set('solimp', '0.95 0.99 0.001')
        actuators = root.find('actuator')
        if config.scenario in ('flap', 'fold'):
            world.find("geom[@name='floor']").set('pos', '0 0 -0.5')
        if config.scenario != 'flap':
            world.remove(world.find("geom[@name='table']"))
            world.remove(world.find("body[@name='flap']"))
            actuators.remove(actuators.find("position[@name='flap_motor']"))
        if config.scenario != 'fold':
            world.remove(world.find("body[@name='folder']"))
            for actuator in list(actuators):
                if actuator.get('name', '').startswith('fold_'):
                    actuators.remove(actuator)
        xml = ET.tostring(root, encoding='unicode')
        self.runner_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        spec = mujoco.MjSpec.from_string(xml)
        self.folder_center = self.folder_half = None
        if config.scenario == 'fold':
            self.folder_center, self.folder_half = _configure_folder(spec)
        if config.contact != 'native':
            _add_vertex_spheres(spec, ShirtConfig(radius=config.radius, friction=config.friction))
            for geom in spec.geoms:
                if geom.group == 3:
                    geom.solref = [config.contact_timeconst, 1]
                    geom.solimp = [0.95, 0.99, 0.001, 0.5, 2]
        if config.contact == 'partitioned':
            add_shirt_contact_patches(spec, config.patch_triangles)
        with contact_patch_warnings():
            self.model = spec.compile()
            self.model_hash = hashlib.sha256(spec.to_xml().encode()).hexdigest()
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)
        f = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_FLEX, 'shirt')
        va, vn = int(self.model.flex_vertadr[f]), int(self.model.flex_vertnum[f])
        ea, en = int(self.model.flex_edgeadr[f]), int(self.model.flex_edgenum[f])
        self.vertex_slice, self.edge_slice = slice(va, va + vn), slice(ea, ea + en)
        bodies = self.model.flex_vertbodyid[self.vertex_slice]
        self.qadr = np.array([self.model.jnt_qposadr[self.model.body_jntadr[b]] for b in bodies])
        self.dadr = np.array([self.model.jnt_dofadr[self.model.body_jntadr[b]] for b in bodies])
        ta, tn = int(self.model.flex_elemdataadr[f]), int(self.model.flex_elemnum[f])
        self.faces = self.model.flex_elem[ta:ta + tn * 3].reshape(-1, 3).copy()
        self.surface = SurfaceMetrics(self.faces)
        self.rest = self.data.flexvert_xpos[self.vertex_slice].copy()
        rest_triangles = self.rest[self.faces]
        self.rest_areas = 0.5 * np.linalg.norm(np.cross(rest_triangles[:, 1] - rest_triangles[:, 0], rest_triangles[:, 2] - rest_triangles[:, 0]), axis=1)
        positions = self.rest.copy()
        rng = np.random.default_rng(config.seed)
        offset = rng.uniform(-0.005, 0.005, size=2)
        if config.scenario == 'layers':
            u = positions[:, 0] - positions[:, 0].min()
            width = float(np.ptp(u)) / config.layers
            layer = np.minimum((u / width).astype(int), config.layers - 1)
            local = u - layer * width
            positions[:, 0] = np.where(layer % 2, width - local, local) - width / 2
            positions[:, 2] += layer * 2.5 * config.radius
        positions[:, :2] += offset
        self.data.qpos[self.qadr[:, None] + np.arange(3)] = positions - self.rest
        self.initial_left = positions[:, 0] < -config.radius
        mujoco.mj_forward(self.model, self.data)
        self.physics_seconds = 0.0
        self.step_seconds: list[float] = []
        self.peak_contacts = 0
        self.peak_self_contacts = 0
        self.peak_self_contact_pair_contacts = 0
        self.peak_retained_penetration = 0.0

    def step(self) -> None:
        if self.config.scenario == 'flap':
            self.data.ctrl[0] = flap_target(self.data.time)
        elif self.config.scenario == 'fold':
            for index, name in enumerate(FOLDER_PANELS):
                clearance = (4, 6, 12)[index] * self.config.radius * self.config.fold_clearance_scale
                angle, lift = folder_target(self.data.time - index * FOLDER_SLOT, clearance, self.config.fold_return_clearance, self.config.fold_angle)
                self.data.actuator(f'fold_{name}_motor').ctrl[0] = angle
                self.data.actuator(f'fold_{name}_lift_motor').ctrl[0] = lift
        started = time.perf_counter()
        mujoco.mj_step(self.model, self.data)
        elapsed = time.perf_counter() - started
        self.physics_seconds += elapsed
        self.step_seconds.append(elapsed)
        n = self.data.ncon
        self.peak_contacts = max(self.peak_contacts, n)
        if n:
            flex = self.data.contact.flex
            pairs = np.sort(flex[np.all(flex >= 0, axis=1)], axis=1)
            self.peak_self_contacts = max(self.peak_self_contacts, len(pairs))
            if len(pairs):
                _, counts = np.unique(pairs, axis=0, return_counts=True)
                self.peak_self_contact_pair_contacts = max(self.peak_self_contact_pair_contacts, int(counts.max()))
            self.peak_retained_penetration = max(self.peak_retained_penetration, float(np.maximum(-self.data.contact.dist, 0).max()))

    def measure(self) -> dict:
        mujoco.mj_forward(self.model, self.data)
        pos = self.data.flexvert_xpos[self.vertex_slice]
        strain = np.abs(self.data.flexedge_length[self.edge_slice] / self.model.flexedge_length0[self.edge_slice] - 1)
        velocity = self.data.qvel[self.dadr[:, None] + np.arange(3)]
        triangles = pos[self.faces]
        areas = 0.5 * np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
        span = np.ptp(pos, axis=0)
        flap = self.config.scenario == 'flap'
        folder = self.config.scenario == 'fold'
        folding = {'folder_phase': folder_phase(self.data.time) if folder else None,
                   'packet_footprint_fraction': None}
        for name in FOLDER_PANELS:
            folding.update({
                f'{name}_fold_fraction': None,
                f'fold_{name}_angle_rad': float(self.data.joint(f'fold_{name}_hinge').qpos[0]) if folder else None,
                f'fold_{name}_lift_m': float(self.data.joint(f'fold_{name}_lift').qpos[0]) if folder else None,
                f'fold_{name}_torque_nm': float(self.data.actuator(f'fold_{name}_motor').force[0]) if folder else None,
            })
        if folder:
            x, y = self.folder_center
            hx, hy = self.folder_half
            tolerance = 2 * self.config.radius
            inside = (np.abs(pos[:, 0] - x) <= hx + tolerance) & (pos[:, 1] >= y - tolerance) & (pos[:, 1] <= y + hy + tolerance)
            folding['packet_footprint_fraction'] = float(np.mean(inside))
            for name, selected, folded in (
                ('left', self.rest[:, 0] < x - hx - 1e-9, pos[:, 0] >= x - hx - tolerance),
                ('right', self.rest[:, 0] > x + hx + 1e-9, pos[:, 0] <= x + hx + tolerance),
                ('hem', self.rest[:, 1] < y - 1e-9, pos[:, 1] >= y - tolerance),
            ):
                folding[f'{name}_fold_fraction'] = float(np.mean(folded[selected]))
        return {
            **folding,
            't_s': float(self.data.time),
            'edge_strain_p99': float(np.quantile(strain, 0.99)),
            'edge_strain_max': float(strain.max()),
            'surface_area_m2': float(areas.sum()),
            'degenerate_triangles': int(np.count_nonzero(areas <= 5e-13)),
            'min_triangle_area_ratio': float(np.min(areas / np.maximum(self.rest_areas, 1e-30))),
            'surface_intersection_pairs': self.surface.intersections(pos),
            'max_vertex_speed_m_s': float(np.linalg.norm(velocity, axis=1).max()),
            'rms_vertex_speed_m_s': float(np.sqrt(np.mean(np.sum(velocity**2, axis=1)))),
            'z_std_m': float(np.std(pos[:, 2])),
            'z_min_m': float(pos[:, 2].min()),
            'span_x_m': float(span[0]), 'span_y_m': float(span[1]), 'span_z_m': float(span[2]),
            'below_work_surface_vertices': int(np.count_nonzero(pos[:, 2] < -1e-4)),
            'left_vertices_on_right_fraction': float(np.mean(pos[self.initial_left, 0] > self.config.radius)) if flap else None,
            'flap_angle_rad': float(self.data.joint('flap_hinge').qpos[0]) if flap else None,
            'flap_target_rad': flap_target(self.data.time) if flap else None,
            'flap_torque_nm': float(self.data.actuator_force[0]) if flap else None,
            'contacts': int(self.data.ncon),
        }


def run_experiment(config: LabConfig, *, viewer=None, lab: ClothLab | None = None, on_checkpoint=None) -> dict:
    lab = lab or ClothLab(config)
    if lab.config != config or lab.data.time != 0:
        raise ValueError('Experiments require a fresh lab with matching configuration')
    data, model = lab.data, lab.model
    samples = [lab.measure()]
    checkpoints = {}
    targets = FOLDER_CHECKPOINTS if config.scenario == 'fold' else ()
    next_sample = config.sample_interval
    error = None
    started = time.perf_counter()
    steps = math.ceil(config.duration / config.timestep)
    for _ in range(steps):
        if viewer is not None and not viewer.is_running():
            error = 'Viewer closed before the requested duration'
            break
        before, step_started = data.time, time.perf_counter()
        try:
            lab.step()
        except mujoco.FatalError as exc:
            error = f'MuJoCo could not complete the physics step: {exc}'
            break
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all() or not math.isfinite(data.time) or data.time <= before or np.any(data.warning.number):
            error = 'Non-finite state, non-advancing time or MuJoCo warning'
            break
        reached = [name for name, t in targets if name not in checkpoints and data.time + 1e-9 >= t]
        if data.time + 1e-9 >= next_sample or data.time + 1e-9 >= config.duration or reached:
            samples.append(lab.measure())
            next_sample = data.time + config.sample_interval
            for name in reached:
                checkpoints[name] = samples[-1]
                if on_checkpoint is not None:
                    on_checkpoint(name, samples[-1])
        if viewer is not None:
            viewer.sync()
            time.sleep(max(0.0, config.timestep - (time.perf_counter() - step_started)))
    wall = time.perf_counter() - started
    sim_time = float(data.time) if math.isfinite(data.time) else None
    warnings = {mujoco.mjtWarning(i).name: int(n) for i, n in enumerate(data.warning.number) if n}
    return {
        'config': asdict(config),
        'provenance': {
            'mujoco': mujoco.__version__, 'numpy': np.__version__, 'platform': platform.platform(),
            'model_sha256': lab.model_hash,
            'runner_sha256': lab.runner_hash,
            'mesh_sha256': hashlib.sha256((MODELS_DIR / 'shirt_t.obj').read_bytes()).hexdigest() if config.mesh == 'tee' else None,
            'vertices': len(lab.qadr), 'triangles': len(lab.faces),
            'contact_patches': model.nflex - 1 if config.contact == 'partitioned' else 0,
            'collision_only_patches_share_original_bodies': config.contact == 'partitioned',
            'compiler_warning_policy': 'Only unconstrained collision-only shirt_contact_* flex warnings are filtered; their bodies use the original cloth mechanics.',
            'initial_condition': 'pre-folded connected sheet; initial strain is measured' if config.scenario == 'layers' else 'flat sheet with seeded XY offset',
            'cloth_state_writes_after_initialization': False, 'viewer': viewer is not None,
            'material_calibrated': False,
            'folder_center_m': lab.folder_center.tolist() if lab.folder_center is not None else None,
            'folder_deck_half_extents_m': lab.folder_half.tolist() if lab.folder_half is not None else None,
            'packet_footprint_tolerance_m': 2 * config.radius if config.scenario == 'fold' else None,
            'packet_footprint_target_fraction': FOLDER_MIN_FOOTPRINT if config.scenario == 'fold' else None,
            'packet_height_target_m': 14 * config.radius if config.scenario == 'fold' else None,
            'folder_lift_clearances_m': (np.array([4, 6, 12]) * config.radius * config.fold_clearance_scale).tolist() if config.scenario == 'fold' else None,
            'surface_metric': 'sampled triangle intersections; shared-vertex pairs and degenerate triangles excluded; no continuous collision detection',
        },
        'summary': {
            'numerically_valid': error is None, 'error': error, 'warnings': warnings,
            'sim_s': sim_time, 'wall_s': wall, 'physics_s': lab.physics_seconds,
            'failure_contacts': int(data.ncon) if error else None,
            'physics_real_time_factor': sim_time / lab.physics_seconds if lab.physics_seconds and sim_time is not None else None,
            'experiment_real_time_factor': sim_time / wall if wall and sim_time is not None else None,
            'step_p95_ms': float(np.quantile(lab.step_seconds, .95) * 1000) if lab.step_seconds else None,
            'peak_contacts': lab.peak_contacts, 'peak_self_contacts': lab.peak_self_contacts,
            'peak_self_contact_pair_contacts': lab.peak_self_contact_pair_contacts,
            'self_contact_cap_reached': lab.peak_self_contact_pair_contacts >= mujoco.mjMAXCONPAIR,
            'retained_contact_penetration_max_m': lab.peak_retained_penetration,
            'sampled_peak_surface_intersection_pairs': max(s['surface_intersection_pairs'] for s in samples),
            'sampled_peak_edge_strain_p99': max(s['edge_strain_p99'] for s in samples),
            'flap_schedule_completed': data.time + 1e-9 >= FLAP_END if config.scenario == 'flap' else None,
            'folder_schedule_completed': data.time + 1e-9 >= FOLDER_DURATION if config.scenario == 'fold' else None,
            'folder_footprint_target_met': samples[-1]['packet_footprint_fraction'] >= FOLDER_MIN_FOOTPRINT if config.scenario == 'fold' else None,
            'folder_height_target_met': samples[-1]['span_z_m'] <= 14 * config.radius if config.scenario == 'fold' else None,
            'physical_success': None,
        },
        'initial': samples[0], 'final': samples[-1], 'samples': samples, 'checkpoints': checkpoints,
    }


def save_results(results: list[dict], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    summary = [{key: value for key, value in result.items() if key != 'samples'} for result in results]
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    with (output / 'samples.csv').open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['experiment', *results[0]['samples'][0]])
        writer.writeheader()
        for index, result in enumerate(results):
            writer.writerows({'experiment': index, **sample} for sample in result['samples'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('drop', 'layers', 'flap', 'fold'), default='drop')
    parser.add_argument('--mesh', choices=('grid', 'tee'), default='grid')
    parser.add_argument('--contact', choices=('proxy', 'hybrid', 'native', 'partitioned'), default='hybrid')
    parser.add_argument('--material', choices=('edge', 'vert', 'elastic'), default='edge')
    parser.add_argument('--integrator', choices=('Euler', 'discrete'), default='Euler')
    parser.add_argument('--solver', choices=('CG', 'Newton'), default='CG')
    for name in ('resolution', 'iterations', 'seed', 'layers', 'patch_triangles'):
        parser.add_argument(f'--{name.replace("_", "-")}', type=int, default=getattr(LabConfig(), name))
    for name in ('timestep', 'duration', 'sample_interval', 'mass', 'young', 'thickness', 'radius', 'damping', 'edge_damping', 'edge_timeconst', 'contact_timeconst', 'friction', 'fold_clearance_scale', 'fold_return_clearance', 'fold_angle'):
        parser.add_argument(f'--{name.replace("_", "-")}', type=float, default=None if name == 'duration' else getattr(LabConfig(), name))
    parser.add_argument('--compare', action='store_true', help='Compare four contact modes and two integrators')
    parser.add_argument('--viewer', action='store_true', help='Open a single experiment in the MuJoCo viewer')
    parser.add_argument('--output', type=Path, help='New result directory; existing directories are never overwritten')
    args = parser.parse_args()
    if args.viewer and args.compare:
        parser.error('--viewer and --compare cannot be combined')
    cfg = LabConfig(**{name: getattr(args, name) for name in LabConfig.__dataclass_fields__})
    try:
        cfg.validate()
    except ValueError as exc:
        parser.error(str(exc))
    output = args.output or Path('data/cloth-lab') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if output.exists():
        parser.error(f'Output directory already exists: {output}')
    def report_checkpoint(name, sample):
        print(json.dumps({'checkpoint': name, 'measurement': sample}, allow_nan=False), flush=True)

    if args.viewer:
        reexec_under_mjpython('xfold.cloth_lab')
        import mujoco.viewer

        lab = ClothLab(cfg)
        with mujoco.viewer.launch_passive(lab.model, lab.data) as viewer:
            viewer.cam.lookat[:] = [0, 0, 0.1]
            viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = 1.6, 120, -30
            results = [run_experiment(cfg, viewer=viewer, lab=lab, on_checkpoint=report_checkpoint)]
    else:
        configs = [replace(cfg, contact=contact, integrator=integrator)
                   for contact in ('proxy', 'hybrid', 'native', 'partitioned') for integrator in ('Euler', 'discrete')] if args.compare else [cfg]
        results = []
        for current in configs:
            result = run_experiment(current, on_checkpoint=report_checkpoint)
            results.append(result)
            print(json.dumps({'config': asdict(current), 'summary': result['summary']}, allow_nan=False), flush=True)
    save_results(results, output)
    print(f'Results saved to {output}. Sequence completion is not validated physical success.')
    if any(not result['summary']['numerically_valid'] for result in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
