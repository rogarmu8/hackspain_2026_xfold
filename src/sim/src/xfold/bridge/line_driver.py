"""LineDriver — the real line (belt, press, flap folder, bagger) → journal.

The Driver owns the physics. `xfold.line.Line` is stepped here, inside
`SimSession.lock`, never in the renderer: the viewport only renders whatever
the shared session currently holds.

Integration contract: docs/INTEGRATION_CONTRACT.md §4 / §4b

=============================================================================
AGENT NOTE — PRESS / LINE TRACK
-----------------------------------------------------------------------------
Line stages are free-form strings (`Line._enter`). The dashboard stepper only
knows the six `CellState`s, so `_STAGE_STATE` maps one onto the other and
`_RANK` keeps the mapping monotonic — `BELT` means SPREAD on the way to the
press and nothing at all on the way to the carton, and the stepper must never
walk backwards.

Add a stage to `Line`? Add it to `_STAGE_STATE` too, or it silently keeps the
previous CellState.

  runtime.emit_state(run_id, CellState.<STAGE>, t=session.sim_time())
  runtime.emit_log(run_id, msg, source="line")

Respect pause/cancel via runtime.driver_active_run(). Do not import FastAPI.
Do not block mj_step on network I/O.
=============================================================================
"""

from __future__ import annotations

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


class LineDriver:
    """Steps xfold.line.Line on the shared SimSession and journals it."""

    def __init__(self, runtime: Runtime, session: SimSession) -> None:
        self.runtime = runtime
        self.session = session
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

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
            self._run_cycle(run)

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
        while True:
            run = self._active(run_id)
            if run is None:
                return False
            if run.paused or run.lifecycle == "paused":
                self.runtime.wait_wake(0.1)
                continue
            return True

    # --- the cycle -------------------------------------------------------

    def _run_cycle(self, run) -> None:
        from xfold.line import Line
        from xfold.shirt import shirt_config

        run_id = run.id
        seed = int(run.seed)
        garment = getattr(run, "garment", None) or shirt_config().garment
        skewed = bool(getattr(run, "skewed", False))
        custom_tex = getattr(run, "customTexture", None)
        recorder = TrajectoryRecorder(run_id, sample_hz=10.0)
        session = self.session
        dt = float(session.model.opt.timestep) if session.ok else 0.002

        # Line.log fires inside session.lock; emit_log takes the runtime lock.
        # Buffer here and flush once the session lock is released, so the two
        # locks are never held at the same time in this order.
        pending: list[str] = []

        try:
            shot: list[str] = []

            def take_photo() -> None:
                """QC camera → data/photos/{run}.jpg. Runs under session.lock.

                Only touches `pending` / `shot`; the journal call happens on
                the driver loop once the lock is released.
                """
                got = session.render_photo("qc_cam")
                if not got:
                    pending.append("foto de producto no disponible (sin GL)")
                    return
                payload, mime = got
                path = save_photo(run_id, payload, mime)
                shot.append(path.name)
                pending.append(
                    f"foto de producto · {path.name} · {len(payload) // 1024} kB"
                )

            session.ensure_garment(garment, texture=custom_tex)
            session.reset_time()
            dt = float(session.model.opt.timestep)
            with session.lock:
                line = Line(
                    session.model,
                    session.data,
                    repeat=False,
                    log=pending.append,
                    skewed=skewed,
                    seed=seed,
                    on_photo=take_photo,
                )
            cfg = shirt_config()
            self._log(
                run_id,
                f"ciclo iniciado · {cfg.garment} ({cfg.mesh}) · "
                f"{'prenda personalizada (recorte, dos caras)' if custom_tex else cfg.texture} · "
                f"{'colocada torcida' if skewed else 'colocada a escuadra'} · "
                f"seed {seed} · nq={session.model.nq} · timestep {dt:g}s",
            )

            state: CellState | None = None
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
                    stage_now = line.stage
                    finished = line.finished
                    qpos = np.asarray(session.data.qpos, dtype=np.float64).copy()
                    cloth = line.positions() if (track and session.follow) else None
                steps += 1

                for message in pending:
                    self.runtime.emit_log(run_id, message, source="line", t=t)
                    last_event = time.monotonic()
                pending.clear()
                if shot:
                    shot.clear()
                    self.runtime.mark_photo(run_id)

                if cloth is not None:
                    session.track_camera(cloth, _TRACK_EVERY * dt)
                recorder.maybe_sample(t, state.value if state else None, qpos)
                self.runtime.bump_sim_time(run_id, t)

                if stage_now != stage:
                    stage = stage_now
                    mapped = _STAGE_STATE.get(stage)
                    if mapped is not None and (
                        state is None or _RANK[mapped] > _RANK[state]
                    ):
                        state = mapped
                        if self._active(run_id) is None:
                            return
                        self.runtime.emit_state(run_id, state, t)
                        last_event = time.monotonic()

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
                recorder.maybe_sample(t, CellState.BAG.value, session.data.qpos)
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
