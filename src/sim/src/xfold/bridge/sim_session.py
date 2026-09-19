"""Shared MuJoCo session for bridge live view + trajectory seek.

One MjModel/MjData owned by the bridge process. The physics driver advances
it; the viewport only renders; recording seek temporarily restores qpos under
the same lock.

Scene preference, best first (``kind`` says which one won):

  ``line``        line.xml -- belt, press, flap folder, bagger. LineDriver.
  ``press_cell``  the older arm cell. PressBridgeDriver.
  ``stub``        cell.xml. Renders, but nothing drives it.

Integration contract: docs/INTEGRATION_CONTRACT.md §4b
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np

from xfold.bridge.photo import PHOTO_SIZE
from xfold.bridge.viewport import encode_frame

# Fallback stub if press_cell fails to compile.
_CELL_FALLBACK = Path(__file__).resolve().parents[3] / "models" / "cell.xml"


class SimSession:
    """Thread-safe shared sim: step / forward / render / qpos snapshot."""

    def __init__(self, *, width: int = 640, height: int = 360) -> None:
        self.width = width
        self.height = height
        self.lock = threading.RLock()
        self.model: Any = None
        self.data: Any = None
        self.cell: Any = None
        self.kind = "none"
        # May be a camera name or an MjvCamera. The line uses a FollowCam so
        # the shirt does not shrink to a dot as it travels the 3 m of belt;
        # seek renders use `static_camera` instead, since the follow camera
        # tracks the live run, not the replayed one.
        self.camera: Any = "overview"
        self.static_camera = "overview"
        self.follow: Any = None
        # One Renderer per thread — MuJoCo GL contexts are not cross-thread safe.
        self._renderers: dict[int, Any] = {}
        self._mujoco: Any = None
        self._ok = False
        self._source = "none"
        # Offscreen GL is not always there (headless box, no EGL/OSMesa). MuJoCo
        # aborts the process if we keep poking a context that failed to make,
        # so one failure disables rendering for good and the bridge keeps
        # serving the journal without pixels.
        self._render_broken = False
        # Last SKU compiled into line.xml. None until the first successful compile.
        self._garment_key: str | None = None

    @property
    def ok(self) -> bool:
        return self._ok

    @property
    def source(self) -> str:
        return self._source

    def start(self) -> bool:
        """Compile scene (no GL yet). Returns False if MuJoCo unavailable."""
        try:
            import mujoco
        except ImportError:
            return False

        with self.lock:
            if self._ok:
                return True
            try:
                from xfold.shirt import load_mujoco_plugins

                load_mujoco_plugins()
                self._mujoco = mujoco
                self._compile(mujoco)
                self.model.vis.global_.offwidth = max(
                    self.model.vis.global_.offwidth, self.width, PHOTO_SIZE
                )
                self.model.vis.global_.offheight = max(
                    self.model.vis.global_.offheight, self.height, PHOTO_SIZE
                )
                self._ok = True
                self._source = "mujoco"
                print(
                    f"[sim-session] ready kind={self.kind} camera={self.static_camera} "
                    f"nq={self.model.nq} timestep={self.model.opt.timestep}",
                    flush=True,
                )
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"[sim-session] failed to start: {exc}", flush=True)
                self._teardown_unlocked()
                return False

    def stop(self) -> None:
        with self.lock:
            self._teardown_unlocked()

    def _teardown_unlocked(self) -> None:
        for renderer in self._renderers.values():
            try:
                renderer.close()
            except Exception:
                pass
        self._renderers.clear()
        self.model = None
        self.data = None
        self.cell = None
        self.kind = "none"
        self.follow = None
        self.camera = "overview"
        self._mujoco = None
        self._ok = False
        self._source = "none"

    def _renderer_for_current_thread(self) -> Any:
        """Lazy per-thread Renderer (must be called with lock held)."""
        tid = threading.get_ident()
        renderer = self._renderers.get(tid)
        if renderer is None:
            renderer = self._mujoco.Renderer(
                self.model, height=self.height, width=self.width
            )
            self._renderers[tid] = renderer
        return renderer

    def _compile(self, mujoco) -> None:
        """Pick the best scene available and set model/data/cell/camera/kind."""
        if self._compile_line(mujoco):
            return
        if self._compile_press_cell(mujoco):
            return
        self._compile_stub(mujoco)

    def _compile_line(self, mujoco) -> bool:
        """line.xml — the belt/press/folder/bagger cycle LineDriver runs."""
        try:
            from xfold.line import FollowCam, build

            model = build()
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
        except Exception as exc:  # noqa: BLE001
            print(f"[sim-session] line compile failed ({exc}); trying press_cell", flush=True)
            return False
        self.model, self.data, self.cell, self.kind = model, data, None, "line"
        self.static_camera = "overview"
        self.follow = FollowCam()
        self.camera = self.follow.cam
        from xfold.shirt import shirt_config

        self._garment_key = f"{shirt_config().garment}:{shirt_config().texture}"
        print("[sim-session] line.xml (belt, press, folder, bagger)", flush=True)
        return True

    def _compile_press_cell(self, mujoco) -> bool:
        """The older arm cell, kept as a fallback for the press track."""
        try:
            from xfold.scene import build, spawn_shirt_in_bin

            cell = build()
            data = mujoco.MjData(cell.model)
            spawn_shirt_in_bin(cell, data, np.random.default_rng(7))
            mujoco.mj_forward(cell.model, data)
        except Exception as exc:  # noqa: BLE001
            print(f"[sim-session] press_cell compile failed ({exc}); using cell.xml", flush=True)
            return False
        camera = "overview"
        try:
            cell.model.camera(camera)
        except KeyError:
            camera = "cell_cam"
        self.model, self.data, self.cell, self.kind = cell.model, data, cell, "press_cell"
        self.camera = self.static_camera = camera
        self.follow = None
        print("[sim-session] press_cell (flex shirt + UR5e)", flush=True)
        return True

    def _compile_stub(self, mujoco) -> None:
        """cell.xml — renders, but no driver advances it."""
        if not _CELL_FALLBACK.is_file():
            raise RuntimeError("no scene compiles and models/cell.xml is missing")
        model = mujoco.MjModel.from_xml_path(_CELL_FALLBACK.as_posix())
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        self.model, self.data, self.cell, self.kind = model, data, None, "stub"
        self.camera = self.static_camera = "overview"
        self.follow = None

    def track_camera(self, cloth: np.ndarray, dt: float) -> None:
        """Move the follow camera's look-at toward the cloth. No-op if fixed."""
        if self.follow is not None:
            self.follow.track(cloth, dt)

    def ensure_garment(self, name: str, *, texture: str | None = None) -> None:
        """Recompile the line if the launch SKU is a different mesh/texture.

        Different catalogue items are different flexcomps. Pose-only changes
        (``skewed``) do not need a rebuild — ``Line`` handles those per cycle.
        A custom garment swaps in a silhouette mesh plus the cut-out PNG:
        still rebuilds, because both are compiled into the MJCF asset.
        """
        if not self._ok or self.kind != "line":
            return
        from xfold.shirt import select_garment

        cfg = select_garment(name, texture=texture)
        token = f"{cfg.garment}:{cfg.texture}"
        with self.lock:
            # Same SKU token would skip a second custom photo. Always recompile.
            if self._garment_key == token and cfg.garment != "custom":
                return
            self._rebuild_line_unlocked()
            self._garment_key = token
            print(
                f"[sim-session] rebuilt line for garment={cfg.garment} "
                f"tex={cfg.texture} nq={self.model.nq}",
                flush=True,
            )

    def _rebuild_line_unlocked(self) -> None:
        """Swap MjModel/MjData after ``select_garment``. Caller holds ``lock``."""
        for renderer in self._renderers.values():
            try:
                renderer.close()
            except Exception:
                pass
        self._renderers.clear()
        from xfold.line import FollowCam, build

        model = build()
        data = self._mujoco.MjData(model)
        self._mujoco.mj_forward(model, data)
        self.model, self.data, self.cell, self.kind = model, data, None, "line"
        self.follow = FollowCam()
        self.camera = self.follow.cam
        self.static_camera = "overview"

    def reset_shirt(self, seed: int) -> None:
        """Respawn cloth in the bin for a new run."""
        if not self._ok or self.cell is None:
            return
        from xfold.scene import spawn_shirt_in_bin

        with self.lock:
            spawn_shirt_in_bin(
                self.cell, self.data, np.random.default_rng(int(seed) & 0xFFFFFFFF)
            )
            self._mujoco.mj_forward(self.model, self.data)

    def place_shirt_on_bed(self) -> None:
        """Lay the flex shirt onto the heated bed (SPREAD without full arm)."""
        if not self._ok or self.cell is None:
            return
        from xfold.shirt import set_shirt_world

        cell = self.cell
        with self.lock:
            local = np.asarray(cell.shirt_rest_local, dtype=float).copy()
            local -= local.mean(axis=0)
            world = local.copy()
            world[:, 0] += float(cell.bed_center[0])
            world[:, 1] += float(cell.bed_center[1])
            world[:, 2] += (
                float(cell.bed_surface_z + cell.shirt_half_thickness)
                - float(world[:, 2].min())
            )
            set_shirt_world(
                self.data, world, cell.shirt_rest_world, cell.shirt_qposadr
            )
            self.data.qvel[:] = 0.0
            self._mujoco.mj_forward(self.model, self.data)

    def reset_time(self) -> None:
        with self.lock:
            if self._ok:
                self.data.time = 0.0

    def step(self, count: int = 1) -> float:
        """Advance physics under lock. Returns sim time after steps."""
        with self.lock:
            return self.step_unlocked(count)

    def step_unlocked(self, count: int = 1) -> float:
        assert self._ok and self._mujoco is not None
        for _ in range(count):
            self._mujoco.mj_step(self.model, self.data)
        return float(self.data.time)

    def forward(self) -> None:
        with self.lock:
            if self._ok:
                self._mujoco.mj_forward(self.model, self.data)

    def sim_time(self) -> float:
        with self.lock:
            if not self._ok:
                return 0.0
            return float(self.data.time)

    def copy_qpos(self) -> np.ndarray:
        with self.lock:
            return np.asarray(self.data.qpos, dtype=np.float64).copy()

    def apply_qpos(self, qpos: np.ndarray) -> None:
        with self.lock:
            self.data.qpos[:] = np.asarray(qpos, dtype=np.float64)
            self.data.qvel[:] = 0.0
            self._mujoco.mj_forward(self.model, self.data)

    def seek_render(
        self, qpos: np.ndarray
    ) -> tuple[bytes, str] | None:
        """Temporarily apply qpos, render, restore. Safe during live runs."""
        with self.lock:
            if not self._ok:
                return None
            saved_qpos = np.asarray(self.data.qpos, dtype=np.float64).copy()
            saved_qvel = np.asarray(self.data.qvel, dtype=np.float64).copy()
            saved_time = float(self.data.time)
            try:
                self.data.qpos[:] = np.asarray(qpos, dtype=np.float64)
                self.data.qvel[:] = 0.0
                self._mujoco.mj_forward(self.model, self.data)
                return self.render_jpeg_unlocked(camera=self.static_camera)
            finally:
                self.data.qpos[:] = saved_qpos
                self.data.qvel[:] = saved_qvel
                self.data.time = saved_time
                self._mujoco.mj_forward(self.model, self.data)

    def render_photo(
        self, camera: str, size: int = PHOTO_SIZE
    ) -> tuple[bytes, str] | None:
        """One square frame from a named camera — the QC product shot.

        Its own Renderer, because it is square and larger than the viewport's,
        and it is thrown away afterwards: this runs once per cycle, not per
        frame. A failure here is local to the shot and does not disable the
        viewport.
        """
        with self.lock:
            if not self._ok or self._mujoco is None or self._render_broken:
                return None
            renderer = None
            try:
                renderer = self._mujoco.Renderer(self.model, height=size, width=size)
                renderer.update_scene(self.data, camera=camera)
                return encode_frame(np.asarray(renderer.render()), quality=88)
            except Exception as exc:  # noqa: BLE001
                print(f"[sim-session] product shot failed: {exc}", flush=True)
                return None
            finally:
                if renderer is not None:
                    try:
                        renderer.close()
                    except Exception:
                        pass

    def render_jpeg(self) -> tuple[bytes, str] | None:
        """Live viewport frame, holding the lock only as long as it must.

        `update_scene` reads MjData and needs the lock; rasterising works off
        the scene it just filled and does not. Keeping the whole render under
        the lock starves the driver — on software GL a frame costs tens of
        milliseconds, and at 12 fps that is most of the wall clock.
        """
        with self.lock:
            if not self._ok or self._mujoco is None or self._render_broken:
                return None
            try:
                renderer = self._renderer_for_current_thread()
                renderer.update_scene(self.data, camera=self.camera)
            except Exception as exc:  # noqa: BLE001
                self._render_broken = True
                self._renderers.pop(threading.get_ident(), None)
                print(
                    f"[sim-session] offscreen render unavailable ({exc}); "
                    "continuing without a viewport",
                    flush=True,
                )
                return None
        try:
            return encode_frame(np.asarray(renderer.render()))
        except Exception as exc:  # noqa: BLE001
            print(f"[sim-session] render failed: {exc}", flush=True)
            return None

    def render_jpeg_unlocked(self, camera: Any = None) -> tuple[bytes, str] | None:
        if not self._ok or self._mujoco is None or self._render_broken:
            return None
        try:
            renderer = self._renderer_for_current_thread()
            renderer.update_scene(
                self.data, camera=self.camera if camera is None else camera
            )
            rgb = renderer.render()
            return encode_frame(np.asarray(rgb))
        except Exception as exc:  # noqa: BLE001
            self._render_broken = True
            self._renderers.pop(threading.get_ident(), None)
            print(
                f"[sim-session] offscreen render unavailable ({exc}); "
                "continuing without a viewport",
                flush=True,
            )
            return None

    @property
    def can_render(self) -> bool:
        return self._ok and not self._render_broken

    def probe_render(self) -> bool:
        """Render one throwaway frame to find out if this box has offscreen GL.

        Called once at startup, before the viewport producer thread exists:
        a GL context that cannot be made must fail here, on one thread, not
        under a running producer where MuJoCo aborts the process.
        """
        with self.lock:
            if not self._ok:
                return False
            return self.render_jpeg_unlocked(camera=self.static_camera) is not None
