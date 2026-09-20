"""Shirt flexcomp parameters, config, and geometry helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .claws import add_claw_bodies
from .garments import resolve_garment

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
DEFAULT_CONFIG = MODELS_DIR / "shirt.toml"
PLAYGROUND_XML = MODELS_DIR / "shirt_playground.xml"
PLAYGROUND_HI_XML = MODELS_DIR / "shirt_playground_hi.xml"
PLAYGROUND_PONCHO_XML = MODELS_DIR / "shirt_playground_poncho.xml"
SHIRT_XML = MODELS_DIR / "shirt.xml"
CELL_XML = MODELS_DIR / "cell.xml"
ACTIVE_SHIRT_XML = MODELS_DIR / "_garment_active.xml"
ACTIVE_SCENE_XML = MODELS_DIR / "_scene_active.xml"

# Matches models/shirt.toml — bend FEM + edge equality. young is calibrated
# to cotton jersey there; the mesh, not young, is what sets the drape.
# Flex-vs-one-plane is still one pair (mjMAXCONPAIR=50). Ground support
# comes from per-vertex sphere geoms added in apply_shirt_config.
SHIRT_CONTACT_BUDGET = 50
SHIRT_SPAWN_POS = (0.15, 0.0, 0.098)
SHIRT_SOLREF = "0.005 1"
SHIRT_SOLIMP = "0.95 0.99 0.001"
SHIRT_EDGE_DAMPING = 0.1
# elastic2d: 0=none, 1=bend, 2=stretch, 3=both. Bend + edge equality.
SHIRT_ELASTIC2D_BEND = 1


@dataclass(frozen=True)
class ShirtConfig:
    """Editable knobs from shirt.toml."""

    mass: float = 0.18
    young: float = 3.0e3
    poisson: float = 0.0
    thickness: float = 0.001
    damping: float = 0.02
    edge_damping: float = 0.1
    radius: float = 0.003
    friction: float = 0.8
    timestep: float = 0.002
    iterations: int = 80
    claw_force: float = 12.0
    claw_hz: float = 5.0
    garment: str = "tee"
    mesh: str = "shirt_t.obj"
    texture: str = "shirt_print.png"
    path: Path = DEFAULT_CONFIG


def _config_path() -> Path:
    env = os.environ.get("XFOLD_SHIRT_CONFIG", "").strip()
    return Path(env).expanduser() if env else DEFAULT_CONFIG


def load_shirt_config(path: Path | None = None) -> ShirtConfig:
    """Read shirt.toml (or XFOLD_SHIRT_CONFIG). Missing file → defaults."""
    import tomllib

    src = path or _config_path()
    if not src.is_file():
        return ShirtConfig(path=src)
    raw = tomllib.loads(src.read_text(encoding="utf-8"))
    cloth = raw.get("cloth", {})
    solver = raw.get("solver", {})
    fold = raw.get("fold", {})
    garment_raw = raw.get("garment", {})
    env_kind = os.environ.get("XFOLD_GARMENT", "").strip()
    kind = env_kind or str(garment_raw.get("type", "tee"))
    item = resolve_garment(kind)
    return ShirtConfig(
        mass=float(cloth.get("mass", 0.18)),
        young=float(cloth.get("young", 3.0e3)),
        poisson=float(cloth.get("poisson", 0.0)),
        thickness=float(cloth.get("thickness", 0.001)),
        damping=float(cloth.get("damping", 0.02)),
        edge_damping=float(cloth.get("edge_damping", 0.1)),
        radius=float(cloth.get("radius", 0.003)),
        friction=float(cloth.get("friction", 0.8)),
        timestep=float(solver.get("timestep", 0.002)),
        iterations=int(solver.get("iterations", 80)),
        claw_force=float(fold.get("claw_force", 12.0)),
        claw_hz=float(fold.get("claw_hz", 5.0)),
        garment=item.key,
        mesh=item.mesh,
        texture=item.texture,
        path=src,
    )


_CFG = load_shirt_config()
SHIRT_MASS = _CFG.mass
SHIRT_YOUNG = _CFG.young
SHIRT_POISSON = _CFG.poisson
SHIRT_THICKNESS = _CFG.thickness
SHIRT_RADIUS = _CFG.radius
SHIRT_MESH = _CFG.mesh


def shirt_config() -> ShirtConfig:
    return _CFG


def select_garment(name: str, *, texture: str | None = None) -> ShirtConfig:
    """Switch the active catalogue item (CLI / XFOLD_GARMENT).

    ``texture`` overrides the catalogue PNG (custom operator print).
    """
    global _CFG, _MESH_CACHE, SHIRT_MESH
    item = resolve_garment(name)
    if item.key == "custom":
        from xfold.generate_shirt_mesh import ensure_custom_mesh

        ensure_custom_mesh()
    _MESH_CACHE = None
    _CFG = ShirtConfig(
        mass=_CFG.mass,
        young=_CFG.young,
        poisson=_CFG.poisson,
        thickness=_CFG.thickness,
        damping=_CFG.damping,
        edge_damping=_CFG.edge_damping,
        radius=_CFG.radius,
        friction=_CFG.friction,
        timestep=_CFG.timestep,
        iterations=_CFG.iterations,
        claw_force=_CFG.claw_force,
        claw_hz=_CFG.claw_hz,
        garment=item.key,
        mesh=item.mesh,
        texture=texture or item.texture,
        path=_CFG.path,
    )
    SHIRT_MESH = _CFG.mesh
    return _CFG


def apply_shirt_config(spec, cfg: ShirtConfig | None = None, *, claws: bool = True):
    """Write config onto an MjSpec before compile()."""
    import mujoco

    cfg = cfg or shirt_config()
    spec.option.timestep = cfg.timestep
    spec.option.iterations = cfg.iterations
    # Bend FEM is not integrated under implicit / implicitfast.
    spec.option.integrator = int(mujoco.mjtIntegrator.mjINT_EULER)
    flex_name = "shirt"
    for flex in spec.flexes:
        if flex.name and flex.name != "shirt":
            continue
        flex_name = str(flex.name or "shirt")
        flex.young = cfg.young
        flex.poisson = cfg.poisson
        flex.thickness = cfg.thickness
        flex.damping = cfg.damping
        flex.edgedamping = cfg.edge_damping
        flex.elastic2d = SHIRT_ELASTIC2D_BEND
        flex.radius = cfg.radius
        flex.selfcollide = mujoco.mjtFlexSelf.mjFLEXSELF_NONE
        fr = np.asarray(flex.friction, dtype=np.float64)
        if fr.size:
            fr = fr.copy()
            fr[0] = cfg.friction
            flex.friction = fr
        # Flex-element vs one floor is one pair (50 contacts). Vertex
        # spheres below carry the ground / press / arm contacts instead.
        flex.contype = 0
        flex.conaffinity = 0
        break
    _ensure_edge_equality(spec, flex_name)
    bodies = [b for b in spec.bodies if str(getattr(b, "name", "")).startswith("shirt_")]
    current = float(sum(float(b.mass) for b in bodies))
    if bodies and current > 1e-9:
        scale = cfg.mass / current
        for body in bodies:
            body.mass = float(body.mass) * scale
    _add_vertex_spheres(spec, cfg)
    if claws:
        add_claw_bodies(spec)
    nvert = max(len(bodies), 1)
    spec.nconmax = max(int(spec.nconmax or 0), nvert + 2048)


def _ensure_edge_equality(spec, flex_name: str) -> None:
    """One mjEQ_FLEX so edges cannot stretch (poncho / flag recipe)."""
    import mujoco

    flex_eq = int(mujoco.mjtEq.mjEQ_FLEX)
    for eq in spec.equalities:
        if int(eq.type) == flex_eq and (eq.name1 == flex_name or not eq.name1):
            eq.active = True
            if not eq.name1:
                eq.name1 = flex_name
            return
    eq = spec.add_equality()
    eq.type = flex_eq
    eq.name1 = flex_name
    eq.active = True


def _add_vertex_spheres(spec, cfg: ShirtConfig) -> int:
    """One collision sphere per flex vertex — each is its own floor pair.

    Spheres use contype=2 / conaffinity=1 so they hit the world (floor,
    press, arms) and *not* each other. After a ninja fold the thirds
    stack; sphere-sphere contacts were pumping random motion into a
    shirt that no claw was touching.
    """
    import mujoco

    added = 0
    for body in spec.bodies:
        name = str(getattr(body, "name", "") or "")
        if not name.startswith("shirt_"):
            continue
        geoms = list(getattr(body, "geoms", []))
        if any(int(getattr(g, "type", -1)) == int(mujoco.mjtGeom.mjGEOM_SPHERE) for g in geoms):
            continue
        geom = body.add_geom()
        geom.type = mujoco.mjtGeom.mjGEOM_SPHERE
        geom.size = np.array([cfg.radius, 0.0, 0.0], dtype=np.float64)
        # World is contype=1, conaffinity=1. (2&1)|(1&1) hits the floor;
        # (2&1)|(2&1) does not hit another shirt sphere.
        geom.contype = 2
        geom.conaffinity = 1
        geom.condim = 3
        geom.friction = np.array([cfg.friction, 0.005, 0.0001], dtype=np.float64)
        geom.solref = np.array([0.008, 1.0], dtype=np.float64)
        geom.density = 0.0
        geom.mass = 0.0
        geom.group = 3
        geom.rgba = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)
        added += 1
    return added


def spec_from_mjcf(xml_path: Path, cfg: ShirtConfig | None = None):
    """Load an MJCF scene with the active garment mesh and texture."""
    import mujoco

    cfg = cfg or shirt_config()
    shirt = SHIRT_XML.read_text(encoding="utf-8")
    shirt = shirt.replace("shirt_t.obj", cfg.mesh)
    shirt = shirt.replace("shirt_print.png", cfg.texture)
    ACTIVE_SHIRT_XML.write_text(shirt, encoding="utf-8")
    text = xml_path.read_text(encoding="utf-8")
    text = text.replace('include file="shirt.xml"', 'include file="_garment_active.xml"')
    text = text.replace('file="shirt_t.obj"', f'file="{cfg.mesh}"')
    text = text.replace('file="shirt_print.png"', f'file="{cfg.texture}"')
    if xml_path.resolve() == SHIRT_XML.resolve():
        return mujoco.MjSpec.from_file(ACTIVE_SHIRT_XML.as_posix())
    ACTIVE_SCENE_XML.write_text(text, encoding="utf-8")
    return mujoco.MjSpec.from_file(ACTIVE_SCENE_XML.as_posix())


def load_mjcf(xml_path: Path, cfg: ShirtConfig | None = None, *, claws: bool = True):
    """Compile an MJCF scene with shirt.toml applied."""
    import mujoco

    load_mujoco_plugins()
    cfg = cfg or shirt_config()
    spec = spec_from_mjcf(xml_path, cfg)
    apply_shirt_config(spec, cfg, claws=claws)
    model = spec.compile()
    data = mujoco.MjData(model)
    return model, data


# Press bed centre / half-extents from cell.xml (for smoke AABB checks).
# Bed is the size of the T plus sleeves (SOLUTION.md §5.2).
PRESS_BED_POS = np.array([0.15, 0.0, 0.08], dtype=np.float64)
PRESS_BED_HALF = np.array([0.48, 0.40, 0.015], dtype=np.float64)

# Steam: raise edge damping so wrinkles relax under the platen (§5.2).
# Stay under ~0.5 — higher edge damping pumps energy into the equalities.
STEAM_EDGE_DAMPING = 0.4
DRY_EDGE_DAMPING = SHIRT_EDGE_DAMPING


def load_mujoco_plugins() -> None:
    """Load bundled MuJoCo plugins (safe no-op if already loaded)."""
    import mujoco

    load = getattr(mujoco, "_load_all_bundled_plugins", None)
    if callable(load):
        load()
        return
    plugin_dir = Path(mujoco.__file__).resolve().parent / "plugin"
    if plugin_dir.is_dir():
        mujoco.mj_loadAllPluginLibraries(str(plugin_dir))


def load_cell_model():
    """Return (MjModel, MjData) for the full cell including the flex shirt."""
    if not CELL_XML.is_file():
        raise FileNotFoundError(CELL_XML)
    return load_mjcf(CELL_XML, claws=False)


def shirt_vertex_positions(model, data) -> np.ndarray:
    """World-frame flex vertex positions, shape (nvert, 3)."""
    if model.nflexvert == 0:
        raise RuntimeError("Model has no flex vertices; is shirt.xml included?")
    return np.asarray(data.flexvert_xpos, dtype=np.float64).reshape(-1, 3)


def flatness(model, data) -> float:
    """std(z) of shirt flex vertices — lower means flatter."""
    z = shirt_vertex_positions(model, data)[:, 2]
    return float(np.std(z))


def shirt_aabb(model, data) -> tuple[np.ndarray, np.ndarray]:
    """Return (mins, maxs) of shirt vertices."""
    pos = shirt_vertex_positions(model, data)
    return pos.min(axis=0), pos.max(axis=0)


def set_steam(model, on: bool) -> None:
    """Press 'steam': extra edge damping, not thermodynamics."""
    if model.nflexedge == 0:
        return
    model.flex_edgedamping[:] = STEAM_EDGE_DAMPING if on else DRY_EDGE_DAMPING


def aabb_overlaps_press(model, data, margin: float = 0.05) -> bool:
    """True if the shirt AABB overlaps the press bed (expanded by margin)."""
    mins, maxs = shirt_aabb(model, data)
    bed_min = PRESS_BED_POS - PRESS_BED_HALF - margin
    bed_max = PRESS_BED_POS + PRESS_BED_HALF + margin
    return bool(np.all(maxs >= bed_min) and np.all(mins <= bed_max))


# --- rest-mesh geometry (controller frame: +X collar, +Y left sleeve) -----

_MESH_CACHE: tuple[np.ndarray, np.ndarray] | None = None


def load_shirt_mesh() -> tuple[np.ndarray, np.ndarray]:
    """Rest vertices and triangles of ``shirt_t.obj``, in the raw OBJ frame."""
    global _MESH_CACHE
    if _MESH_CACHE is not None:
        return _MESH_CACHE
    path = MODELS_DIR / shirt_config().mesh
    verts: list[list[float]] = []
    faces: list[tuple[int, int, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            parts = line.split()
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            ids = [int(tok.split("/")[0]) - 1 for tok in line.split()[1:]]
            if len(ids) >= 3:
                faces.append((ids[0], ids[1], ids[2]))
    _MESH_CACHE = (
        np.asarray(verts, dtype=np.float64),
        np.asarray(faces, dtype=np.int32),
    )
    return _MESH_CACHE


def mesh_to_shirt(points: np.ndarray) -> np.ndarray:
    """Map OBJ XY (sleeves, collar) onto the controller frame (collar, left)."""
    out = np.empty_like(points)
    out[:, 0] = points[:, 1]
    out[:, 1] = points[:, 0]
    out[:, 2] = points[:, 2]
    return out


def shirt_rest_local() -> np.ndarray:
    """Rest vertices in the controller frame, shape (nvert, 3)."""
    return mesh_to_shirt(load_shirt_mesh()[0])


def shirt_collar_ids() -> np.ndarray:
    """Vertex indices around the crew-neck opening."""
    mesh, _ = load_shirt_mesh()
    # shirt_t.obj: collar at +Y in the OBJ frame.
    y_cut = float(mesh[:, 1].max()) - 0.10
    return np.flatnonzero((mesh[:, 1] > y_cut) & (np.abs(mesh[:, 0]) < 0.16))


def shirt_band_local() -> np.ndarray:
    """Neck opening centre in the controller frame."""
    local = shirt_rest_local()
    ids = shirt_collar_ids()
    return local[ids].mean(axis=0) if len(ids) else np.array([0.24, 0.0, 0.0])


def shirt_torso_half() -> np.ndarray:
    """Torso panel half-extents in the controller frame (no sleeves)."""
    local = shirt_rest_local()
    torso = local[np.abs(local[:, 1]) < 0.30]
    center = torso.mean(axis=0)
    span = np.maximum(torso.max(axis=0) - center, center - torso.min(axis=0))
    return span[:2]


def shirt_footprint_polygons() -> list[np.ndarray]:
    """Rest-mesh triangles in the controller xy frame, for the vision fit."""
    mesh, faces = load_shirt_mesh()
    local = mesh_to_shirt(mesh)[:, :2]
    return [local[face] for face in faces]


def shirt_vertex_qposadr(model) -> np.ndarray:
    """qpos address of the first slide joint of each flex vertex."""
    bodies = np.asarray(model.flex_vertbodyid)
    addresses = np.empty(len(bodies), dtype=int)
    for index, body in enumerate(bodies):
        joints = np.flatnonzero(model.jnt_bodyid == body)
        addresses[index] = int(model.jnt_qposadr[joints[0]])
    return addresses


def shirt_rest_world(model, data) -> np.ndarray:
    """World positions of the undeformed flex (all vertex qpos at zero)."""
    return shirt_vertex_positions(model, data).copy()


def set_shirt_world(data, world: np.ndarray, rest_world: np.ndarray, qposadr) -> None:
    """Teleport every flex vertex by writing slide-joint offsets."""
    offset = np.asarray(world, dtype=np.float64) - rest_world
    for index, address in enumerate(qposadr):
        data.qpos[address : address + 3] = offset[index]


# The 2F-85 pads bat a thin sheet away before a contact grasp seats. The
# loading cell uses this hold so a pinched corner follows the hand.
PINCH_RADIUS = 0.07
# Stiff enough that dragging the whole shirt over the crate lip (~7 N) lags
# the jaws by ~1 cm, not ~10 cm. The force is explicit, so omega * dt must
# stay well under 1: 30 Hz at 2 ms is 0.38.
PINCH_SPRING_HZ = 30.0
# Per held vertex, in multiples of its weight. A patch of ~9 vertices then
# holds ~30 N, about what a 2F-85 pinch holds on cotton: enough to draw the
# shirt out over the crate lip and drag it across the plate.
PINCH_FORCE_LIMIT = 250.0
# An anchored grab only takes if that vertex really sits between the jaws,
# and holds the patch of fabric within ANCHOR_PATCH of it on the rest mesh
# (one grid step and the diagonals).
ANCHOR_REACH = 0.04
ANCHOR_PATCH = 0.08


class PinchHold:
    """Spring a patch of flex vertices onto the hand's pinch point."""

    def __init__(
        self,
        model,
        data,
        *,
        hz: float = PINCH_SPRING_HZ,
        force_limit: float = PINCH_FORCE_LIMIT,
    ) -> None:
        self._model = model
        self._data = data
        self._hz = float(hz)
        self._force_limit = float(force_limit)
        self._vert_body = np.asarray(model.flex_vertbodyid, dtype=np.int64)
        self._bodies: np.ndarray | None = None
        self._offsets: np.ndarray | None = None

    @property
    def active(self) -> bool:
        return self._bodies is not None

    def grab(self, target: np.ndarray, anchor: int | None = None) -> int:
        """Hold the cloth under the jaws.

        With ``anchor`` the jaws close on one corner of the fabric: only the
        patch around that vertex on the rest mesh is held, so a layer lying
        a centimetre underneath stays behind. Returns how many vertices are
        held; 0 means the anchor was out of the jaws and nothing is held.
        """
        pos = shirt_vertex_positions(self._model, self._data)
        target = np.asarray(target, dtype=np.float64)
        dist = np.linalg.norm(pos - target, axis=1)
        if anchor is not None:
            if dist[anchor] > ANCHOR_REACH:
                return 0
            rest = shirt_rest_local()
            patch = np.linalg.norm(rest - rest[anchor], axis=1) <= ANCHOR_PATCH
            near = np.flatnonzero(patch & (dist <= 2.0 * ANCHOR_PATCH))
        else:
            near = np.flatnonzero(dist <= PINCH_RADIUS)
        if near.size == 0:
            near = np.array([int(np.argmin(dist))])
        self._bodies = self._vert_body[near]
        self._offsets = pos[near] - pos[near].mean(axis=0)
        return int(near.size)

    def release(self) -> None:
        if self._bodies is not None:
            self._data.xfrc_applied[self._bodies, :3] = 0.0
        self._bodies = None
        self._offsets = None

    def pull(self, target: np.ndarray) -> None:
        if self._bodies is None or self._offsets is None:
            return
        import mujoco

        target = np.asarray(target, dtype=np.float64)
        omega = 2.0 * np.pi * self._hz
        vel = np.empty(6)
        for body, offset in zip(self._bodies, self._offsets):
            mass = float(self._model.body_mass[body])
            pos = np.asarray(self._data.xpos[body])
            mujoco.mj_objectVelocity(
                self._model, self._data, mujoco.mjtObj.mjOBJ_BODY, int(body), vel, 0
            )
            error = (target + offset) - pos
            force = mass * (omega**2) * error - 2.0 * mass * omega * vel[3:6]
            limit = self._force_limit * mass * 9.81
            magnitude = np.linalg.norm(force)
            if magnitude > limit:
                force *= limit / magnitude
            self._data.xfrc_applied[body, :3] = force


def shirt_rigid_pose(live: np.ndarray, rest_local: np.ndarray) -> tuple[np.ndarray, float]:
    """Best rigid (centre, yaw) taking the rest mesh onto the live vertices."""
    rest_xy = rest_local[:, :2] - rest_local[:, :2].mean(axis=0)
    live_xy = live[:, :2] - live[:, :2].mean(axis=0)
    u, _, vt = np.linalg.svd(rest_xy.T @ live_xy)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt = vt.copy()
        vt[-1] *= -1.0
        rotation = vt.T @ u.T
    yaw = float(np.arctan2(rotation[1, 0], rotation[0, 0]))
    return live.mean(axis=0).copy(), yaw
