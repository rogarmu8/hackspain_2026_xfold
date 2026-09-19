"""Real-time stepping helper shared by every MuJoCo demo in this package."""

from __future__ import annotations

import time


def smoothstep(progress: float) -> float:
    """Ease-in/ease-out so actuators never start or stop with a jerk."""
    clamped = min(max(progress, 0.0), 1.0)
    return clamped * clamped * (3.0 - 2.0 * clamped)


class Loop:
    """Steps the model, keeps wall-clock pace, and syncs a passive viewer.

    Every motion helper returns False once the viewer window is closed, so
    call sites can unwind a cycle without exceptions.
    """

    def __init__(self, model, data, viewer=None, realtime: bool = True) -> None:
        import mujoco

        self._mujoco = mujoco
        self.model = model
        self.data = data
        self.viewer = viewer
        self.realtime = realtime

    @property
    def running(self) -> bool:
        return self.viewer is None or self.viewer.is_running()

    def step(self, count: int = 1) -> bool:
        for _ in range(count):
            started = time.perf_counter()
            self._mujoco.mj_step(self.model, self.data)
            if self.viewer is not None:
                self.viewer.sync()
                if not self.viewer.is_running():
                    return False
            if self.realtime:
                leftover = self.model.opt.timestep - (time.perf_counter() - started)
                if leftover > 0:
                    time.sleep(leftover)
        return self.running

    def hold(self, seconds: float) -> bool:
        return self.step(self.steps_for(seconds))

    def ramp_ctrl(self, actuator: int, target: float, seconds: float) -> bool:
        """Drive one actuator from its current command to target."""
        start = float(self.data.ctrl[actuator])
        steps = self.steps_for(seconds)
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            self.data.ctrl[actuator] = start + (target - start) * blend
            if not self.step():
                return False
        return self.running

    def steps_for(self, seconds: float) -> int:
        return max(1, int(round(seconds / self.model.opt.timestep)))
