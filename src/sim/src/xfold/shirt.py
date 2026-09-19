"""Shirt flexcomp parameters and geometry helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Matches models/shirt.xml / shirt_cloth3d.obj — keep in sync when retuning.
# Params adapted from mujoco/model/flex/poncho_edgeequality.xml.
SHIRT_MESH = "shirt_cloth3d.obj"
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
PRESS_BED_POS = np.array([0.15, 0.0, 0.08], dtype=np.float64)
PRESS_BED_HALF = np.array([0.35, 0.35, 0.015], dtype=np.float64)


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


def aabb_overlaps_press(model, data, margin: float = 0.05) -> bool:
    """True if the shirt AABB overlaps the press bed (expanded by margin)."""
    mins, maxs = shirt_aabb(model, data)
    bed_min = PRESS_BED_POS - PRESS_BED_HALF - margin
    bed_max = PRESS_BED_POS + PRESS_BED_HALF + margin
    return bool(np.all(maxs >= bed_min) and np.all(mins <= bed_max))
