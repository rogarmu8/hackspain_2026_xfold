"""The Backend protocol on a second MjData: MuJoCo standing in for PhysX.

Nothing about the Isaac port is testable without a GPU except the part that
matters most, the bookkeeping in EngineShim: what goes to the engine, what
comes back, when. This backend steps the same model in a shadow MjData, so
a Line run through EngineShim + MujocoBackend has to reproduce the native
Line. scripts/test-isaac-port.py checks that it does.
"""

from __future__ import annotations

import mujoco
import numpy as np


class MujocoBackend:
    def __init__(self, line) -> None:
        self.model = line.model
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)
        self._qadr = line._qadr
        self._dadr = line._dadr
        self._rest = line._rest
        self._xyz = np.arange(3)
        self._bag_q = slice(line._bag_qadr, line._bag_qadr + 7)
        self._bag_v = slice(line._bag_dadr, line._bag_dadr + 6)
        # Actuated joints: EngineShim integrates them, the shadow just follows.
        joints = self.model.actuator_trnid[:, 0]
        self._joints = [
            (int(self.model.jnt_qposadr[j]), int(self.model.jnt_dofadr[j])) for j in joints
        ]
        self.frames = 0

    def write_kinematics(self, model, data) -> None:
        shadow = self.data
        shadow.mocap_pos[:] = data.mocap_pos
        shadow.mocap_quat[:] = data.mocap_quat
        for qadr, dadr in self._joints:
            shadow.qpos[qadr] = data.qpos[qadr]
            shadow.qvel[dadr] = data.qvel[dadr]
        shadow.ctrl[:] = data.ctrl

    def write_cloth(self, pos: np.ndarray, vel: np.ndarray) -> None:
        self.data.qpos[self._qadr[:, None] + self._xyz] = pos - self._rest
        self.data.qvel[self._dadr[:, None] + self._xyz] = vel

    def read_cloth(self) -> tuple[np.ndarray, np.ndarray]:
        pos = self._rest + self.data.qpos[self._qadr[:, None] + self._xyz]
        return pos, self.data.qvel[self._dadr[:, None] + self._xyz].copy()

    def write_bag(self, qpos: np.ndarray, qvel: np.ndarray) -> None:
        self.data.qpos[self._bag_q] = qpos
        self.data.qvel[self._bag_v] = qvel

    def read_bag(self) -> tuple[np.ndarray, np.ndarray]:
        return self.data.qpos[self._bag_q].copy(), self.data.qvel[self._bag_v].copy()

    def set_collisions(self, geoms: np.ndarray, enabled: np.ndarray) -> None:
        pass  # the shadow shares the controller's model, flags included

    def sync_visuals(self, model, data, geoms: np.ndarray, lights: bool, cloth: np.ndarray) -> None:
        pass  # nothing to draw

    def step(self, render: bool) -> None:
        mujoco.mj_step(self.model, self.data)
        self.frames += int(render)
