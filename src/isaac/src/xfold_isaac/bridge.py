"""The dashboard's bridge with Isaac Sim stepping the line.

    python -m xfold_isaac.bridge            # on the GPU box, in the isaac-sim env
    moon run xfold:dev-isaac                # from a laptop: this + tunnel + dashboard

Same FastAPI app, journal, REST/SSE and HLS video as ``python -m xfold.bridge``
(xfold.bridge.app.create_app), with one difference in who owns which thread.
Kit (physics, rendering, USD) only works on the thread that started it, so:

  * main thread   SimulationApp, then LineDriver.run_here(): every line.step,
                  every PhysX step, every render, the QC photo;
  * uvicorn       a background thread serving HTTP;
  * viewport      the bridge's usual producer thread, which only copies the
                  last frame the main thread rendered into the JPEG hub and
                  the run's video.

Two resolutions from one render. Every rendered frame is 1920x1080: it goes
straight into the run's recording (24 fps of sim time, so replay, which seeks
the video to sim time, lines up), and a 960x540 copy is the live view. The
live view is JPEG frames, not the recording: at ~0.2x realtime a 2 s HLS
segment takes ~10 s to fill, and watching the video live meant a black
viewport for the first half minute (/capabilities.liveVideo = false).
"""

from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path
from typing import Any


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="XFOLD bridge on Isaac Sim")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (127.0.0.1: reach it over SSH)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--size", default="960x540", help="live view frame size, WxH")
    parser.add_argument("--video-size", default="1920x1080", help="recorded video frame size, WxH")
    parser.add_argument("--video-fps", type=float, default=12.0, help="recorded frames per simulated second")
    parser.add_argument("--timestep", type=float, default=None,
                        help="physics timestep (default 0.0055, ~1x realtime; 0.002 matches the MuJoCo line)")
    parser.add_argument("--gui", action="store_true", help="open Isaac Sim's window (needs a display)")
    return parser.parse_args()


def main() -> None:
    args = _args()
    width, height = (int(v) for v in args.size.lower().split("x"))
    video_size = tuple(int(v) for v in args.video_size.lower().split("x"))

    from isaacsim import SimulationApp

    from .run import kit_args

    kit = SimulationApp(
        {
            "headless": not args.gui,
            "width": video_size[0],
            "height": video_size[1],
            # See run.py: the picture is plain USD, drawn without Fabric.
            "extra_args": ["--/app/useFabricSceneDelegate=0", *kit_args()],
        }
    )

    import uvicorn
    from xfold.bridge.app import create_app

    session = IsaacSession(
        kit,
        width=width,
        height=height,
        video_size=video_size,
        video_fps=args.video_fps,
        timestep=args.timestep,
    )
    if not session.start():
        raise SystemExit("Isaac session failed to start")
    app = create_app(session=session, start_driver=False)
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="info"))
    threading.Thread(target=server.run, name="xfold-bridge-http", daemon=True).start()
    # The driver is made in the app's startup hook, on the server's thread.
    deadline = time.monotonic() + 60.0
    while not (server.started and getattr(app.state, "driver", None)):
        if time.monotonic() > deadline:
            raise SystemExit("bridge did not start (port in use?)")
        time.sleep(0.1)
    print(f"[bridge] Isaac Sim bridge on http://{args.host}:{args.port}", flush=True)
    try:
        app.state.driver.run_here()
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        kit.close()


# SimSession is imported lazily so `import xfold_isaac.bridge` stays cheap.
def _session_base():
    from xfold.bridge.sim_session import SimSession

    return SimSession


class IsaacSession(_session_base()):
    """A SimSession whose physics and pictures come from Isaac Sim.

    The MjModel/MjData are still here, built from line.xml exactly as the
    MuJoCo session builds them: they are Line's state and the stage's source.
    Everything that touches Kit runs on the main thread, where LineDriver
    runs; the viewport producer's thread only reads ``_frame``.
    """

    engine = "isaac"
    seekable = False  # replay plays the run's video instead
    live_video = False  # live is JPEG frames; the recording is for replay
    records_video = True

    def __init__(
        self,
        kit,
        *,
        width: int,
        height: int,
        video_size: tuple[int, int],
        video_fps: float,
        timestep: float | None = None,
    ) -> None:
        super().__init__(width=width, height=height)
        self.kit = kit
        self.timestep = timestep
        self.video_size = video_size
        self.video_fps = float(video_fps)
        self._video: Any = None
        self._live_run: Any = None
        self.backend: Any = None
        self.shim: Any = None
        self._frame: Any = None
        self._frame_lock = threading.Lock()
        self._texture_dir = Path("data/isaac/textures").resolve()

    # sim time is the video's clock (see module doc)
    @property
    def video_clock(self):  # type: ignore[override]
        return self.sim_time

    def attach_video(self, video, active_run) -> None:
        self._video = video
        self._live_run = active_run

    def start(self) -> bool:
        try:
            import mujoco
        except ImportError:
            return False
        with self.lock:
            if self._ok:
                return True
            from xfold.shirt import load_mujoco_plugins

            load_mujoco_plugins()
            self._mujoco = mujoco
            self._build()
            self._ok = True
            self._source = "isaac"
            print(f"[sim-session] Isaac Sim ready kind=line nq={self.model.nq}", flush=True)
        return True

    def _build(self) -> None:
        """Model, data, stage and PhysX for the current garment (main thread)."""
        from xfold.line import build
        from xfold.shirt import shirt_config
        from xfold_isaac.isaac_backend import cloth_physics, create_backend
        from xfold_isaac.run import FollowCam

        from xfold_isaac.run import DEFAULT_TIMESTEP

        model = build()
        model.opt.timestep = self.timestep or DEFAULT_TIMESTEP
        data = self._mujoco.MjData(model)
        self._mujoco.mj_forward(model, data)
        self.model, self.data, self.cell, self.kind = model, data, None, "line"
        self.static_camera = "overview"
        self.camera = "follow"
        self.follow = FollowCam()
        self.backend = create_backend(
            self.kit, model, data, texture_dir=self._texture_dir, cloth=cloth_physics()
        )
        self.shim = None
        cfg = shirt_config()
        self._garment_key = f"{cfg.garment}:{cfg.texture}"
        # Something for the viewport before the first run.
        self.backend.set_camera("follow", *self.follow.pose(self._rest_cloth(), 0.0))
        self._grab(fresh=True)

    def _rest_cloth(self):
        import numpy as np

        start = int(self.model.flex_vertadr[0])
        return np.asarray(self.data.flexvert_xpos[start : start + int(self.model.flex_vertnum[0])])

    def ensure_garment(self, name: str, *, texture: str | None = None) -> None:
        if not self._ok:
            return
        from xfold.shirt import select_garment

        cfg = select_garment(name, texture=texture)
        token = f"{cfg.garment}:{cfg.texture}"
        with self.lock:
            if self._garment_key == token and cfg.garment != "custom":
                return
            self._build()
            print(f"[sim-session] rebuilt Isaac stage for garment={cfg.garment}", flush=True)

    def make_line(self, **kwargs: Any):
        from xfold.line import Line
        from xfold_isaac.engine import EngineShim

        line = Line(self.model, self.data, **kwargs)
        dt = float(self.model.opt.timestep)
        every = max(1, round(1.0 / (self.video_fps * dt)))
        self.shim = shim = EngineShim(line, self.backend, render_every=every)
        step = line.step

        def step_and_grab() -> None:
            rendered = shim.steps % every == 0
            step()
            if rendered:
                self._grab(fresh=False)

        line.step = step_and_grab
        return line

    def _grab(self, *, fresh: bool) -> None:
        """One render: full size into the recording, a small copy for live."""
        rgb = self.backend.capture(self.camera, *self.video_size, fresh=fresh)
        run_id = self._live_run() if self._live_run is not None else None
        if self._video is not None and run_id is not None:
            self._video.frame(run_id, rgb)
        with self._frame_lock:
            self._frame = self._shrink(rgb)

    def _shrink(self, rgb):
        """The live copy of a recorded frame. A whole-number stride (1080p to
        540p) is a few array reads; anything else needs a real resample."""
        import numpy as np

        wide, high = self.video_size
        if (wide, high) == (self.width, self.height):
            return rgb
        if wide % self.width == 0 and high % self.height == 0:
            step_x, step_y = wide // self.width, high // self.height
            return np.ascontiguousarray(rgb[::step_y, ::step_x])
        from PIL import Image

        return np.asarray(Image.fromarray(rgb).resize((self.width, self.height), Image.BILINEAR))

    def track_camera(self, cloth, dt: float) -> None:
        if self.backend is not None and self.follow is not None:
            self.backend.set_camera("follow", *self.follow.pose(cloth, dt))

    # --- what the bridge renders -----------------------------------------

    def render_rgb(self):
        with self._frame_lock:
            return None if self._frame is None else self._frame.copy()

    def render_jpeg(self):
        from xfold.bridge.viewport import encode_frame

        rgb = self.render_rgb()
        return None if rgb is None else encode_frame(rgb)

    def render_photo(self, camera: str, size: int | None = None):
        """The QC shot. Called from Line.on_photo, on the main thread."""
        from xfold.bridge.photo import PHOTO_SIZE
        from xfold.bridge.viewport import encode_frame

        size = size or PHOTO_SIZE
        try:
            if self.shim is not None:
                self.shim.sync_visuals()
            return encode_frame(self.backend.capture(camera, size, size), quality=88)
        except Exception as exc:  # noqa: BLE001
            print(f"[sim-session] product shot failed: {exc}", flush=True)
            return None

    def probe_render(self) -> bool:
        return self.render_rgb() is not None

    @property
    def can_render(self) -> bool:
        return self._ok

    def seek_render(self, qpos):
        return None

    def render_jpeg_unlocked(self, camera: Any = None):
        return self.render_jpeg()


if __name__ == "__main__":
    main()
