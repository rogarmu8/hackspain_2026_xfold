"""XPBD-style cloth layer separation on top of MuJoCo flex.

MuJoCo flex self-collision is force-based and one pair is capped at
mjMAXCONPAIR = 50 contacts. A three-layer ninja packet blows that budget
and the layers occupy the same plane.

Unreal Chaos / Velvet / XPBD do not leave this to contact forces. After
the integrator they *project* particles that are closer than a collision
thickness, ignoring pairs that were already neighbours in the rest pose
(Velvet's "collision filtering"). That is what this module ports.

Flex vertex slides store *offsets* from the bind pose (qpos is 0 at rest),
so we read world positions from flexvert_xpos and write the same delta
into qpos.

The hot path is a spatial hash, not an n×n distance matrix. At 1080 verts
the dense version was ~30 ms/step and made the playground unusable.
"""

from __future__ import annotations

import numpy as np

# Unreal "collision thickness" — bigger than the visible 4 mm slab.
THICKNESS = 0.010
# Rest-pose pairs closer than this × edge length are the mesh, not two layers.
REST_EXCLUDE = 1.55
ITERATIONS = 3
FRICTION = 0.25


class ClothLayers:
    """Project folded layers apart after each mj_step."""

    def __init__(self, model, data, thickness: float = THICKNESS):
        self._model = model
        self._data = data
        bodies = np.asarray(model.flex_vertbodyid, dtype=np.int64)
        self._qadr = np.array(
            [int(model.jnt_qposadr[int(model.body_jntadr[b])]) for b in bodies],
            dtype=np.int64,
        )
        self._dadr = np.array(
            [int(model.jnt_dofadr[int(model.body_jntadr[b])]) for b in bodies],
            dtype=np.int64,
        )
        rest = np.asarray(data.flexvert_xpos, dtype=np.float64).reshape(-1, 3).copy()
        edge0 = np.asarray(model.flexedge_length0, dtype=np.float64)
        spacing = float(np.median(edge0)) if edge0.size else 0.052
        exclude = REST_EXCLUDE * spacing
        d2 = np.sum((rest[:, None, :] - rest[None, :, :]) ** 2, axis=2)
        skip = d2 <= exclude**2
        self._skip = np.logical_or(skip, skip.T)
        np.fill_diagonal(self._skip, True)
        self._sep = 2.0 * float(thickness)
        self._floor = float(model.flex_radius[0]) if model.nflex else 0.004
        self._n = rest.shape[0]
        # Allow-mask kept for overlap_count (tests / diagnostics).
        self._allow = np.triu(~self._skip, k=1)

    def overlap_count(self) -> int:
        """How many non-neighbour pairs are closer than the layer gap."""
        pos = self._world_pos()
        pairs = self._near_pairs(pos)
        if pairs.size == 0:
            return 0
        i, j = pairs[:, 0], pairs[:, 1]
        dist = np.linalg.norm(pos[i] - pos[j], axis=1)
        return int(np.count_nonzero(dist < self._sep))

    def separate(self, iterations: int = ITERATIONS) -> int:
        """Project overlapping layers apart. Returns colliding-pair count."""
        pos = self._world_pos()
        n_hit = 0
        vel = None
        wrote = False
        for _ in range(iterations):
            pairs = self._near_pairs(pos)
            if pairs.size == 0:
                break
            ii, jj = pairs[:, 0], pairs[:, 1]
            delta = pos[ii] - pos[jj]
            dist = np.linalg.norm(delta, axis=1)
            keep = (dist < self._sep) & (dist > 1e-8)
            if not np.any(keep):
                n_hit = 0
                break
            ii, jj, dist = ii[keep], jj[keep], dist[keep]
            n_hit = int(ii.size)
            nrm = (pos[ii] - pos[jj]) / dist[:, None]
            push = (0.5 * (self._sep - dist))[:, None] * nrm
            corr = np.zeros_like(pos)
            np.add.at(corr, ii, push)
            np.add.at(corr, jj, -push)
            pos += corr
            if vel is None:
                vel = self._read_vel()
            rel = vel[ii] - vel[jj]
            vn = np.sum(rel * nrm, axis=1, keepdims=True)
            approach = np.minimum(vn, 0.0)
            dv = np.zeros_like(vel)
            np.add.at(dv, ii, -0.5 * approach * nrm)
            np.add.at(dv, jj, 0.5 * approach * nrm)
            vel += dv
            rel = vel[ii] - vel[jj]
            vt = rel - np.sum(rel * nrm, axis=1, keepdims=True) * nrm
            dv.fill(0.0)
            np.add.at(dv, ii, -FRICTION * vt)
            np.add.at(dv, jj, FRICTION * vt)
            vel += dv
            pos[:, 2] = np.maximum(pos[:, 2], self._floor)
            wrote = True
        if wrote:
            self._write_world(pos)
            self._write_vel(vel)
        return n_hit

    def _near_pairs(self, pos: np.ndarray) -> np.ndarray:
        """Candidate pairs from a 3-cell spatial hash, rest-neighbours removed."""
        inv = 1.0 / self._sep
        cell = np.floor(pos * inv).astype(np.int32)
        buckets: dict[tuple[int, int, int], list[int]] = {}
        for i, (x, y, z) in enumerate(cell):
            buckets.setdefault((int(x), int(y), int(z)), []).append(i)
        skip = self._skip
        out_i: list[np.ndarray] = []
        out_j: list[np.ndarray] = []
        for (ix, iy, iz), ids in buckets.items():
            neigh: list[int] = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        extra = buckets.get((ix + dx, iy + dy, iz + dz))
                        if extra:
                            neigh.extend(extra)
            if len(neigh) < 2:
                continue
            neigh_a = np.fromiter(neigh, dtype=np.int64, count=len(neigh))
            for i in ids:
                js = neigh_a[neigh_a > i]
                if js.size == 0:
                    continue
                js = js[~skip[i, js]]
                if js.size:
                    out_i.append(np.full(js.size, i, dtype=np.int64))
                    out_j.append(js)
        if not out_i:
            return np.empty((0, 2), dtype=np.int64)
        return np.column_stack((np.concatenate(out_i), np.concatenate(out_j)))

    def _world_pos(self) -> np.ndarray:
        return np.asarray(self._data.flexvert_xpos, dtype=np.float64).reshape(-1, 3).copy()

    def _write_world(self, new_pos: np.ndarray) -> None:
        old = np.asarray(self._data.flexvert_xpos, dtype=np.float64).reshape(-1, 3)
        delta = new_pos - old
        self._data.qpos[self._qadr[:, None] + np.arange(3)] += delta

    def _read_vel(self) -> np.ndarray:
        qvel = self._data.qvel
        return np.ascontiguousarray(
            qvel[self._dadr[:, None] + np.arange(3)], dtype=np.float64
        )

    def _write_vel(self, vel: np.ndarray) -> None:
        self._data.qvel[self._dadr[:, None] + np.arange(3)] = vel
