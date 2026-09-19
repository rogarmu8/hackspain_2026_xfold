"""LineDriver — the real line (belt, press, flap folder, bagger) → journal.

The Driver owns the physics. `xfold.line.Line` is stepped here, inside
`SimSession.lock`, never in the renderer: the viewport only renders whatever
the shared session currently holds.

Integration contract: docs/INTEGRATION_CONTRACT.md §4 / §4b

=============================================================================
AGENT NOTE — PRESS / LINE TRACK
-----------------------------------------------------------------------------
Line owns its phase catalogue and observations (`LINE_PHASES`, `on_event`).
The driver forwards those facts without translating or suppressing phases.
The legacy `_STAGE_STATE` / `_RANK` constants below are not used by this driver.
Add phases and operations in Line; the dashboard receives their IDs and labels.

  runtime.emit_state(run_id, CellState.<STAGE>, t=session.sim_time())
  runtime.emit_log(run_id, msg, source="line")

Respect pause/cancel via runtime.driver_active_run(). Do not import FastAPI.
Do not block mj_step on network I/O.
=============================================================================
"""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

from xfold.bridge.photo import save_photo
from xfold.bridge.trajectory import TrajectoryRecorder
from xfold.fsm import CellState

if TYPE_CHECKING:
    from xfold.bridge.runtime import Runtime
    from xfold.bridge.sim_session import SimSession

# Line stage -> the cell state the dashboard stepper shows.
_STAGE_STATE: dict[str, CellState] = {
    "LOAD": CellState.PICK,
    "BELT": CellState.SPREAD,  # only the first belt move; see _RANK
    "PRESS": CellState.PRESS,
    "STEAM": CellState.PRESS,
    "LIFT": CellState.PRESS,
    "PHOTO": CellState.PRESS,  # the QC shot, still at the press end of the line
    "SETTLE": CellState.FOLD,
    "BAGGER": CellState.FOLD,  # runs interleaved with the flap folds
    "FOLD": CellState.FOLD,
    "BAG": CellState.CHUTE,
    "TILT": CellState.CHUTE,
    "PEEL": CellState.CHUTE,
    "RELEASE": CellState.CHUTE,
    "INDEX": CellState.BAG,
    "SEAL": CellState.BAG,
    "DONE": CellState.BAG,
}

# Cycle order, so a stage that maps backwards is ignored rather than emitted.
_RANK: dict[CellState, int] = {
    CellState.PICK: 0,
    CellState.SPREAD: 1,
    CellState.PRESS: 2,
    CellState.FOLD: 3,
    CellState.CHUTE: 4,
    CellState.BAG: 5,
}

# Camera look-at and trajectory sampling do not need every physics step.
_TRACK_EVERY = 16  # ~30 Hz at timestep 0.002
# The UI flags a stall after 8 s without an event; keep well under it.
_HEARTBEAT_S = 5.0
# A cycle is ~45 s of sim time. Well past that, something is wedged.
_SIM_TIME_CAP_S = 240.0


def _skewed_default() -> bool:
    """XFOLD_SKEWED=1 drops the shirt off square, like `--skewed` on the CLI."""
    return os.environ.get("XFOLD_SKEWED", "").strip().lower() in {"1", "true", "yes", "on"}


class LineDriver:
    """Steps xfold.line.Line on the shared SimSession and journals it."""

    def __init__(self, runtime: Runtime, session: SimSession) -> None:
        self.runtime = runtime
        self.session = session
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        from dataclasses import asdict
        from xfold.line import LINE_PHASES
        from xfold.shirt import shirt_config

        cfg = shirt_config()
        inputs = asdict(cfg)
        inputs["path"] = str(cfg.path)
        inputs.update({"skewed": _skewed_default(), "seedApplied": False, "driver": "line"})
        runtime.configure_process(LINE_PHASES, scenario="line", config=inputs)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="xfold-line-driver", daemon=True
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

    # --- journal helpers ------------------------------------------------

    def _log(self, run_id: str, message: str, level: str = "info") -> None:
        """stdout for the operator terminal + journal ``log`` for the console."""
        print(f"[line-driver] {message}", flush=True)
        self.runtime.emit_log(
            run_id, message, level=level, source="line", t=self.session.sim_time()
        )

    def _active(self, run_id: str):
        """The run if it is still ours and not cancelled, else None."""
        run = self.runtime.driver_active_run()
        if run is None or run.id != run_id:
            return None
        if run.cancel_requested or run.lifecycle == "cancelled":
            return None
        return run

    def _wait_unpaused(self, run_id: str) -> bool:
        """Block while the run is paused. False once it is gone or cancelled."""
        while not self._stop.is_set():
            run = self._active(run_id)
            if run is None:
                return False
            if run.paused or run.lifecycle == "paused":
                self.runtime.wait_wake(0.1)
                continue
            return True
        return False

    def _publish(self, run_id: str, observation: dict) -> None:
        if self._active(run_id) is None:
            return
        self.runtime.emit_state(run_id, observation["state"], observation["t"])
        self.runtime.emit_log(
            run_id, observation["message"], t=observation["t"],
            source="bagger" if observation["parallel"] else "line",
            operation=observation["operation"], station=observation["station"],
            parallel=observation["parallel"], level=observation.get("level", "info"),
        )
        if observation["measurements"]:
            self.runtime.emit_metrics(run_id, observation["t"], observation["measurements"])

    def _capture_photo(self, run_id: str, line) -> str | None:
        got = self.session.render_photo("qc_cam")
        if not got:
            line._observe("PHOTO_UNAVAILABLE", "foto de producto no disponible (sin GL)", level="warning")
            return None
        payload, mime = got
        path = save_photo(run_id, payload, mime)
        line._observe("PHOTO_SAVED", f"foto de producto · {path.name} · {len(payload) // 1024} kB")
        return path.name

    # --- the cycle -------------------------------------------------------

    def _run_cycle(self, run_id: str, seed: int) -> None:
        from xfold.line import Line
        from xfold.shirt import shirt_config

        recorder = TrajectoryRecorder(run_id, sample_hz=10.0)
        session = self.session
        dt = float(session.model.opt.timestep)
        skewed = _skewed_default()

        # Line.log fires inside session.lock; emit_log takes the runtime lock.
        # Buffer here and flush once the session lock is released, so the two
        # locks are never held at the same time in this order.
        pending: list[dict] = []

        try:
            shot: list[str] = []

            def take_photo() -> None:
                """QC camera → data/photos/{run}.jpg. Runs under session.lock.

                Only touches `pending` / `shot`; the journal call happens on
                the driver loop once the lock is released.
                """
                name = self._capture_photo(run_id, line)
                if name:
                    shot.append(name)

            session.reset_time()
            with session.lock:
                line = Line(
                    session.model,
                    session.data,
                    repeat=False,
                    log=lambda message: None,
                    skewed=skewed,
                    on_event=pending.append,
                    on_photo=take_photo,
                )
            cfg = shirt_config()
            self._log(
                run_id,
                f"ciclo iniciado · {cfg.garment} ({cfg.mesh}) · "
                f"{'colocada torcida' if skewed else 'colocada a escuadra'} · "
                f"seed {seed} (no aplicada por esta línea) · nq={session.model.nq} · timestep {dt:g}s",
            )

            stage = ""
            last_event = time.monotonic()
            steps = 0

            while True:
                if not self._wait_unpaused(run_id):
                    return

                started = time.perf_counter()
                track = steps % _TRACK_EVERY == 0
                with session.lock:
                    line.step()
                    t = float(session.data.time)
                    stage = line.phase
                    finished = line.finished
                    qpos = np.asarray(session.data.qpos, dtype=np.float64).copy()
                    cloth = line.positions() if (track and session.follow) else None
                steps += 1

                for observation in pending:
                    self._publish(run_id, observation)
                    last_event = time.monotonic()
                pending.clear()
                if shot:
                    shot.clear()
                    self.runtime.mark_photo(run_id)

                if cloth is not None:
                    session.track_camera(cloth, _TRACK_EVERY * dt)
                recorder.maybe_sample(t, stage, qpos)
                self.runtime.bump_sim_time(run_id, t)

                if finished:
                    break

                if t > _SIM_TIME_CAP_S:
                    self._log(
                        run_id,
                        f"ciclo abandonado a los {t:.0f}s de simulación en {stage or '?'}",
                        level="error",
                    )
                    self.runtime.finish_failed(run_id, t, reason="cycle did not finish")
                    return

                now = time.monotonic()
                if now - last_event > _HEARTBEAT_S:
                    # Keep the console's stall watchdog quiet during a long,
                    # legitimate phase (steam dwell, belt run).
                    self._log(run_id, f"{stage or '?'} en curso · t={t:.1f}s", level="debug")
                    last_event = time.monotonic()

                leftover = dt - (time.perf_counter() - started)
                if leftover > 0:
                    time.sleep(leftover)

            t = session.sim_time()
            if self._active(run_id) is None:
                return
            with session.lock:
                recorder.maybe_sample(t, line.phase, session.data.qpos)
            self._log(run_id, f"ciclo completo · {t:.1f}s de simulación")
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
