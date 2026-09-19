"""Background mock FSM that feeds the runtime journal without touching HTTP.

Integration contract: docs/INTEGRATION_CONTRACT.md §4 / §4b
AGENTS.md → “For agents on other tracks (arm / cloth)”

=============================================================================
AGENT NOTE — ARM / FSM TRACK
-----------------------------------------------------------------------------
This file is the **reference fallback Driver** (wall-clock stages, no physics).
When MuJoCo + press_cell load, the bridge uses ``PressBridgeDriver`` instead.

  1. Keep calling the same Runtime API — do NOT invent a new bus.
       runtime.emit_state(run_id, CellState.<STAGE>, t=float(data.time))
       runtime.emit_log(run_id, "platen closed", level="info", source="press", t=float(data.time))
       runtime.finish_success(run_id, t=float(data.time))
     ``emit_log`` replaces ``print`` — it shows up live in the dashboard console
     (e.g. ``Line(log=lambda m: runtime.emit_log(run_id, m, source="line"))``).
     Log stage changes / warnings / failures, never per physics step.
  2. Respect pause/cancel via runtime.driver_active_run().
  3. Prefer extending ``press_driver.py`` for real cycles; keep MockDriver as
     offline / no-MuJoCo fallback.
  4. Do not import FastAPI here. Do not block mj_step on network I/O.

Cloth teammates: emit stages from your controller; share SimSession for 3D.
=============================================================================
"""

from __future__ import annotations

import threading
import time

from xfold.bridge.runtime import Runtime
from xfold.fsm import CYCLE, CellState

HOLD_S = 0.35


class MockDriver:
    """Walks PICK→BAG for the active run; respects pause / cancel via runtime.

    Stand-in until the arm/cloth tracks drive the same emit_* API.
    """

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="xfold-mock-driver", daemon=True)
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

            run_id = run.id
            # Skip PICK if already emitted at start.
            states = list(CYCLE)
            start_idx = 0
            if run.currentState == CellState.PICK.value and run.t == 0.0:
                start_idx = 1
                # Hold on PICK briefly so the UI can show it.
                if self._hold_or_abort(run_id, HOLD_S):
                    continue

            t = max(run.t, 0.0)
            aborted = False
            for state in states[start_idx:]:
                current = self.runtime.driver_active_run()
                if current is None or current.id != run_id:
                    aborted = True
                    break
                if current.cancel_requested or current.lifecycle == "cancelled":
                    aborted = True
                    break
                while True:
                    current = self.runtime.driver_active_run()
                    if current is None or current.id != run_id:
                        aborted = True
                        break
                    if current.lifecycle == "cancelled":
                        aborted = True
                        break
                    if current.paused or current.lifecycle == "paused":
                        self.runtime.wait_wake(0.2)
                        continue
                    break
                if aborted:
                    break

                t += HOLD_S
                self.runtime.emit_state(run_id, state, t)
                if self._hold_or_abort(run_id, HOLD_S):
                    aborted = True
                    break

            if aborted:
                continue
            final = self.runtime.driver_active_run()
            if final and final.id == run_id and final.lifecycle == "running":
                self.runtime.finish_success(run_id, t)

    def _hold_or_abort(self, run_id: str, seconds: float) -> bool:
        """Sleep in slices; return True if the run is no longer active."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stop.is_set():
                return True
            current = self.runtime.driver_active_run()
            if current is None or current.id != run_id:
                return True
            if current.lifecycle == "cancelled":
                return True
            if current.paused or current.lifecycle == "paused":
                self.runtime.wait_wake(0.15)
                continue
            remaining = end - time.monotonic()
            self.runtime.wait_wake(min(0.15, max(0.0, remaining)))
        return False
