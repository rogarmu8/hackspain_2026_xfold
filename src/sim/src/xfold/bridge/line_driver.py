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
Infeed: Line stage ORIENT is the dual-belt turner (phase ORIENT).

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
from xfold.garments import garment_result_label, grade_line_outcome

if TYPE_CHECKING:
    from xfold.bridge.runtime import Runtime
    from xfold.bridge.sim_session import SimSession

# Line stage -> the cell state the dashboard stepper shows.
_STAGE_STATE: dict[str, CellState] = {
    "LOAD": CellState.PICK,
    "ORIENT": CellState.ORIENT,
    "BELT": CellState.SPREAD,  # only the first belt move; see _RANK
    "PRESS": CellState.PRESS,
    "STEAM": CellState.PRESS,
    "LIFT": CellState.PRESS,
    "PHOTO": CellState.PRESS,  # the QC shot, still at the press end of the line
    "SORT": CellState.PRESS,  # pass or suction-divert into a reject tote
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
    CellState.ORIENT: 1,
    CellState.SPREAD: 2,
    CellState.PRESS: 3,
    CellState.FOLD: 4,
    CellState.CHUTE: 5,
    CellState.BAG: 6,
}

# Camera look-at and trajectory sampling do not need every physics step.
_TRACK_EVERY = 16  # ~30 Hz at timestep 0.002
# The UI flags a stall after 8 s without an event; keep well under it.
_HEARTBEAT_S = 5.0
# A cycle is ~45 s of sim time at nominal speed, and proportionally less as
# the machines speed up. Well past that, the line is not doing the cycle any
# more — usually cloth that stopped being carried — so the run is failed
# rather than left dragging.
_SIM_TIME_CAP_S = 240.0


class LineDriver:
    """Steps xfold.line.Line on a SimSession and journals it.

    One worker per session: each claims a run from the Runtime, simulates its
    cycle on its own session, and releases it. With several sessions the
    bridge runs that many experiments at once and queues the rest; with one
    (the default, and all Isaac can do) it behaves as it always did.
    """

    def __init__(self, runtime: Runtime, session: SimSession, *, sessions=None) -> None:
        self.runtime = runtime
        self.sessions = list(sessions) if sessions else [session]
        # The first session is "the" one for callers that need a single sim
        # (recording seek, the focused viewport).
        self.session = self.sessions[0]
        runtime.concurrency = len(self.sessions)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._threads: list[threading.Thread] = []
        from dataclasses import asdict
        from xfold.line import LINE_PHASES
        from xfold.shirt import shirt_config

        cfg = shirt_config()
        inputs = asdict(cfg)
        inputs["path"] = str(cfg.path)
        inputs.update({"seedApplied": True, "driver": "line"})
        runtime.configure_process(LINE_PHASES, scenario="line", config=inputs)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._threads = [
            threading.Thread(
                target=self._loop,
                args=(f"w{index}", session),
                name=f"xfold-line-driver-{index}",
                daemon=True,
            )
            for index, session in enumerate(self.sessions)
        ]
        for thread in self._threads:
            thread.start()
        self._thread = self._threads[0]

    def run_here(self) -> None:
        """Run the driver loop on the calling thread, until ``stop()``.

        For engines whose API only works on one thread (Isaac Sim's Kit): the
        caller keeps the main thread for this and serves HTTP elsewhere.
        """
        self._stop.clear()
        self._loop("w0", self.session)

    def stop(self) -> None:
        self._stop.set()
        self.runtime.wake_driver()
        for thread in self._threads or ([self._thread] if self._thread else []):
            thread.join(timeout=2.0)

    def _loop(self, worker: str, session: SimSession) -> None:
        while not self._stop.is_set():
            run = self.runtime.claim_run(worker)
            if run is None:
                self.runtime.wait_wake(0.5)
                continue
            try:
                self._run_cycle(run, session)
            finally:
                self.runtime.release_run(run.id)

    # --- journal helpers ------------------------------------------------

    def _log(self, run_id: str, message: str, level: str = "info", session: SimSession | None = None) -> None:
        """stdout for the operator terminal + journal ``log`` for the console."""
        print(f"[line-driver] {run_id} {message}", flush=True)
        self.runtime.emit_log(
            run_id, message, level=level, source="line",
            t=(session or self.session).sim_time(),
        )

    def _active(self, run_id: str):
        """The run if it is still going and not cancelled, else None."""
        run = self.runtime.driver_run(run_id)
        if run is None:
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

    def _force_quit(self, run_id: str, line, session: SimSession | None = None) -> None:
        """Stop the Line now. Cancel does not wait for the current phase."""
        session = session or self.session
        try:
            with session.lock:
                abort = getattr(line, "abort", None)
                if callable(abort):
                    abort()
                else:
                    line.finished = True
        except Exception:  # noqa: BLE001 — the run is already cancelled
            pass
        video = getattr(session, "_video", None)
        end = getattr(video, "end", None)
        if callable(end):
            try:
                end(run_id)
            except Exception:  # noqa: BLE001
                pass
        self._log(run_id, "cycle force-quit", session=session)

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

    def _capture_photo(self, run_id: str, line, session: SimSession | None = None) -> str | None:
        got = (session or self.session).render_photo("qc_cam")
        if not got:
            line._observe("PHOTO_UNAVAILABLE", "product photo unavailable (no GL)", level="warning")
            return None
        payload, mime = got
        path = save_photo(run_id, payload, mime)
        line._observe("PHOTO_SAVED", f"product photo · {path.name} · {len(payload) // 1024} kB")
        return path.name

    def _score_fold(self, run_id: str, line, session: SimSession | None = None) -> float | None:
        """Render fold_qc_cam, save the OpenCV overlay, return the percent."""
        from xfold.bridge.photo import save_fold_photo
        from xfold.bridge.viewport import encode_frame
        from xfold.fold_quality import inspect_fold

        session = session or self.session
        render = getattr(session, "render_rgb_camera", None)
        rgb = render("fold_qc_cam") if callable(render) else None
        if rgb is None:
            line._observe(
                "FOLD_QC_UNAVAILABLE",
                "fold quality camera unavailable (no GL)",
                level="warning",
            )
            return None
        got = inspect_fold(rgb)
        if got.score is None:
            line._observe(
                "FOLD_QC_UNAVAILABLE",
                "fold quality camera saw no pack",
                level="warning",
            )
            return None
        if got.annotated is not None:
            payload, mime = encode_frame(got.annotated, quality=88)
            path = save_fold_photo(run_id, payload, mime)
            line._observe(
                "FOLD_QC_SAVED",
                f"fold eval · {path.name} · {got.score:.0f}%",
            )
        return got.score

    # --- the cycle -------------------------------------------------------

    def _run_cycle(self, run, session: SimSession | None = None) -> None:
        from xfold.shirt import shirt_config

        run_id = run.id
        seed = int(run.seed)
        garment = getattr(run, "garment", None) or shirt_config().garment
        skewed = bool(getattr(run, "skewed", False))
        custom_tex = getattr(run, "customTexture", None)
        speed = float(getattr(run, "speed", 1.0) or 1.0)
        recorder = TrajectoryRecorder(run_id, sample_hz=10.0)
        session = session or self.session
        dt = float(session.model.opt.timestep) if session.ok else 0.002

        # Line.log fires inside session.lock; emit_log takes the runtime lock.
        # Buffer here and flush once the session lock is released, so the two
        # locks are never held at the same time in this order.
        pending: list[dict] = []

        try:
            shot: list[str] = []
            fold_shot: list[str] = []

            def take_photo() -> None:
                """QC camera → data/photos/{run}.jpg. Runs under session.lock.

                Only touches `pending` / `shot`; the journal call happens on
                the driver loop once the lock is released.
                """
                name = self._capture_photo(run_id, line, session)
                if name:
                    shot.append(name)

            def inspect_fold() -> float | None:
                """Opener-mounted camera → fold quality percent, or None."""
                score = self._score_fold(run_id, line, session)
                if score is not None:
                    fold_shot.append("fold")
                return score

            session.ensure_garment(garment, texture=custom_tex)
            session.reset_time()
            dt = float(session.model.opt.timestep)
            with session.lock:
                line = session.make_line(
                    speed=speed,
                    garment=garment,
                    repeat=False,
                    log=lambda message: None,
                    skewed=skewed,
                    on_event=pending.append,
                    seed=seed,
                    on_photo=take_photo,
                    on_fold_inspect=inspect_fold,
                )
                if session.follow is not None:
                    session.follow.reset()
                    session.track_camera(line.positions(), 0.0)
            cfg = shirt_config()
            self._log(
                run_id,
                f"cycle started · {cfg.garment} ({cfg.mesh}) · "
                f"{'custom garment (cut-out, both faces)' if custom_tex else cfg.texture} · "
                f"{'placed skewed' if skewed else 'placed square'} · "
                f"machines at {speed:g}x · "
                f"seed {seed} ({'applied to infeed' if run.inputs.get('seedApplied') else 'fixed infeed'}) · "
                f"nq={session.model.nq} · timestep {dt:g}s",
                session=session,
            )

            stage = ""
            last_event = time.monotonic()
            steps = 0
            # Pace against one deadline for the whole cycle, not per step: a
            # step that overruns (a rendered frame) is then made up by the
            # cheap steps after it instead of the cycle drifting late.
            clock = time.perf_counter()

            while True:
                if not self._wait_unpaused(run_id):
                    self._force_quit(run_id, line, session)
                    return

                track = steps % _TRACK_EVERY == 0
                with session.lock:
                    line.step()
                    t = float(session.data.time)
                    stage = line.phase
                    finished = line.finished
                    qpos = np.asarray(session.data.qpos, dtype=np.float64).copy()
                    cloth = line.positions() if (track and session.follow) else None
                steps += 1
                if self._active(run_id) is None:
                    self._force_quit(run_id, line, session)
                    return

                for observation in pending:
                    self._publish(run_id, observation)
                    last_event = time.monotonic()
                pending.clear()
                if shot:
                    shot.clear()
                    self.runtime.mark_photo(run_id)
                if fold_shot:
                    fold_shot.clear()
                    self.runtime.mark_fold_photo(run_id)

                if cloth is not None:
                    session.track_camera(cloth, _TRACK_EVERY * dt)
                recorder.maybe_sample(t, stage, qpos)
                self.runtime.bump_sim_time(run_id, t)

                if finished:
                    break

                if t > _SIM_TIME_CAP_S / speed:
                    self._log(
                        run_id,
                        f"cycle abandoned after {t:.0f}s of simulation in {stage or '?'} "
                        f"(machines at {speed:g}x)",
                        level="error",
                        session=session,
                    )
                    self.runtime.finish_failed(
                        run_id, t, reason=f"line did not keep up at {speed:g}x"
                    )
                    return

                now = time.monotonic()
                if now - last_event > _HEARTBEAT_S:
                    # Keep the console's stall watchdog quiet during a long,
                    # legitimate phase (steam dwell, belt run).
                    self._log(run_id, f"{stage or '?'} in progress · t={t:.1f}s", level="debug", session=session)
                    last_event = time.monotonic()

                leftover = clock + steps * dt - time.perf_counter()
                if leftover > 0:
                    self.runtime.wait_wake(leftover)
                    if self._active(run_id) is None:
                        self._force_quit(run_id, line, session)
                        return
                elif leftover < -1.0:
                    # Far behind (an engine slower than realtime): pace from
                    # here rather than sprinting to catch up.
                    clock = time.perf_counter() - steps * dt

            t = session.sim_time()
            if self._active(run_id) is None:
                self._force_quit(run_id, line, session)
                return
            with session.lock:
                recorder.maybe_sample(t, line.phase, session.data.qpos)
                outcome = line.outcome
            record = self._active(run_id)
            garment = record.garment if record is not None else "tee"
            condition = record.clothCondition if record is not None else None
            ok, reason = grade_line_outcome(outcome, garment, condition)
            mark = garment_result_label(garment, condition)
            if ok:
                self._log(run_id, f"cycle complete · {mark.lower()} · {t:.1f}s of simulation", session=session)
                self.runtime.finish_success(run_id, t)
            else:
                self._log(run_id, f"cycle failed · {reason} · {t:.1f}s of simulation", level="error", session=session)
                self.runtime.finish_failed(run_id, t, reason=reason)
        except Exception as exc:  # noqa: BLE001
            self._log(run_id, f"cycle failed: {exc}", level="error", session=session)
            final = self.runtime.driver_active_run()
            if final and final.id == run_id and final.lifecycle == "running":
                self.runtime.finish_failed(run_id, session.sim_time(), reason=str(exc))
        finally:
            path = recorder.finalize()
            if path:
                self._log(run_id, f"trajectory → {path}", level="debug", session=session)
