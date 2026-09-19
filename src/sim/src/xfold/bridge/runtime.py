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
from xfold.bridge.schema import BridgeCapabilities, CatalogOption, CommandKind, CommandRequest, ProcessDefinition
from xfold.fsm import CYCLE, CellState
from xfold.garments import public_catalog, resolve_garment, resolve_launch

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
    label: str | None = None
    station: str | None = None


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
    shirt_in_bag: bool | None = None
    measurements: dict[str, float] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    operation: dict[str, Any] | None = None
    activities: dict[str, dict[str, Any]] = field(default_factory=dict)
    stages: list[StageProgress] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    paused: bool = False
    cancel_requested: bool = False
    driverLabel: str = "Bridge mock driver"
    hasPhoto: bool = False
    garment: str = "tee"
    clothType: str = "tee"
    clothCondition: str = "good"
    skewed: bool = False

    def telemetry(self) -> dict[str, Any] | None:
        if self.currentState is None:
            return None
        state = self.currentState
        return {
            "t": round(self.t, 3),
            "state": state,
            "cycle": self.cycle,
            "flatness": self.flatness,
            "shirt_in_bag": self.shirt_in_bag,
            "operation": self.operation,
            "activities": list(self.activities.values()),
        }

    def to_detail(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "batchId": self.batchId,
            "lifecycle": self.lifecycle,
            "seed": self.seed,
            "name": self.name,
            "garment": self.garment,
            "clothType": self.clothType,
            "clothCondition": self.clothCondition,
            "skewed": self.skewed,
            "currentState": self.currentState,
            "startedAtIso": self.startedAtIso,
            "finishedAtIso": self.finishedAtIso,
            "failReason": self.failReason,
            "hasPhoto": self.hasPhoto,
            "metrics": {
                "cycleTimeSimS": self.t if self.lifecycle in {"succeeded", "failed", "cancelled"} else None,
                "cycleTimeWallS": (
                    (datetime.fromisoformat(self.finishedAtIso) - datetime.fromisoformat(self.startedAtIso)).total_seconds()
                    if self.finishedAtIso and self.startedAtIso else None
                ),
                "flatnessPre": self.measurements.get("flatnessPreM"),
                "flatnessPost": self.measurements.get("flatnessPostM"),
                "shirtInBag": self.shirt_in_bag,
                "measurements": dict(self.measurements),
            },
            "config": {
                "name": self.name,
                "seed": self.seed,
                "scenario": self.scenario,
                "notes": self.driverLabel,
                "inputs": dict(self.inputs),
                "garment": self.garment,
                "clothType": self.clothType,
                "clothCondition": self.clothCondition,
                "skewed": self.skewed,
            },
            "stages": [
                {
                    "state": s.state,
                    "label": s.label,
                    "station": s.station,
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
        catalog = public_catalog()
        self.capabilities.clothTypes = [CatalogOption(**item) for item in catalog["clothTypes"]]
        self.capabilities.clothConditions = [
            CatalogOption(**item) for item in catalog["clothConditions"]
        ]
        self._lock = threading.RLock()
        self.runs: dict[str, RunRecord] = {}
        self.batches: dict[str, BatchRecord] = {}
        self.active_run_id: str | None = None
        self.active_batch_id: str | None = None
        self._run_counter = 0
        self._batch_counter = 0
        self._seen_commands: dict[str, str] = {}  # clientCommandId -> status
        self._wake = threading.Event()
        # Set by app.py once a driver is chosen; shown as a run's `notes`.
        self.driver_label = "Bridge mock driver"
        self.stage_definitions = tuple({"state": s.value} for s in PRODUCTIVE)
        self.process_scenario: str | None = None
        self.process_config: dict[str, Any] = {}

    def configure_process(self, stages, *, scenario: str, config: dict[str, Any]) -> None:
        with self._lock:
            if self.runs:
                raise ValueError("Process must be configured before launching runs")
            states = [s["state"] for s in stages]
            if not states or len(states) != len(set(states)):
                raise ValueError("Process requires unique phase IDs")
            self.stage_definitions = tuple(dict(s) for s in stages)
            self.process_scenario = scenario
            self.process_config = dict(config)
            self.capabilities.process = ProcessDefinition(
                scenario=scenario, stages=list(self.stage_definitions), seedApplied=config.get("seedApplied")
            )

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
            StageProgress(**s, status="pending", startedAtSimS=None, durationSimS=None)
            for s in self.stage_definitions
        ]

    def _ui_event(self, run: RunRecord, message: str, level: str = "info", **context: Any) -> None:
        run.events.append(
            {
                "id": f"{run.id}-e{len(run.events)+1}",
                "atSimS": run.t,
                "atWallIso": _iso_now(),
                "stage": run.currentState,
                "message": message,
                "level": level,
                **context,
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

    def launch_run(
        self,
        *,
        name: str,
        seed: int,
        scenario: str,
        cloth_type: str = "tee",
        cloth_condition: str = "good",
        cloth_weights: dict[str, float] | None = None,
        condition_weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        cloth_mix = "random" if cloth_type == "random" else "same"
        cond_mix = "random" if cloth_condition == "random" else "same"
        cloth_types = [] if cloth_mix == "random" else [cloth_type]
        conditions = [] if cond_mix == "random" else [cloth_condition]
        pick, cloth, cond = resolve_launch(
            cloth_mix=cloth_mix,
            cloth_types=cloth_types,
            condition_mix=cond_mix,
            conditions=conditions,
            seed=seed,
            index=0,
            cloth_weights=cloth_weights if cloth_mix == "random" else None,
            condition_weights=condition_weights if cond_mix == "random" else None,
        )
        with self._lock:
            if self.active_run_id and self.runs[self.active_run_id].lifecycle in {"running", "paused"}:
                raise ValueError("Ya hay una ejecución activa")
            run = self._create_run(
                name=name or None,
                seed=seed,
                scenario=scenario,
                batch_id=None,
                garment=pick.key,
                cloth_type=cloth,
                cloth_condition=cond,
                skewed=pick.skewed,
                seed_applied=cloth_mix == "random" or cond_mix == "random" or cond in {"notgood", "skewed"},
            )
            self.active_run_id = run.id
            self.active_batch_id = None
            self._start_run_locked(run)
            self.wake_driver()
            return {"ok": True, "id": run.id}

    def launch_batch(
        self,
        *,
        name: str,
        count: int,
        base_seed: int,
        scenario: str,
        cloth_mix: str = "same",
        cloth_types: list[str] | None = None,
        condition_mix: str = "same",
        conditions: list[str] | None = None,
        cloth_weights: dict[str, float] | None = None,
        condition_weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        types = list(cloth_types or [])
        conds = list(conditions or [])
        if cloth_mix == "list" and not types:
            raise ValueError("Selecciona al menos un tipo de prenda")
        if condition_mix == "list" and not conds:
            raise ValueError("Selecciona al menos una condición")
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
                pick, cloth, cond = resolve_launch(
                    cloth_mix=cloth_mix,
                    cloth_types=types,
                    condition_mix=condition_mix,
                    conditions=conds,
                    seed=base_seed + i,
                    index=i,
                    cloth_weights=cloth_weights if cloth_mix == "random" else None,
                    condition_weights=condition_weights if condition_mix == "random" else None,
                )
                run = self._create_run(
                    name=name or None,
                    seed=base_seed + i,
                    scenario=scenario,
                    batch_id=batch_id,
                    garment=pick.key,
                    cloth_type=cloth,
                    cloth_condition=cond,
                    skewed=pick.skewed,
                    seed_applied=cloth_mix != "same" or condition_mix != "same" or cond in {"notgood", "skewed"},
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

    def _create_run(
        self,
        *,
        name: str | None,
        seed: int,
        scenario: str,
        batch_id: str | None,
        garment: str = "tee",
        cloth_type: str = "tee",
        cloth_condition: str = "good",
        skewed: bool = False,
        seed_applied: bool = False,
    ) -> RunRecord:
        item = resolve_garment(garment)
        inputs = {
            **self.process_config,
            "garment": item.key, "mesh": item.mesh, "texture": item.texture,
            "clothType": cloth_type, "clothCondition": cloth_condition,
            "skewed": skewed, "seed": seed, "seedApplied": seed_applied,
        }
        run = RunRecord(
            id=self._next_run_id(),
            batchId=batch_id,
            seed=seed,
            name=name,
            scenario=self.process_scenario or scenario,
            stages=self._fresh_stages(),
            driverLabel=self.driver_label,
            inputs=inputs,
            garment=garment,
            clothType=cloth_type,
            clothCondition=cloth_condition,
            skewed=skewed,
        )
        self.runs[run.id] = run
        return run

    def _start_run_locked(self, run: RunRecord) -> None:
        run.lifecycle = "running"
        run.startedAtIso = _iso_now()
        run.currentState = None
        run.t = 0.0
        run.flatness = None
        run.shirt_in_bag = None
        run.paused = False
        run.cancel_requested = False
        for stage in run.stages:
            stage.status = "pending"
            stage.startedAtSimS = None
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
            stages=[{"state": s.state, "label": s.label, "station": s.station} for s in run.stages],
            inputs=dict(run.inputs),
            driver=run.driverLabel,
            garment=run.garment,
            clothType=run.clothType,
            clothCondition=run.clothCondition,
            skewed=run.skewed,
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

    def emit_state(self, run_id: str, state: CellState | str, t: float) -> None:
        """Record an FSM stage transition (journal + snapshot).

        AGENT (arm/cloth): call this after each productive stage change — see
        docs/INTEGRATION_CONTRACT.md §4 / mock_driver.py. Do not call from FastAPI routes.
        """
        with self._lock:
            run = self.runs.get(run_id)
            if not run or run.lifecycle not in {"running", "paused"}:
                return
            state = str(state)
            target = next((s for s in run.stages if s.state == state), None)
            if target is None:
                raise ValueError(f"Undeclared simulator phase: {state}")
            if run.currentState == state:
                return
            for stage in run.stages:
                if stage.status == "active":
                    stage.status = "completed"
                    if stage.startedAtSimS is not None:
                        stage.durationSimS = round(t - stage.startedAtSimS, 3)
            run.currentState = state
            run.operation = None
            run.t = t
            target.status = "active"
            target.startedAtSimS = t
            self._ui_event(run, f"Fase {target.label or state}", source="fsm")
            self.journal.append(
                "state_changed", run_id=run.id, batch_id=run.batchId,
                state=state, label=target.label, station=target.station,
                t=round(t, 3), cycle=run.cycle,
            )

    def emit_metrics(self, run_id: str, t: float, measurements: dict[str, float]) -> None:
        import math

        with self._lock:
            run = self.runs.get(run_id)
            if not run or run.lifecycle not in {"running", "paused"}:
                return
            if not all(math.isfinite(value) for value in measurements.values()):
                raise ValueError("Simulator measurements must be finite")
            run.measurements.update(measurements)
            run.flatness = run.measurements.get("flatnessPostM", run.measurements.get("flatnessPreM"))
            run.t = t
            self.journal.append(
                "metric_sample", run_id=run.id, batch_id=run.batchId,
                t=round(t, 3), flatness=run.flatness, shirt_in_bag=run.shirt_in_bag,
                cycle=run.cycle, state=run.currentState, measurements=dict(measurements),
            )

    def emit_log(
        self,
        run_id: str | None,
        message: str,
        level: str = "info",
        source: str = "sim",
        t: float | None = None,
        *,
        operation: str | None = None,
        station: str | None = None,
        parallel: bool = False,
    ) -> None:
        """Append a free-form simulator log line (journal ``log`` + run events).

        AGENT (arm/cloth/press): route your driver's ``print``/``log`` here so the
        dashboard console sees it live — e.g. ``Line(log=lambda m: runtime.emit_log(run_id, m, source="line"))``.
        Never log per-step; keep it to stage changes, warnings and failures.
        """
        with self._lock:
            run = self.runs.get(run_id) if run_id else None
            if run_id is not None and run is None:
                return
            context = {"source": source, "operation": operation, "station": station, "parallel": parallel}
            if run is not None:
                if t is not None and run.lifecycle in {"running", "paused"}:
                    run.t = float(t)
                if operation and run.lifecycle in {"running", "paused"}:
                    activity = {"id": operation, "station": station, "message": message, "t": run.t, "parallel": parallel}
                    if parallel:
                        run.activities[station or source] = activity
                    else:
                        run.operation = activity
                self._ui_event(run, message, level, **context)
            at = float(t) if t is not None else (run.t if run else None)
            self.journal.append(
                "log",
                run_id=run.id if run else None,
                batch_id=run.batchId if run else None,
                level=level,
                message=message,
                stage=run.currentState if run else None,
                t=round(at, 3) if at is not None else None,
                **context,
            )

    def mark_photo(self, run_id: str) -> None:
        """The QC shot for this run is on disk; the UI may ask for it."""
        with self._lock:
            run = self.runs.get(run_id)
            if run:
                run.hasPhoto = True

    def bump_sim_time(self, run_id: str, t: float) -> None:
        """Update live telemetry clock without a journal event (substep ticks)."""
        with self._lock:
            run = self.runs.get(run_id)
            if not run or run.lifecycle not in {"running", "paused"}:
                return
            run.t = float(t)

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

    def finish_failed(self, run_id: str, t: float, reason: str | None = None) -> None:
        with self._lock:
            run = self.runs.get(run_id)
            if not run:
                return
            run.t = t
            for stage in run.stages:
                if stage.status == "active":
                    stage.status = "failed"
                    if stage.startedAtSimS is not None:
                        stage.durationSimS = round(t - stage.startedAtSimS, 3)
            self._finish_run_locked(run, "failed", reason or "failed")

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
