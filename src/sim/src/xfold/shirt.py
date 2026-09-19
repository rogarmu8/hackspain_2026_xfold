"""Shirt flexcomp parameters, config, and geometry helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from xfold.claws import add_claw_bodies

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
DEFAULT_CONFIG = MODELS_DIR / "shirt.toml"
PLAYGROUND_XML = MODELS_DIR / "shirt_playground.xml"
PLAYGROUND_HI_XML = MODELS_DIR / "shirt_playground_hi.xml"
PLAYGROUND_PONCHO_XML = MODELS_DIR / "shirt_playground_poncho.xml"
SHIRT_XML = MODELS_DIR / "shirt.xml"
CELL_XML = MODELS_DIR / "cell.xml"

# Matches models/shirt.toml — isotropic StVK surrogate, not cotton constants.
SHIRT_MESH = "shirt_t.obj"
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
        path=src,
    )


_CFG = load_shirt_config()
SHIRT_MASS = _CFG.mass
SHIRT_YOUNG = _CFG.young
SHIRT_POISSON = _CFG.poisson
SHIRT_THICKNESS = _CFG.thickness
SHIRT_RADIUS = _CFG.radius


def shirt_config() -> ShirtConfig:
    return _CFG


def apply_shirt_config(spec, cfg: ShirtConfig | None = None):
    """Write config onto an MjSpec before compile()."""
    import mujoco

    cfg = cfg or shirt_config()
    spec.option.timestep = cfg.timestep
    spec.option.iterations = cfg.iterations
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
    add_claw_bodies(spec)
    nvert = max(len(bodies), 1)
    spec.nconmax = max(int(spec.nconmax or 0), nvert + 512)


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
    eq.type = mujoco.mjtEq.mjEQ_FLEX
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


def load_mjcf(xml_path: Path, cfg: ShirtConfig | None = None):
    """Compile an MJCF scene with shirt.toml applied."""
    import mujoco

    load_mujoco_plugins()
    cfg = cfg or shirt_config()
    spec = mujoco.MjSpec.from_file(xml_path.as_posix())
    apply_shirt_config(spec, cfg)
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
    return load_mjcf(CELL_XML)


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
