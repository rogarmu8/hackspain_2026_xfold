"""Append-only trajectory samples (qpos + FSM state) keyed by sim time.

Stored under data/trajectories/{run_id}.npz (gitignored via data/).
Replay seeks nearest sample → SimSession.apply_qpos + render.

Never puts JPEG into the journal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


def trajectories_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pixi.toml").exists() and (parent / "moon.yml").exists():
            path = parent / "data" / "trajectories"
            path.mkdir(parents=True, exist_ok=True)
            return path
    path = here.parents[5] / "data" / "trajectories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def trajectory_path(run_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)
    return trajectories_dir() / f"{safe}.npz"


@dataclass
class TrajectoryRecorder:
    """Sample qpos at ~sample_hz during a live run."""

    run_id: str
    sample_hz: float = 10.0
    _t: list[float] = field(default_factory=list)
    _state: list[str] = field(default_factory=list)
    _qpos: list[np.ndarray] = field(default_factory=list)
    _last_sample_t: float = -1e9
    _path: Path | None = None

    def __post_init__(self) -> None:
        self._path = trajectory_path(self.run_id)

    def maybe_sample(self, t: float, state: str | None, qpos: np.ndarray) -> None:
        interval = 1.0 / max(self.sample_hz, 1.0)
        if t - self._last_sample_t < interval and self._t:
            return
        self._last_sample_t = t
        self._t.append(float(t))
        self._state.append(state or "PICK")
        self._qpos.append(np.asarray(qpos, dtype=np.float64).copy())

    def finalize(self) -> Path | None:
        if not self._t or self._path is None:
            return None
        qpos = np.stack(self._qpos, axis=0)
        np.savez_compressed(
            self._path,
            t=np.asarray(self._t, dtype=np.float64),
            state=np.asarray(self._state),
            qpos=qpos,
            sample_hz=np.asarray([self.sample_hz], dtype=np.float64),
        )
        return self._path


@dataclass
class TrajectoryMeta:
    runId: str
    tMax: float
    sampleHz: float
    hasTrajectory: bool
    frameCount: int
    nq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.runId,
            "tMax": self.tMax,
            "sampleHz": self.sampleHz,
            "hasTrajectory": self.hasTrajectory,
            "frameCount": self.frameCount,
            "nq": self.nq,
        }


def load_trajectory_meta(run_id: str) -> TrajectoryMeta:
    path = trajectory_path(run_id)
    if not path.is_file():
        return TrajectoryMeta(
            runId=run_id,
            tMax=0.0,
            sampleHz=0.0,
            hasTrajectory=False,
            frameCount=0,
        )
    with np.load(path, allow_pickle=False) as z:
        t = np.asarray(z["t"], dtype=np.float64)
        hz = float(np.asarray(z["sample_hz"]).reshape(-1)[0]) if "sample_hz" in z else 10.0
        qpos = z["qpos"]
        return TrajectoryMeta(
            runId=run_id,
            tMax=float(t[-1]) if len(t) else 0.0,
            sampleHz=hz,
            hasTrajectory=True,
            frameCount=int(len(t)),
            nq=int(qpos.shape[1]) if qpos.ndim == 2 else 0,
        )


def nearest_sample(run_id: str, t: float) -> tuple[float, str, np.ndarray] | None:
    path = trajectory_path(run_id)
    if not path.is_file():
        return None
    with np.load(path, allow_pickle=False) as z:
        times = np.asarray(z["t"], dtype=np.float64)
        if times.size == 0:
            return None
        idx = int(np.argmin(np.abs(times - float(t))))
        state_arr = z["state"]
        state = str(state_arr[idx])
        qpos = np.asarray(z["qpos"][idx], dtype=np.float64)
        return float(times[idx]), state, qpos
