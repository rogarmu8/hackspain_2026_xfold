"""Shared MuJoCo session for bridge live view + trajectory seek.

One MjModel/MjData owned by the bridge process. The physics driver advances
it; the viewport only renders; recording seek temporarily restores qpos under
the same lock.

Integration contract: docs/INTEGRATION_CONTRACT.md §4b
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np

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
        self.camera = "overview"
        # One Renderer per thread — MuJoCo GL contexts are not cross-thread safe.
        self._renderers: dict[int, Any] = {}
        self._mujoco: Any = None
        self._ok = False
        self._source = "none"

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
                self.model, self.data, self.cell, self.camera = self._compile(mujoco)
                self.model.vis.global_.offwidth = max(
                    self.model.vis.global_.offwidth, self.width
                )
                self.model.vis.global_.offheight = max(
                    self.model.vis.global_.offheight, self.height
                )
                self._ok = True
                self._source = "mujoco"
                print(
                    f"[sim-session] ready camera={self.camera} "
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

    def _compile(self, mujoco):
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
            print("[sim-session] press_cell (flex shirt + UR5e)", flush=True)
            return cell.model, data, cell, camera
        except Exception as exc:
            print(
                f"[sim-session] press_cell compile failed ({exc}); using cell.xml",
                flush=True,
            )
            if not _CELL_FALLBACK.is_file():
                raise
            model = mujoco.MjModel.from_xml_path(_CELL_FALLBACK.as_posix())
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            return model, data, None, "overview"

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

    def apply_garment(
        self,
        kind: str | None,
        garment_id: str | None,
        seed: int,
    ) -> dict[str, str] | None:
        """Project a catalog photo onto the shirt skin / cloth material."""
        from xfold.garment import apply_to_model, project_for_run

        rgb, sample = project_for_run(kind, garment_id, seed)
        with self.lock:
            if not self._ok:
                return None
            apply_to_model(self.model, rgb)
            for renderer in list(self._renderers.values()):
                try:
                    renderer.close()
                except Exception:
                    pass
            self._renderers.clear()
        return sample

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
                return self.render_jpeg_unlocked()
            finally:
                self.data.qpos[:] = saved_qpos
                self.data.qvel[:] = saved_qvel
                self.data.time = saved_time
                self._mujoco.mj_forward(self.model, self.data)

    def render_jpeg(self) -> tuple[bytes, str] | None:
        with self.lock:
            return self.render_jpeg_unlocked()

    def render_jpeg_unlocked(self) -> tuple[bytes, str] | None:
        if not self._ok or self._mujoco is None:
            return None
        try:
            renderer = self._renderer_for_current_thread()
            renderer.update_scene(self.data, camera=self.camera)
            rgb = renderer.render()
            return encode_frame(np.asarray(rgb))
        except Exception as exc:  # noqa: BLE001
            print(f"[sim-session] render failed: {exc}", flush=True)
            return None
