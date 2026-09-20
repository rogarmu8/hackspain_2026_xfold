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
    "log",
    "run_deleted",
]

LogLevel = Literal["debug", "info", "warning", "error"]

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

CellState = Literal["PICK", "ORIENT", "SPREAD", "PRESS", "FOLD", "CHUTE", "BAG", "RESET"]
PhaseId = str


class PhaseDefinition(BaseModel):
    state: PhaseId
    label: str | None = None
    station: str | None = None


class ProcessDefinition(BaseModel):
    scenario: str
    stages: list[PhaseDefinition]
    seedApplied: bool | None = None


class SimOperation(BaseModel):
    id: str
    station: str | None
    message: str
    t: float
    parallel: bool


BRIDGE_VERSION = "0.2.0"


class CatalogOption(BaseModel):
    key: str
    label: str
    outlineUv: list[list[float]] = Field(default_factory=list)


class CustomDesignPayload(BaseModel):
    """Operator photo, base64. Never written to the journal."""

    mime: str = "image/png"
    data: str = ""


class BridgeCapabilities(BaseModel):
    process: ProcessDefinition | None = None
    liveTelemetry: bool = True
    viewportStream: bool = False
    recordingSeek: bool = False
    viewportVideo: bool = False
    # The run's video can be watched live (HLS a few segments behind). False
    # for an engine slower than realtime: the live view stays on JPEG frames
    # and the video is for replay.
    liveVideo: bool = True
    # Which physics engine steps the line: "mujoco" or "isaac".
    engine: str = "mujoco"
    # Runs that can simulate at once; the rest queue.
    maxConcurrentRuns: int = 1
    # Machinery speed range the launch form may offer.
    speedRange: tuple[float, float] = (1.0, 20.0)
    startRun: bool = True
    startBatch: bool = True
    deleteRun: bool = True
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
    clothTypes: list[CatalogOption] = Field(default_factory=list)
    clothConditions: list[CatalogOption] = Field(default_factory=list)


class CommandRequest(BaseModel):
    clientCommandId: str
    kind: CommandKind
    runId: str | None = None
    batchId: str | None = None


class LaunchRunRequest(BaseModel):
    name: str = ""
    seed: int = 0
    scenario: str = "mock"
    clothType: str = "tee"
    clothCondition: str = "good"
    clothTypeWeights: dict[str, float] = Field(default_factory=dict)
    clothConditionWeights: dict[str, float] = Field(default_factory=dict)
    customDesign: CustomDesignPayload | None = None
    # Machinery speed: 1 is nominal, 20 is twenty times the belts, flaps and
    # peel. Fast enough and the garment does not keep up and the run fails.
    speed: float = Field(default=1.0, ge=1.0, le=20.0)


class LaunchBatchRequest(BaseModel):
    name: str = ""
    count: int = Field(ge=1)
    baseSeed: int = 0
    seedStrategy: Literal["sequential"] = "sequential"
    scenario: str = "mock"
    clothMix: Literal["same", "random", "list"] = "same"
    clothTypes: list[str] = Field(default_factory=lambda: ["tee"])
    conditionMix: Literal["same", "random", "list"] = "same"
    conditions: list[str] = Field(default_factory=lambda: ["good"])
    clothTypeWeights: dict[str, float] = Field(default_factory=dict)
    clothConditionWeights: dict[str, float] = Field(default_factory=dict)
    customDesign: CustomDesignPayload | None = None
    speed: float = Field(default=1.0, ge=1.0, le=20.0)


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
