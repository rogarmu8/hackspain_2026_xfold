"""Shirt flexcomp parameters and geometry helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Matches models/shirt.xml / shirt_t.obj — keep in sync when retuning.
# Params adapted from mujoco/model/flex/poncho_edgeequality.xml.
SHIRT_MESH = "shirt_t.obj"
SHIRT_MASS = 0.22
# Half-thickness of the rendered slab as well as the collision margin. 8 mm
# looked like a yoga mat; 4 mm is the thinnest that still never clips.
SHIRT_RADIUS = 0.004
# Above ~0.5 the edge equalities inject energy and the shirt launches upward.
SHIRT_EDGE_DAMPING = 0.5
SHIRT_SOLREF = "0.005 1.2"
SHIRT_SOLIMP = "0.99 0.999 0.0002"
# MuJoCo caps one flex-vs-geom pair at mjMAXCONPAIR contacts. A physics mesh
# that lays down more vertices than this is under-supported: it clips through
# the floor and ripples forever. Keep resting contacts at or under the cap.
SHIRT_CONTACT_BUDGET = 50
SHIRT_SPAWN_POS = (0.15, 0.0, 0.55)

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
PLAYGROUND_XML = MODELS_DIR / "shirt_playground.xml"
PLAYGROUND_HI_XML = MODELS_DIR / "shirt_playground_hi.xml"
PLAYGROUND_PONCHO_XML = MODELS_DIR / "shirt_playground_poncho.xml"
SHIRT_XML = MODELS_DIR / "shirt.xml"
CELL_XML = MODELS_DIR / "cell.xml"

# Press bed centre / half-extents from cell.xml (for smoke AABB checks).
# Bed is the size of the T plus sleeves (SOLUTION.md §5.2).
PRESS_BED_POS = np.array([0.15, 0.0, 0.08], dtype=np.float64)
PRESS_BED_HALF = np.array([0.48, 0.40, 0.015], dtype=np.float64)

# Steam: raise edge damping so wrinkles relax under the platen (§5.2).
STEAM_EDGE_DAMPING = 10.0
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
    import mujoco

    load_mujoco_plugins()
    if not CELL_XML.is_file():
        raise FileNotFoundError(CELL_XML)
    model = mujoco.MjModel.from_xml_path(CELL_XML.as_posix())
    data = mujoco.MjData(model)
    return model, data


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
    path = MODELS_DIR / SHIRT_MESH
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
    # shirt_t.obj: collar at y ≈ +0.32, neck bite 0.18 × 0.08.
    return np.flatnonzero((mesh[:, 1] > 0.22) & (np.abs(mesh[:, 0]) < 0.14))


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


# The 2F-85 pads bat a 4 mm sheet away before a contact grasp seats. The
# playground already hauls this mesh with a damped spring; the loading cell
# uses the same hold so a pinched neck follows the hand.
PINCH_RADIUS = 0.07
PINCH_SPRING_HZ = 12.0
PINCH_FORCE_LIMIT = 80.0


class PinchHold:
    """Spring a patch of flex vertices onto the hand's pinch point."""

    def __init__(self, model, data) -> None:
        self._model = model
        self._data = data
        self._vert_body = np.asarray(model.flex_vertbodyid, dtype=np.int64)
        self._bodies: np.ndarray | None = None
        self._offsets: np.ndarray | None = None

    @property
    def active(self) -> bool:
        return self._bodies is not None

    def grab(self, target: np.ndarray) -> int:
        pos = shirt_vertex_positions(self._model, self._data)
        target = np.asarray(target, dtype=np.float64)
        dist = np.linalg.norm(pos - target, axis=1)
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
        omega = 2.0 * np.pi * PINCH_SPRING_HZ
        vel = np.empty(6)
        for body, offset in zip(self._bodies, self._offsets):
            mass = float(self._model.body_mass[body])
            pos = np.asarray(self._data.xpos[body])
            mujoco.mj_objectVelocity(
                self._model, self._data, mujoco.mjtObj.mjOBJ_BODY, int(body), vel, 0
            )
            error = (target + offset) - pos
            force = mass * (omega**2) * error - 2.0 * mass * omega * vel[3:6]
            limit = PINCH_FORCE_LIMIT * mass * 9.81
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
