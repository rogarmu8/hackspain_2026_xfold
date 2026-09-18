"""Authoritative run/batch state; emits journal facts; applies commands.

The physics / mock driver must only call ``emit_*`` / queue helpers — never HTTP.
Binding contract: docs/INTEGRATION_CONTRACT.md
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from xfold.bridge.journal import Journal
from xfold.bridge.schema import BridgeCapabilities, CommandKind, CommandRequest
from xfold.fsm import CYCLE, CellState

# Productive stages for the control-room stepper (matches @xfold/protocol).
PRODUCTIVE = tuple(CYCLE)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class StageProgress:
    state: str
    status: Literal["completed", "active", "pending", "failed", "skipped"]
    startedAtSimS: float | None
    durationSimS: float | None


@dataclass
class RunRecord:
    id: str
    batchId: str | None
    seed: int
    name: str | None
    scenario: str
    lifecycle: str = "queued"
    currentState: str | None = None
    startedAtIso: str | None = None
    finishedAtIso: str | None = None
    failReason: str | None = None
    t: float = 0.0
    cycle: int = 1
    flatness: float | None = None
    shirt_in_bag: bool = False
    stages: list[StageProgress] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    paused: bool = False
    cancel_requested: bool = False

    def telemetry(self) -> dict[str, Any] | None:
        if self.currentState is None and self.lifecycle == "queued":
            return None
        state = self.currentState or "PICK"
        return {
            "t": round(self.t, 3),
            "state": state,
            "cycle": self.cycle,
            "flatness": self.flatness,
            "shirt_in_bag": self.shirt_in_bag,
        }

    def to_detail(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "batchId": self.batchId,
            "lifecycle": self.lifecycle,
            "seed": self.seed,
            "name": self.name,
            "currentState": self.currentState,
            "startedAtIso": self.startedAtIso,
            "finishedAtIso": self.finishedAtIso,
            "failReason": self.failReason,
            "metrics": {
                "cycleTimeSimS": self.t if self.lifecycle in {"succeeded", "failed", "cancelled"} else None,
                "cycleTimeWallS": None,
                "flatnessPre": None,
                "flatnessPost": self.flatness,
                "shirtInBag": self.shirt_in_bag if self.lifecycle == "succeeded" else None,
            },
            "config": {
                "name": self.name,
                "seed": self.seed,
                "scenario": self.scenario,
                "notes": "Bridge mock driver" if self.scenario == "mock" else None,
            },
            "stages": [
                {
                    "state": s.state,
                    "status": s.status,
                    "startedAtSimS": s.startedAtSimS,
                    "durationSimS": s.durationSimS,
                }
                for s in self.stages
            ],
            "events": list(self.events),
            "telemetry": self.telemetry(),
        }


@dataclass
class BatchRecord:
    id: str
    name: str
    lifecycle: str = "queued"
    total: int = 0
    finished: int = 0
    succeeded: int = 0
    failed: int = 0
    pending: int = 0
    activeRunId: str | None = None
    seedStrategy: str = "sequential"
    baseSeed: int = 0
    run_ids: list[str] = field(default_factory=list)
    paused: bool = False
    cancel_requested: bool = False
    startedAtIso: str | None = None

    def to_summary(self, runs: dict[str, RunRecord]) -> dict[str, Any]:
        preview = []
        for rid in self.run_ids:
            run = runs.get(rid)
            if not run or run.lifecycle != "queued":
                continue
            if len(preview) >= 3:
                break
            preview.append(
                {
                    "runId": run.id,
                    "seed": run.seed,
                    "name": run.name,
                    "lifecycle": "queued",
                }
            )
        queued = [r for r in self.run_ids if runs.get(r) and runs[r].lifecycle == "queued"]
        return {
            "id": self.id,
            "name": self.name,
            "lifecycle": self.lifecycle,
            "total": self.total,
            "finished": self.finished,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "pending": len(queued),
            "activeRunId": self.activeRunId,
            "queuePreview": preview,
            "queueTotal": len(queued),
            "seedStrategy": self.seedStrategy,
            "baseSeed": self.baseSeed,
        }


class Runtime:
    """Single-process authority for runs, batches, and command idempotency."""

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.capabilities = BridgeCapabilities()
        self._lock = threading.RLock()
        self.runs: dict[str, RunRecord] = {}
        self.batches: dict[str, BatchRecord] = {}
        self.active_run_id: str | None = None
        self.active_batch_id: str | None = None
        self._run_counter = 0
        self._batch_counter = 0
        self._seen_commands: dict[str, str] = {}  # clientCommandId -> status
        self._wake = threading.Event()

    def wake_driver(self) -> None:
        self._wake.set()

    def wait_wake(self, timeout: float) -> bool:
        triggered = self._wake.wait(timeout)
        if triggered:
            self._wake.clear()
        return triggered

    def _next_run_id(self) -> str:
        self._run_counter += 1
        return f"RUN-{self._run_counter:03d}"

    def _next_batch_id(self) -> str:
        self._batch_counter += 1
        return f"B-{self._batch_counter:03d}"

    def _fresh_stages(self) -> list[StageProgress]:
        return [
            StageProgress(state=s.value, status="pending", startedAtSimS=None, durationSimS=None)
            for s in PRODUCTIVE
        ]

    def _ui_event(self, run: RunRecord, message: str, level: str = "info") -> None:
        run.events.append(
            {
                "id": f"{run.id}-e{len(run.events)+1}",
                "atSimS": run.t,
                "atWallIso": _iso_now(),
                "stage": run.currentState,
                "message": message,
                "level": level,
            }
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active_run = self.runs.get(self.active_run_id) if self.active_run_id else None
            active_batch = self.batches.get(self.active_batch_id) if self.active_batch_id else None
            return {
                "provenance": "live",
                "connection": "connected",
                "lastUpdatedIso": _iso_now(),
                "capabilities": self.capabilities.model_dump(),
                "activeRun": active_run.to_detail() if active_run else None,
                "activeBatch": active_batch.to_summary(self.runs) if active_batch else None,
                "incident": None,
                "journalSeq": self.journal.last_seq,
            }

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [r.to_detail() for r in sorted(self.runs.values(), key=lambda x: x.id, reverse=True)]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self.runs.get(run_id)
            return run.to_detail() if run else None

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._lock:
            batch = self.batches.get(batch_id)
            return batch.to_summary(self.runs) if batch else None

    def list_experiments(self) -> list[dict[str, Any]]:
        with self._lock:
            items: list[dict[str, Any]] = []
            for batch in self.batches.values():
                items.append(
                    {
                        "kind": "batch",
                        "id": batch.id,
                        "title": batch.name,
                        "lifecycle": batch.lifecycle,
                        "total": batch.total,
                        "finished": batch.finished,
                        "succeeded": batch.succeeded,
                        "failed": batch.failed,
                        "startedAtIso": batch.startedAtIso,
                    }
                )
            for run in self.runs.values():
                if run.batchId:
                    continue
                items.append(
                    {
                        "kind": "run",
                        "id": run.id,
                        "title": run.name or f"Semilla {run.seed}",
                        "lifecycle": run.lifecycle,
                        "seed": run.seed,
                        "startedAtIso": run.startedAtIso,
                        "batchId": None,
                    }
                )
            items.sort(key=lambda x: x.get("startedAtIso") or "", reverse=True)
            return items

    def launch_run(self, *, name: str, seed: int, scenario: str) -> dict[str, Any]:
        with self._lock:
            if self.active_run_id and self.runs[self.active_run_id].lifecycle in {"running", "paused"}:
                raise ValueError("Ya hay una ejecución activa")
            run = self._create_run(name=name or None, seed=seed, scenario=scenario, batch_id=None)
            self.active_run_id = run.id
            self.active_batch_id = None
            self._start_run_locked(run)
            self.wake_driver()
            return {"ok": True, "id": run.id}

    def launch_batch(self, *, name: str, count: int, base_seed: int, scenario: str) -> dict[str, Any]:
        with self._lock:
            if self.active_run_id and self.runs[self.active_run_id].lifecycle in {"running", "paused"}:
                raise ValueError("Ya hay una ejecución activa")
            batch_id = self._next_batch_id()
            batch = BatchRecord(
                id=batch_id,
                name=name or f"Batch ×{count}",
                lifecycle="running",
                total=count,
                pending=count,
                seedStrategy="sequential",
                baseSeed=base_seed,
                startedAtIso=_iso_now(),
            )
            self.batches[batch_id] = batch
            self.active_batch_id = batch_id
            for i in range(count):
                run = self._create_run(
                    name=name or None,
                    seed=base_seed + i,
                    scenario=scenario,
                    batch_id=batch_id,
                )
                batch.run_ids.append(run.id)
            first = self.runs[batch.run_ids[0]]
            batch.activeRunId = first.id
            batch.pending = count - 1
            self.active_run_id = first.id
            self._start_run_locked(first)
            self._emit_batch_updated(batch)
            self.wake_driver()
            return {"ok": True, "id": batch_id}

    def _create_run(self, *, name: str | None, seed: int, scenario: str, batch_id: str | None) -> RunRecord:
        run = RunRecord(
            id=self._next_run_id(),
            batchId=batch_id,
            seed=seed,
            name=name,
            scenario=scenario,
            stages=self._fresh_stages(),
        )
        self.runs[run.id] = run
        return run

    def _start_run_locked(self, run: RunRecord) -> None:
        run.lifecycle = "running"
        run.startedAtIso = _iso_now()
        run.currentState = CellState.PICK.value
        run.t = 0.0
        run.flatness = None
        run.shirt_in_bag = False
        run.paused = False
        run.cancel_requested = False
        for stage in run.stages:
            stage.status = "active" if stage.state == CellState.PICK.value else "pending"
            stage.startedAtSimS = 0.0 if stage.state == CellState.PICK.value else None
            stage.durationSimS = None
        self._ui_event(run, "Ejecución iniciada en el bridge")
        self.journal.append(
            "run_started",
            run_id=run.id,
            batch_id=run.batchId,
            seed=run.seed,
            name=run.name,
            scenario=run.scenario,
            cycle=run.cycle,
        )
        self.journal.append(
            "state_changed",
            run_id=run.id,
            batch_id=run.batchId,
            state=CellState.PICK.value,
            t=0.0,
            cycle=run.cycle,
        )

    def handle_command(self, req: CommandRequest) -> dict[str, Any]:
        with self._lock:
            prior = self._seen_commands.get(req.clientCommandId)
            if prior is not None:
                return {
                    "clientCommandId": req.clientCommandId,
                    "status": "duplicate",
                    "reason": f"already {prior}",
                }

            allowed = self.capabilities.commands.get(req.kind, False)
            if not allowed:
                self._seen_commands[req.clientCommandId] = "rejected"
                self.journal.append(
                    "command_rejected",
                    run_id=req.runId,
                    batch_id=req.batchId,
                    clientCommandId=req.clientCommandId,
                    kind=req.kind,
                    reason="Comando no soportado",
                )
                return {
                    "clientCommandId": req.clientCommandId,
                    "status": "rejected",
                    "reason": "Comando no soportado",
                }

            reason = self._validate_command(req)
            if reason:
                self._seen_commands[req.clientCommandId] = "rejected"
                self.journal.append(
                    "command_rejected",
                    run_id=req.runId or self.active_run_id,
                    batch_id=req.batchId or self.active_batch_id,
                    clientCommandId=req.clientCommandId,
                    kind=req.kind,
                    reason=reason,
                )
                return {
                    "clientCommandId": req.clientCommandId,
                    "status": "rejected",
                    "reason": reason,
                }

            self._seen_commands[req.clientCommandId] = "accepted"
            run_id = req.runId or self.active_run_id
            batch_id = req.batchId or self.active_batch_id
            self.journal.append(
                "command_accepted",
                run_id=run_id,
                batch_id=batch_id,
                clientCommandId=req.clientCommandId,
                kind=req.kind,
                reason=None,
            )
            self._apply_command_locked(req.kind, run_id, batch_id)
            self._seen_commands[req.clientCommandId] = "applied"
            self.journal.append(
                "command_applied",
                run_id=run_id,
                batch_id=batch_id,
                clientCommandId=req.clientCommandId,
                kind=req.kind,
                reason=None,
            )
            self.wake_driver()
            return {
                "clientCommandId": req.clientCommandId,
                "status": "accepted",
                "reason": None,
            }

    def _validate_command(self, req: CommandRequest) -> str | None:
        kind: CommandKind = req.kind
        if kind.endswith("_run"):
            run_id = req.runId or self.active_run_id
            run = self.runs.get(run_id) if run_id else None
            if not run:
                return "No hay ejecución objetivo"
            if kind == "pause_run" and run.lifecycle != "running":
                return "La ejecución no está en running"
            if kind == "resume_run" and run.lifecycle != "paused":
                return "La ejecución no está en paused"
            if kind == "cancel_run" and run.lifecycle not in {"running", "paused", "queued"}:
                return "La ejecución no se puede cancelar"
        else:
            batch_id = req.batchId or self.active_batch_id
            batch = self.batches.get(batch_id) if batch_id else None
            if not batch:
                return "No hay batch objetivo"
            if kind == "pause_batch" and batch.lifecycle != "running":
                return "El batch no está en running"
            if kind == "resume_batch" and batch.lifecycle != "paused":
                return "El batch no está en paused"
            if kind == "cancel_batch" and batch.lifecycle not in {"running", "paused", "queued"}:
                return "El batch no se puede cancelar"
        return None

    def _apply_command_locked(self, kind: CommandKind, run_id: str | None, batch_id: str | None) -> None:
        if kind == "pause_run" and run_id and run_id in self.runs:
            run = self.runs[run_id]
            run.lifecycle = "paused"
            run.paused = True
            self._ui_event(run, "Pausa aplicada")
        elif kind == "resume_run" and run_id and run_id in self.runs:
            run = self.runs[run_id]
            run.lifecycle = "running"
            run.paused = False
            self._ui_event(run, "Reanudación aplicada")
        elif kind == "cancel_run" and run_id and run_id in self.runs:
            self._finish_run_locked(self.runs[run_id], "cancelled", "Cancelada por el operador")
        elif kind == "pause_batch" and batch_id and batch_id in self.batches:
            batch = self.batches[batch_id]
            batch.lifecycle = "paused"
            batch.paused = True
            if batch.activeRunId and batch.activeRunId in self.runs:
                active = self.runs[batch.activeRunId]
                active.lifecycle = "paused"
                active.paused = True
            self._emit_batch_updated(batch)
        elif kind == "resume_batch" and batch_id and batch_id in self.batches:
            batch = self.batches[batch_id]
            batch.lifecycle = "running"
            batch.paused = False
            if batch.activeRunId and batch.activeRunId in self.runs:
                active = self.runs[batch.activeRunId]
                if active.lifecycle == "paused":
                    active.lifecycle = "running"
                    active.paused = False
            self._emit_batch_updated(batch)
        elif kind == "cancel_batch" and batch_id and batch_id in self.batches:
            batch = self.batches[batch_id]
            batch.cancel_requested = True
            batch.lifecycle = "cancelled"
            for rid in batch.run_ids:
                run = self.runs[rid]
                if run.lifecycle in {"queued", "running", "paused"}:
                    self._finish_run_locked(run, "cancelled", "Batch cancelado", emit_batch=False)
            batch.activeRunId = None
            batch.pending = 0
            if self.active_batch_id == batch_id:
                self.active_batch_id = None
                self.active_run_id = None
            self._emit_batch_updated(batch)

    # --- facts from the mock / physics driver ---

    def driver_active_run(self) -> RunRecord | None:
        with self._lock:
            if not self.active_run_id:
                return None
            run = self.runs.get(self.active_run_id)
            if not run or run.lifecycle not in {"running", "paused"}:
                return None
            return run

    def emit_state(self, run_id: str, state: CellState, t: float) -> None:
        with self._lock:
            run = self.runs.get(run_id)
            if not run or run.lifecycle not in {"running", "paused"}:
                return
            prev = run.currentState
            if prev and prev != state.value:
                for stage in run.stages:
                    if stage.state == prev and stage.status == "active":
                        stage.status = "completed"
                        if stage.startedAtSimS is not None:
                            stage.durationSimS = round(t - stage.startedAtSimS, 3)
            run.currentState = state.value
            run.t = t
            for stage in run.stages:
                if stage.state == state.value:
                    stage.status = "active"
                    stage.startedAtSimS = t
            flatness = 0.002 if state in {CellState.FOLD, CellState.CHUTE, CellState.BAG} else None
            run.flatness = flatness
            run.shirt_in_bag = state is CellState.BAG
            self._ui_event(run, f"Fase {state.value}")
            self.journal.append(
                "state_changed",
                run_id=run.id,
                batch_id=run.batchId,
                state=state.value,
                t=round(t, 3),
                cycle=run.cycle,
            )
            self.journal.append(
                "metric_sample",
                run_id=run.id,
                batch_id=run.batchId,
                t=round(t, 3),
                flatness=flatness,
                shirt_in_bag=run.shirt_in_bag,
                cycle=run.cycle,
                state=state.value,
            )

    def finish_success(self, run_id: str, t: float) -> None:
        with self._lock:
            run = self.runs.get(run_id)
            if not run:
                return
            run.t = t
            for stage in run.stages:
                if stage.status == "active":
                    stage.status = "completed"
                    if stage.startedAtSimS is not None:
                        stage.durationSimS = round(t - stage.startedAtSimS, 3)
            self._finish_run_locked(run, "succeeded", None)

    def _finish_run_locked(
        self,
        run: RunRecord,
        lifecycle: str,
        reason: str | None,
        *,
        emit_batch: bool = True,
    ) -> None:
        if run.lifecycle in {"succeeded", "failed", "cancelled"}:
            return
        run.lifecycle = lifecycle
        run.finishedAtIso = _iso_now()
        run.failReason = reason
        run.paused = False
        self._ui_event(run, reason or f"Ejecución {lifecycle}", "warning" if lifecycle != "succeeded" else "info")
        self.journal.append(
            "run_finished",
            run_id=run.id,
            batch_id=run.batchId,
            lifecycle=lifecycle,
            reason=reason,
            t=round(run.t, 3),
        )
        if self.active_run_id == run.id:
            self.active_run_id = None

        if run.batchId and run.batchId in self.batches and emit_batch:
            batch = self.batches[run.batchId]
            batch.finished += 1
            if lifecycle == "succeeded":
                batch.succeeded += 1
            elif lifecycle == "failed":
                batch.failed += 1
            # cancelled counts as finished but not success/fail rate denominator in UI docs
            next_queued = next(
                (self.runs[rid] for rid in batch.run_ids if self.runs[rid].lifecycle == "queued"),
                None,
            )
            if batch.cancel_requested or batch.lifecycle == "cancelled":
                batch.activeRunId = None
                batch.pending = 0
            elif next_queued and not batch.paused:
                batch.activeRunId = next_queued.id
                self.active_run_id = next_queued.id
                self._start_run_locked(next_queued)
            else:
                batch.activeRunId = None
                if batch.finished >= batch.total:
                    if batch.failed and batch.succeeded:
                        batch.lifecycle = "partial"
                    elif batch.failed:
                        batch.lifecycle = "failed"
                    else:
                        batch.lifecycle = "succeeded"
                    if self.active_batch_id == batch.id:
                        self.active_batch_id = None
            batch.pending = sum(1 for rid in batch.run_ids if self.runs[rid].lifecycle == "queued")
            self._emit_batch_updated(batch)

    def _emit_batch_updated(self, batch: BatchRecord) -> None:
        self.journal.append(
            "batch_updated",
            run_id=batch.activeRunId,
            batch_id=batch.id,
            lifecycle=batch.lifecycle,
            finished=batch.finished,
            succeeded=batch.succeeded,
            failed=batch.failed,
            pending=batch.pending,
            activeRunId=batch.activeRunId,
        )
