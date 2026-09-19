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

if TYPE_CHECKING:
    from xfold.bridge.runtime import Runtime

# Fallback stub if the loading cell fails to compile. Prefer press_cell via scene.build.
MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "cell.xml"


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
        # scene.build() compiles Menagerie + cloth; give it a few seconds.
        for _ in range(200):
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

        camera = "overview"
        try:
            from xfold.shirt import load_mujoco_plugins

            load_mujoco_plugins()
            model, data, camera = self._compile_scene(mujoco)
            model.vis.global_.offwidth = max(model.vis.global_.offwidth, self.width)
            model.vis.global_.offheight = max(model.vis.global_.offheight, self.height)
            renderer = mujoco.Renderer(model, height=self.height, width=self.width)
            self.hub.set_source("mujoco")
            self._ok = True
        except Exception as exc:  # noqa: BLE001 — surface init failure, keep bridge up
            print(f"[viewport] MuJoCo producer failed to start: {exc}", flush=True)
            self.hub.set_source("none")
            self._ok = False
            return

        interval = 1.0 / max(self.fps, 1.0)
        try:
            while not self._stop.is_set():
                t0 = time.monotonic()
                run = self.runtime.driver_active_run()
                if run and run.lifecycle == "running" and not run.paused:
                    for _ in range(3):
                        mujoco.mj_step(model, data)
                else:
                    mujoco.mj_forward(model, data)

                renderer.update_scene(data, camera=camera)
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

    def _compile_scene(self, mujoco):
        """Prefer the loading cell (flex T + press); fall back to cell.xml."""
        try:
            from xfold.scene import build, spawn_shirt_in_bin

            cell = build()
            data = mujoco.MjData(cell.model)
            spawn_shirt_in_bin(cell, data, np.random.default_rng(7))
            mujoco.mj_forward(cell.model, data)
            camera = "overview"
            try:
                cell.model.camera(camera)
            except KeyError:
                camera = "cell_cam"
            print("[viewport] rendering press_cell (flex shirt + UR5e)", flush=True)
            return cell.model, data, camera
        except Exception as exc:
            print(f"[viewport] press_cell compile failed ({exc}); using cell.xml", flush=True)
            model = mujoco.MjModel.from_xml_path(MODEL_PATH.as_posix())
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            return model, data, "overview"
