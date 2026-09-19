"""Pydantic models for the bridge HTTP API.

Keep in sync with ``@xfold/protocol`` (packages/protocol/src/index.ts).
Binding contract: docs/INTEGRATION_CONTRACT.md
See docs/BRIDGE.md for the event catalogue and invariants.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CommandKind = Literal[
    "pause_run",
    "resume_run",
    "cancel_run",
    "pause_batch",
    "resume_batch",
    "cancel_batch",
]

JournalEventType = Literal[
    "run_started",
    "state_changed",
    "metric_sample",
    "run_finished",
    "command_accepted",
    "command_rejected",
    "command_applied",
    "batch_updated",
]

RunLifecycle = Literal[
    "queued",
    "running",
    "paused",
    "succeeded",
    "failed",
    "cancelled",
]

BatchLifecycle = Literal[
    "queued",
    "running",
    "paused",
    "succeeded",
    "failed",
    "cancelled",
    "partial",
]

CellState = Literal["PICK", "SPREAD", "PRESS", "FOLD", "CHUTE", "BAG", "RESET"]

BRIDGE_VERSION = "0.1.0"


class BridgeCapabilities(BaseModel):
    liveTelemetry: bool = True
    viewportStream: bool = False
    recordingSeek: bool = False
    startRun: bool = True
    startBatch: bool = True
    commands: dict[str, bool] = Field(
        default_factory=lambda: {
            "pause_run": True,
            "resume_run": True,
            "cancel_run": True,
            "pause_batch": True,
            "resume_batch": True,
            "cancel_batch": True,
        }
    )


class CommandRequest(BaseModel):
    clientCommandId: str
    kind: CommandKind
    runId: str | None = None
    batchId: str | None = None


class LaunchRunRequest(BaseModel):
    name: str = ""
    seed: int = 0
    scenario: str = "mock"


class LaunchBatchRequest(BaseModel):
    name: str = ""
    count: int = Field(ge=1, le=100)
    baseSeed: int = 0
    seedStrategy: Literal["sequential"] = "sequential"
    scenario: str = "mock"


class HealthResponse(BaseModel):
    ok: Literal[True] = True
    version: str = BRIDGE_VERSION


class CommandResponse(BaseModel):
    clientCommandId: str
    status: Literal["accepted", "rejected", "duplicate"]
    reason: str | None = None


class JournalEvent(BaseModel):
    """Wire format for one journal fact (SSE ``data`` and JSONL lines)."""

    seq: int
    tsIso: str
    type: JournalEventType
    runId: str | None = None
    batchId: str | None = None
    # Payload fields vary by type; extra keys are allowed for forward compat.
    model_config = {"extra": "allow"}

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=False)
