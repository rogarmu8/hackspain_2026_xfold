"""Mocap claws that kinematically pin flex vertices.

Force springs stretch an inextensible sheet; equality connect is too
soft against hundreds of edge constraints and floor contacts. The
reliable pin is the same qpos-offset write ClothLayers uses: snap the
vertex body to a world point each step. Mocap geoms are the visible
hands.
"""

from __future__ import annotations

import numpy as np

CLAW_BODIES = ("claw_0", "claw_1")
CLAW_EQS = ("claw_0_pin", "claw_1_pin")
CLAW_GEOMS = ("claw_0_geom", "claw_1_geom")
CLAW_RGBA = np.array([0.95, 0.35, 0.12, 0.95], dtype=np.float64)
PARK = np.array([0.0, 0.0, -0.25], dtype=np.float64)


def add_claw_bodies(spec) -> None:
    """Two mocap claws + inactive connect eqs (visual + reserved pins)."""
    import mujoco

    names = {str(getattr(b, "name", "") or "") for b in spec.bodies}
    if CLAW_BODIES[0] in names:
        return
    shirt = next(
        (str(b.name) for b in spec.bodies if str(getattr(b, "name", "")).startswith("shirt_")),
        "",
    )
    if not shirt:
        return
    world = spec.worldbody
    for i, name in enumerate(CLAW_BODIES):
        body = world.add_body()
        body.name = name
        body.mocap = True
        body.pos = PARK.copy()
        geom = body.add_geom()
        geom.name = CLAW_GEOMS[i]
        geom.type = mujoco.mjtGeom.mjGEOM_SPHERE
        geom.size = np.array([0.018, 0.0, 0.0], dtype=np.float64)
        geom.contype = 0
        geom.conaffinity = 0
        geom.group = 0
        geom.rgba = np.array([0.95, 0.35, 0.12, 0.0], dtype=np.float64)
        eq = spec.add_equality()
        eq.type = mujoco.mjtEq.mjEQ_CONNECT
        eq.name = CLAW_EQS[i]
        eq.name1 = name
        eq.name2 = shirt
        eq.active = False
        eq.objtype = mujoco.mjtObj.mjOBJ_BODY
        eq.data = np.zeros(11, dtype=np.float64)


def pin_bodies(model, data, body_ids, world_pos, vel=None) -> None:
    """Move flex vertex bodies to world_pos via qpos offsets from bind pose."""
    bodies = np.atleast_1d(np.asarray(body_ids, dtype=np.int64))
    if bodies.size == 0:
        return
    dest = np.asarray(world_pos, dtype=np.float64).reshape(-1, 3)
    jnt = np.asarray(model.body_jntadr[bodies], dtype=np.int64)
    adr = np.asarray(model.jnt_qposadr[jnt], dtype=np.int64)
    data.qpos[adr[:, None] + np.arange(3)] += dest - np.asarray(data.xpos[bodies])
    dof = np.asarray(model.jnt_dofadr[jnt], dtype=np.int64)
    if vel is None:
        data.qvel[dof[:, None] + np.arange(3)] = 0.0
    else:
        data.qvel[dof[:, None] + np.arange(3)] = np.asarray(vel, dtype=np.float64).reshape(-1, 3)


class ShirtClaws:
    """Two visible mocap hands that kinematically pinch flex vertices."""

    def __init__(self, model, data):
        import mujoco

        self._model = model
        self._data = data
        self._body: list[int] = []
        self._mocap: list[int] = []
        self._geom: list[int] = []
        self._attached = [-1, -1]
        for i, name in enumerate(CLAW_BODIES):
            bid = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name))
            if bid < 0:
                raise RuntimeError(
                    "shirt claws missing — apply_shirt_config did not add mocap claws"
                )
            mid = int(model.body_mocapid[bid])
            if mid < 0:
                raise RuntimeError(f"{name} is not a mocap body")
            gid = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, CLAW_GEOMS[i]))
            self._body.append(bid)
            self._mocap.append(mid)
            self._geom.append(gid)
        self.release()

    def attach(
        self,
        slot: int,
        vertex_body: int,
        pos: np.ndarray,
        vel: np.ndarray | None = None,
    ) -> None:
        """Show a claw and pin that flex body to pos."""
        self._attached[slot] = int(vertex_body)
        self.move(slot, pos, vel)
        gid = self._geom[slot]
        if gid >= 0:
            self._model.geom_rgba[gid] = CLAW_RGBA

    def attach_pair(
        self,
        vertex_bodies: list[int],
        positions: list[np.ndarray],
        vels: list[np.ndarray] | None = None,
    ) -> None:
        for slot, body in enumerate(vertex_bodies):
            vel = None if vels is None else vels[slot]
            self.attach(slot, body, positions[slot], vel)
        for slot in range(len(vertex_bodies), 2):
            self.release(slot)

    def move(
        self, slot: int, pos: np.ndarray, vel: np.ndarray | None = None
    ) -> None:
        dest = np.asarray(pos, dtype=np.float64)
        self._data.mocap_pos[self._mocap[slot]] = dest
        body = self._attached[slot]
        if body >= 0:
            v = None if vel is None else [vel]
            pin_bodies(self._model, self._data, [body], dest, v)

    def release(self, slot: int | None = None) -> None:
        slots = range(2) if slot is None else (slot,)
        for s in slots:
            self._attached[s] = -1
            self._data.mocap_pos[self._mocap[s]] = PARK
            gid = self._geom[s]
            if gid >= 0:
                self._model.geom_rgba[gid, 3] = 0.0

    def hide(self) -> None:
        self.release()

    @property
    def positions(self) -> list[np.ndarray]:
        return [
            np.asarray(self._data.mocap_pos[m], dtype=np.float64).copy()
            for m, attached in zip(self._mocap, self._attached)
            if attached >= 0
        ]
