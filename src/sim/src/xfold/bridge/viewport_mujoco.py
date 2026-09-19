"""MuJoCo offscreen producer → ViewportHub (separate image channel).

Uses mujoco.Renderer + fixed camera ``overview`` from cell.xml.
Advances a light physics pose synced to the active run's FSM stage.
Never puts frames in the journal.

Integration contract: docs/INTEGRATION_CONTRACT.md §4b
AGENTS.md → “For agents on other tracks (arm / cloth)”

=============================================================================
AGENT NOTE — CLOTH TRACK + ARM TRACK (3D view)
-----------------------------------------------------------------------------
This module only **renders** whatever MJCF is at MODEL_PATH. It does not own
flexcomp tuning or arm IK.

  Cloth: put a stable flexcomp shirt into that scene (or change MODEL_PATH and
         note it in TRACKING.md). Then delete shirt_proxy / _STAGE_POSE once
         real cloth is driven by physics.
  Arm:   when your robot is in the same MJCF, it will appear in
         GET /viewport/stream automatically — no dashboard change.
  Keep:  <camera name="overview"/> in the loaded model (MJPEG depends on it).
  Never: write JPEG into the journal; never block mj_step on HTTP.
=============================================================================
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from xfold.bridge.viewport import ViewportHub, encode_frame
from xfold.fsm import CellState

if TYPE_CHECKING:
    from xfold.bridge.runtime import Runtime

# AGENT: cloth/arm — change this path if your demo scene lives elsewhere; note TRACKING.md
MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "cell.xml"

# AGENT: cloth — temporary proxy poses for the blue box shirt_proxy.
# Remove once flexcomp / real shirt is the visual source of truth.
_STAGE_POSE: dict[str, tuple[float, float, float]] = {
    CellState.PICK.value: (-0.55, 0.0, 0.28),
    CellState.SPREAD.value: (0.15, 0.0, 0.12),
    CellState.PRESS.value: (0.15, 0.0, 0.10),
    CellState.FOLD.value: (0.15, 0.0, 0.11),
    CellState.CHUTE.value: (0.72, 0.0, 0.22),
    CellState.BAG.value: (1.05, 0.0, 0.12),
    CellState.RESET.value: (-0.55, 0.0, 0.35),
}


class MujocoViewportProducer:
    """Background thread: render cell → JPEG/PNG → hub."""

    def __init__(
        self,
        runtime: Runtime,
        hub: ViewportHub,
        *,
        width: int = 640,
        height: int = 360,
        fps: float = 12.0,
    ) -> None:
        self.runtime = runtime
        self.hub = hub
        self.width = width
        self.height = height
        self.fps = fps
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ok = False

    @property
    def ok(self) -> bool:
        return self._ok

    def start(self) -> bool:
        try:
            import mujoco  # noqa: F401
        except ImportError:
            return False
        if not MODEL_PATH.is_file():
            return False
        if self._thread and self._thread.is_alive():
            return self._ok
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="xfold-viewport-mujoco", daemon=True
        )
        self._thread.start()
        # Wait briefly for first successful init
        for _ in range(50):
            if self._ok or self._stop.is_set():
                break
            time.sleep(0.05)
        return self._ok

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        import mujoco

        try:
            model = mujoco.MjModel.from_xml_path(MODEL_PATH.as_posix())
            # Ensure offscreen buffer fits our resolution.
            model.vis.global_.offwidth = max(model.vis.global_.offwidth, self.width)
            model.vis.global_.offheight = max(model.vis.global_.offheight, self.height)
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            renderer = mujoco.Renderer(model, height=self.height, width=self.width)
            self.hub.set_source("mujoco")
            self._ok = True
        except Exception as exc:  # noqa: BLE001 — surface init failure, keep bridge up
            print(f"[viewport] MuJoCo producer failed to start: {exc}", flush=True)
            self.hub.set_source("none")
            self._ok = False
            return

        interval = 1.0 / max(self.fps, 1.0)
        shirt_jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "shirt_free")
        qadr = int(model.jnt_qposadr[shirt_jid]) if shirt_jid >= 0 else None

        try:
            while not self._stop.is_set():
                t0 = time.monotonic()
                run = self.runtime.driver_active_run()
                state = (run.currentState if run else None) or CellState.PICK.value
                xyz = _STAGE_POSE.get(state, _STAGE_POSE[CellState.PICK.value])
                if qadr is not None:
                    data.qpos[qadr : qadr + 3] = xyz
                    data.qpos[qadr + 3 : qadr + 7] = (1, 0, 0, 0)
                    data.qvel[:] = 0
                mujoco.mj_forward(model, data)
                if run and run.lifecycle == "running" and not run.paused:
                    for _ in range(3):
                        mujoco.mj_step(model, data)
                    if qadr is not None:
                        data.qpos[qadr : qadr + 3] = xyz
                        data.qpos[qadr + 3 : qadr + 7] = (1, 0, 0, 0)
                        mujoco.mj_forward(model, data)

                renderer.update_scene(data, camera="overview")
                rgb = renderer.render()
                payload, mime = encode_frame(np.asarray(rgb))
                self.hub.publish(payload, mime=mime)

                elapsed = time.monotonic() - t0
                time.sleep(max(0.0, interval - elapsed))
        finally:
            try:
                renderer.close()
            except Exception:
                pass
            self._ok = False
            self.hub.set_source("none")
