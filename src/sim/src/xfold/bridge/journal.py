"""Thread-safe append-only event journal with optional JSONL persistence."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from xfold.bridge.schema import JournalEvent


Subscriber = Callable[[JournalEvent], None]


class Journal:
    """Monotonic ``seq`` log. Subscribers are notified after each append.

    Invariants:
    - ``seq`` starts at 1 and never reuses values.
    - Append never blocks on network I/O (callers must not do I/O in subscribers
      that can stall the producer; SSE fan-out uses queues).
    - State / command events must not be dropped by producers; metric samples
      may be coalesced upstream before append.
    """

    def __init__(self, persist_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._events: list[JournalEvent] = []
        self._seq = 0
        self._subscribers: list[Subscriber] = []
        self._persist_path: Path | None = None
        if persist_dir is not None:
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._persist_path = persist_dir / "events.jsonl"

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def append(self, type: str, *, run_id: str | None = None, batch_id: str | None = None, **payload: Any) -> JournalEvent:
        from datetime import datetime, timezone

        with self._lock:
            self._seq += 1
            raw: dict[str, Any] = {
                "seq": self._seq,
                "tsIso": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "type": type,
                "runId": run_id,
                "batchId": batch_id,
                **payload,
            }
            event = JournalEvent.model_validate(raw)
            self._events.append(event)
            if self._persist_path is not None:
                with self._persist_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event.to_public_dict(), separators=(",", ":")) + "\n")
            subscribers = list(self._subscribers)

        for sub in subscribers:
            sub(event)
        return event

    def since(self, after_seq: int = 0) -> list[JournalEvent]:
        with self._lock:
            return [e for e in self._events if e.seq > after_seq]

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(callback)
                except ValueError:
                    pass

        return unsubscribe
