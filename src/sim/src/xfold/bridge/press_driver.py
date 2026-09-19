"""PressBridgeDriver — real PressCycle physics → Runtime journal.

Replaces MockDriver when SimSession starts. Emits CellState with t=data.time.
Records trajectory samples for replay seek.

Integration contract: docs/INTEGRATION_CONTRACT.md §4 / §4b

=============================================================================
AGENT NOTE — ARM / FSM TRACK
-----------------------------------------------------------------------------
This is the live MuJoCo Driver. Arm teammates: extend the cycle stages here
(or call runtime.emit_state from your controller) — same Runtime API.

  runtime.emit_state(run_id, CellState.<STAGE>, t=float(data.time))
  runtime.finish_success(run_id, t=float(data.time))

Respect pause/cancel via runtime.driver_active_run(). Do not import FastAPI.
Do not block mj_step on network I/O.
=============================================================================
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import numpy as np

from xfold.bridge.trajectory import TrajectoryRecorder
from xfold.fsm import CellState
from xfold.press_cycle import PressCycle

if TYPE_CHECKING:
    from xfold.bridge.runtime import Runtime
    from xfold.bridge.sim_session import SimSession


class BridgeLoop:
    """Loop-compatible stepper over SimSession; respects pause/cancel."""

    def __init__(
        self,
        session: SimSession,
        runtime: Runtime,
        run_id: str,
        recorder: TrajectoryRecorder | None,
        *,
        realtime: bool = True,
    ) -> None:
        self.session = session
        self.runtime = runtime
        self.run_id = run_id
        self.recorder = recorder
        self.realtime = realtime
        self.model = session.model
        self.data = session.data

    @property
    def running(self) -> bool:
        run = self.runtime.driver_active_run()
        return (
            run is not None
            and run.id == self.run_id
            and not run.cancel_requested
            and run.lifecycle not in {"cancelled", "failed", "succeeded"}
        )

    def steps_for(self, seconds: float) -> int:
        return max(1, int(round(seconds / float(self.model.opt.timestep))))

    def step(self, count: int = 1) -> bool:
        for _ in range(count):
            if not self._wait_unpaused():
                return False
            started = time.perf_counter()
            with self.session.lock:
                t = self.session.step_unlocked(1)
                qpos_copy = (
                    np.asarray(self.session.data.qpos, dtype=np.float64).copy()
                    if self.recorder is not None
                    else None
                )
            run = self.runtime.driver_active_run()
            state = run.currentState if run else None
            if self.recorder is not None and qpos_copy is not None:
                self.recorder.maybe_sample(t, state, qpos_copy)
            self.runtime.bump_sim_time(self.run_id, t)
            if self.realtime:
                leftover = float(self.model.opt.timestep) - (
                    time.perf_counter() - started
                )
                if leftover > 0:
                    time.sleep(leftover)
        return self.running

    def hold(self, seconds: float) -> bool:
        return self.step(self.steps_for(seconds))

    def _wait_unpaused(self) -> bool:
        while True:
            if not self.running:
                return False
            run = self.runtime.driver_active_run()
            if run is None or run.id != self.run_id:
                return False
            if run.paused or run.lifecycle == "paused":
                self.runtime.wait_wake(0.1)
                continue
            return True


class PressBridgeDriver:
    """Runs press-centric cycle on shared SimSession; MockDriver is the fallback."""

    def __init__(self, runtime: Runtime, session: SimSession) -> None:
        self.runtime = runtime
        self.session = session
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._recorders: dict[str, TrajectoryRecorder] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="xfold-press-driver", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.runtime.wake_driver()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            run = self.runtime.driver_active_run()
            if run is None:
                self.runtime.wait_wake(0.5)
                continue
            if run.paused or run.lifecycle == "paused":
                self.runtime.wait_wake(0.25)
                continue
            self._run_cycle(run.id, run.seed)

    def _log(self, run_id: str, message: str, level: str = "info") -> None:
        """stdout for the operator terminal + journal ``log`` for the dashboard console."""
        print(f"[press-driver] {message}", flush=True)
        self.runtime.emit_log(
            run_id, message, level=level, source="press-driver", t=self.session.sim_time()
        )

    def _run_cycle(self, run_id: str, seed: int) -> None:
        recorder = TrajectoryRecorder(run_id, sample_hz=10.0)
        self._recorders[run_id] = recorder
        try:
            self.session.reset_time()
            self.session.reset_shirt(seed)
            run = self.runtime.driver_active_run()
            kind = getattr(run, "garmentKind", "tshirt") if run else "tshirt"
            garment_id = getattr(run, "garmentId", None) if run else None
            try:
                sample = self.session.apply_garment(kind, garment_id, seed)
                if sample:
                    self._log(
                        run_id,
                        f"prenda {sample['kind']} · {sample['id']} proyectada en el flex",
                    )
            except Exception as exc:  # noqa: BLE001
                self._log(run_id, f"proyección de prenda falló: {exc}", level="warning")
            self._log(
                run_id,
                f"ciclo iniciado · seed {seed} · timestep {self.session.model.opt.timestep:g}s · nq={self.session.model.nq}",
            )

            press = PressCycle(self.session.model, self.session.data)
            with self.session.lock:
                press.park()
                self.session._mujoco.mj_forward(self.session.model, self.session.data)

            loop = BridgeLoop(
                self.session, self.runtime, run_id, recorder, realtime=True
            )

            # --- PICK: cloth settles in the crate ---
            if not self._emit(run_id, CellState.PICK):
                return
            if not loop.hold(1.2):
                self._abort_or_fail(run_id, recorder)
                return

            # --- SPREAD: place on bed + settle ---
            if not self._emit(run_id, CellState.SPREAD):
                return
            self.session.place_shirt_on_bed()
            if not loop.hold(1.0):
                self._abort_or_fail(run_id, recorder)
                return

            # --- PRESS: platen + steam (real PressCycle) ---
            if not self._emit(run_id, CellState.PRESS):
                return
            if not press.press(loop, close=3.5, steam=4.0, lift=3.0):
                self._abort_or_fail(run_id, recorder)
                return

            # --- FOLD: brief dwell (ninja fold not wired yet) ---
            if not self._emit(run_id, CellState.FOLD):
                return
            if not loop.hold(1.5):
                self._abort_or_fail(run_id, recorder)
                return

            # --- CHUTE: bed dump ---
            if not self._emit(run_id, CellState.CHUTE):
                return
            if not press.dump(loop, tilt=2.5, settle=2.0, back=2.5):
                self._abort_or_fail(run_id, recorder)
                return

            # --- BAG ---
            if not self._emit(run_id, CellState.BAG):
                return
            if not loop.hold(0.8):
                self._abort_or_fail(run_id, recorder)
                return

            final = self.runtime.driver_active_run()
            if final and final.id == run_id and final.lifecycle == "running":
                t = self.session.sim_time()
                with self.session.lock:
                    recorder.maybe_sample(
                        t, CellState.BAG.value, self.session.data.qpos
                    )
                self.runtime.finish_success(run_id, t)
        except Exception as exc:  # noqa: BLE001
            self._log(run_id, f"cycle failed: {exc}", level="error")
            final = self.runtime.driver_active_run()
            if final and final.id == run_id and final.lifecycle == "running":
                self.runtime.finish_failed(
                    run_id, self.session.sim_time(), reason=str(exc)
                )
        finally:
            path = recorder.finalize()
            if path:
                self._log(run_id, f"trajectory → {path}", level="debug")
            self._recorders.pop(run_id, None)

    def _emit(self, run_id: str, state: CellState) -> bool:
        run = self.runtime.driver_active_run()
        if run is None or run.id != run_id:
            return False
        if run.cancel_requested or run.lifecycle == "cancelled":
            return False
        while run.paused or run.lifecycle == "paused":
            self.runtime.wait_wake(0.1)
            run = self.runtime.driver_active_run()
            if run is None or run.id != run_id:
                return False
            if run.cancel_requested or run.lifecycle == "cancelled":
                return False
        t = self.session.sim_time()
        # Skip duplicate if launch already set PICK at t=0
        if (
            state == CellState.PICK
            and run.currentState == CellState.PICK.value
            and run.t == 0.0
        ):
            # Re-emit at current t so journal has a real sim-time marker
            if t > 0:
                self.runtime.emit_state(run_id, state, t)
            return True
        self.runtime.emit_state(run_id, state, t)
        return True

    def _abort_or_fail(
        self, run_id: str, recorder: TrajectoryRecorder
    ) -> None:
        run = self.runtime.driver_active_run()
        if run is None or run.id != run_id:
            return
        if run.cancel_requested or run.lifecycle == "cancelled":
            return
        if run.lifecycle == "running":
            self._log(
                run_id,
                f"ciclo interrumpido en {run.currentState or '?'} · t={self.session.sim_time():.2f}s",
                level="warning",
            )
            self.runtime.finish_failed(
                run_id, self.session.sim_time(), reason="cycle interrupted"
            )
