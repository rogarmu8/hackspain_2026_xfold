"""MuJoCo offscreen producer → H.264 video + ViewportHub (render-only).

Owns no independent MjData. Physics is advanced by PressBridgeDriver (or
MockDriver when MuJoCo is unavailable) on the shared SimSession.

Integration contract: docs/INTEGRATION_CONTRACT.md §4b
AGENTS.md → “For agents on other tracks (arm / cloth)”

=============================================================================
AGENT NOTE — CLOTH TRACK + ARM TRACK (3D view)
-----------------------------------------------------------------------------
This module only **renders** the shared SimSession. It does not own
flexcomp tuning, arm IK, or PressCycle.

  Cloth / arm: drive the same SimSession from your Driver; frames appear in
               the run's video and on GET /viewport/frame automatically — no
               dashboard change.
  Keep:  <camera name="overview"/> in the loaded model (MJPEG depends on it).
  Never: write JPEG into the journal; never block mj_step on HTTP.
  Replay: use GET /runs/{id}/recording/frame?t= (not this live stream).
=============================================================================
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from xfold.bridge.viewport import ViewportHub, encode_frame

if TYPE_CHECKING:
    from xfold.bridge.sim_session import SimSession
    from xfold.bridge.video import VideoManager


class MujocoViewportProducer:
    """Background thread: SimSession.render_jpeg → hub. No mj_step here."""

    def __init__(
        self,
        session: SimSession,
        hub: ViewportHub,
        *,
        fps: float = 12.0,
        video: VideoManager | None = None,
        active_run=None,
    ) -> None:
        self.session = session
        self.hub = hub
        self.fps = fps
        # One render feeds both: H.264 for the dashboard, JPEG for the
        # long-poll fallback and for anything watching before the first
        # segment lands.
        self.video = video
        self.active_run = active_run
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ok = False

    @property
    def ok(self) -> bool:
        return self._ok

    def start(self) -> bool:
        if not self.session.ok:
            return False
        if self._thread and self._thread.is_alive():
            return self._ok
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="xfold-viewport-mujoco", daemon=True
        )
        self._thread.start()
        self.hub.set_source("mujoco")
        self.hub.set_frame_size(self.session.width, self.session.height)
        self._ok = True
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._ok = False
        self.hub.set_source("none")

    def _loop(self) -> None:
        interval = 1.0 / max(self.fps, 1.0)
        try:
            while not self._stop.is_set():
                t0 = time.monotonic()
                try:
                    rgb = self.session.render_rgb()
                except Exception as exc:  # noqa: BLE001
                    print(f"[viewport] render error: {exc}", flush=True)
                    rgb = None
                if self.video is not None:
                    run_id = self.active_run() if self.active_run else None
                    if getattr(self.session, "records_video", False):
                        # The session writes its own frames; only close runs.
                        self.video.sync(run_id)
                    elif rgb is not None:
                        self.video.frame(run_id, rgb)
                if rgb is not None:
                    payload, mime = encode_frame(rgb)
                    self.hub.publish(payload, mime=mime)
                elapsed = time.monotonic() - t0
                time.sleep(max(0.0, interval - elapsed))
        finally:
            self._ok = False
            self.hub.set_source("none")
