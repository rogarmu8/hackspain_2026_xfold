"""Durable experiment catalogue in SQLite.

One experiment = one bridge run (a single cycle). Batches are listed beside
them for the Experimentos UI. Video and QC photos stay on disk; this store
only keeps metadata, the run detail JSON, and journal events so a restarted
bridge (especially the Isaac box) can still answer ``GET /experiments`` and
``GET /runs/{id}``.

Never puts pixels or cloth verts in the DB — same rule as the journal.
Writes are short SQLite transactions under a lock; callers must not invoke
them from inside ``mj_step``.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
  id TEXT PRIMARY KEY,
  batch_id TEXT,
  title TEXT,
  lifecycle TEXT NOT NULL,
  seed INTEGER,
  name TEXT,
  scenario TEXT,
  engine TEXT,
  garment TEXT,
  cloth_type TEXT,
  cloth_condition TEXT,
  skewed INTEGER NOT NULL DEFAULT 0,
  custom_design INTEGER NOT NULL DEFAULT 0,
  driver TEXT,
  fail_reason TEXT,
  started_at_iso TEXT,
  finished_at_iso TEXT,
  t_sim REAL,
  cycle_time_wall_s REAL,
  has_photo INTEGER NOT NULL DEFAULT 0,
  has_video INTEGER NOT NULL DEFAULT 0,
  photo_path TEXT,
  video_dir TEXT,
  detail_json TEXT NOT NULL,
  updated_at_iso TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS experiments_started
  ON experiments (started_at_iso DESC);

CREATE TABLE IF NOT EXISTS batches (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  lifecycle TEXT NOT NULL,
  total INTEGER NOT NULL DEFAULT 0,
  finished INTEGER NOT NULL DEFAULT 0,
  succeeded INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  started_at_iso TEXT,
  summary_json TEXT NOT NULL,
  updated_at_iso TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS batches_started
  ON batches (started_at_iso DESC);

CREATE TABLE IF NOT EXISTS journal_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seq INTEGER NOT NULL,
  run_id TEXT,
  batch_id TEXT,
  type TEXT NOT NULL,
  ts_iso TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS journal_events_run
  ON journal_events (run_id, seq);
"""

_RUN_ID = re.compile(r"^RUN-(\d+)$")
_BATCH_ID = re.compile(r"^B-(\d+)$")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _repo_data_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pixi.toml").exists() and (parent / "moon.yml").exists():
            path = parent / "data"
            path.mkdir(parents=True, exist_ok=True)
            return path
    path = here.parents[5] / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> Path:
    return _repo_data_dir() / "experiments.sqlite"


def _rel_under_data(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        data = _repo_data_dir()
        return str(path.resolve().relative_to(data.resolve()))
    except ValueError:
        return str(path)


class ExperimentStore:
    """SQLite-backed catalogue of finished and in-flight experiments."""

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            path = default_db_path()
        self.path = Path(path) if path != ":memory:" else Path(":memory:")
        self._memory = path == ":memory:"
        self._lock = threading.RLock()
        if not self._memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            ":memory:" if self._memory else str(self.path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we open transactions explicitly
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def max_run_number(self) -> int:
        with self._lock:
            rows = self._conn.execute("SELECT id FROM experiments").fetchall()
        n = 0
        for row in rows:
            m = _RUN_ID.match(str(row["id"]))
            if m:
                n = max(n, int(m.group(1)))
        return n

    def max_batch_number(self) -> int:
        with self._lock:
            rows = self._conn.execute("SELECT id FROM batches").fetchall()
        n = 0
        for row in rows:
            m = _BATCH_ID.match(str(row["id"]))
            if m:
                n = max(n, int(m.group(1)))
        return n

    def upsert_run(
        self,
        detail: dict[str, Any],
        *,
        engine: str | None = None,
        photo_path: Path | None = None,
        video_dir: Path | None = None,
    ) -> None:
        """Insert or replace a run from ``RunRecord.to_detail()``."""
        run_id = detail["id"]
        metrics = detail.get("metrics") or {}
        config = detail.get("config") or {}
        title = detail.get("name") or f"Seed {detail.get('seed')}"
        now = _iso_now()
        photo = _rel_under_data(photo_path)
        video = _rel_under_data(video_dir)
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    """
                    INSERT INTO experiments (
                      id, batch_id, title, lifecycle, seed, name, scenario, engine,
                      garment, cloth_type, cloth_condition, skewed, custom_design,
                      driver, fail_reason, started_at_iso, finished_at_iso, t_sim,
                      cycle_time_wall_s, has_photo, has_video, photo_path, video_dir,
                      detail_json, updated_at_iso
                    ) VALUES (
                      ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?,
                      ?, ?
                    )
                    ON CONFLICT(id) DO UPDATE SET
                      batch_id=excluded.batch_id,
                      title=excluded.title,
                      lifecycle=excluded.lifecycle,
                      seed=excluded.seed,
                      name=excluded.name,
                      scenario=excluded.scenario,
                      engine=COALESCE(excluded.engine, experiments.engine),
                      garment=excluded.garment,
                      cloth_type=excluded.cloth_type,
                      cloth_condition=excluded.cloth_condition,
                      skewed=excluded.skewed,
                      custom_design=excluded.custom_design,
                      driver=excluded.driver,
                      fail_reason=excluded.fail_reason,
                      started_at_iso=excluded.started_at_iso,
                      finished_at_iso=excluded.finished_at_iso,
                      t_sim=excluded.t_sim,
                      cycle_time_wall_s=excluded.cycle_time_wall_s,
                      has_photo=excluded.has_photo,
                      has_video=excluded.has_video,
                      photo_path=COALESCE(excluded.photo_path, experiments.photo_path),
                      video_dir=COALESCE(excluded.video_dir, experiments.video_dir),
                      detail_json=excluded.detail_json,
                      updated_at_iso=excluded.updated_at_iso
                    """,
                    (
                        run_id,
                        detail.get("batchId"),
                        title,
                        detail.get("lifecycle") or "queued",
                        detail.get("seed"),
                        detail.get("name"),
                        config.get("scenario"),
                        engine,
                        detail.get("garment"),
                        detail.get("clothType"),
                        detail.get("clothCondition"),
                        1 if detail.get("skewed") else 0,
                        1 if detail.get("customDesign") else 0,
                        config.get("notes"),
                        detail.get("failReason"),
                        detail.get("startedAtIso"),
                        detail.get("finishedAtIso"),
                        metrics.get("cycleTimeSimS"),
                        metrics.get("cycleTimeWallS"),
                        1 if detail.get("hasPhoto") else 0,
                        1 if detail.get("hasVideo") else 0,
                        photo,
                        video,
                        json.dumps(detail, separators=(",", ":")),
                        now,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def upsert_batch(self, summary: dict[str, Any]) -> None:
        now = _iso_now()
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    """
                    INSERT INTO batches (
                      id, name, lifecycle, total, finished, succeeded, failed,
                      started_at_iso, summary_json, updated_at_iso
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      name=excluded.name,
                      lifecycle=excluded.lifecycle,
                      total=excluded.total,
                      finished=excluded.finished,
                      succeeded=excluded.succeeded,
                      failed=excluded.failed,
                      started_at_iso=COALESCE(excluded.started_at_iso, batches.started_at_iso),
                      summary_json=excluded.summary_json,
                      updated_at_iso=excluded.updated_at_iso
                    """,
                    (
                        summary["id"],
                        summary.get("name") or summary["id"],
                        summary.get("lifecycle") or "queued",
                        int(summary.get("total") or 0),
                        int(summary.get("finished") or 0),
                        int(summary.get("succeeded") or 0),
                        int(summary.get("failed") or 0),
                        summary.get("startedAtIso"),
                        json.dumps(summary, separators=(",", ":")),
                        now,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def append_event(self, event: dict[str, Any]) -> None:
        """Persist one journal event (public dict)."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO journal_events (seq, run_id, batch_id, type, ts_iso, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(event["seq"]),
                    event.get("runId"),
                    event.get("batchId"),
                    event["type"],
                    event["tsIso"],
                    json.dumps(event, separators=(",", ":")),
                ),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT detail_json, has_photo, has_video FROM experiments WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        detail = json.loads(row["detail_json"])
        # Refresh media flags from the row (files may appear after the last upsert).
        detail["hasPhoto"] = bool(row["has_photo"]) or bool(detail.get("hasPhoto"))
        detail["hasVideo"] = bool(row["has_video"]) or bool(detail.get("hasVideo"))
        return detail

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT summary_json FROM batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["summary_json"])

    def list_run_details(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT detail_json FROM experiments ORDER BY started_at_iso DESC"
            ).fetchall()
        return [json.loads(r["detail_json"]) for r in rows]

    def list_experiments(self) -> list[dict[str, Any]]:
        """Launch list items for Experimentos (runs not in a batch + batches)."""
        with self._lock:
            batch_rows = self._conn.execute(
                """
                SELECT id, name, lifecycle, total, finished, succeeded, failed, started_at_iso
                FROM batches
                """
            ).fetchall()
            run_rows = self._conn.execute(
                """
                SELECT id, title, lifecycle, seed, started_at_iso, batch_id
                FROM experiments
                WHERE batch_id IS NULL
                """
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in batch_rows:
            items.append(
                {
                    "kind": "batch",
                    "id": row["id"],
                    "title": row["name"],
                    "lifecycle": row["lifecycle"],
                    "total": row["total"],
                    "finished": row["finished"],
                    "succeeded": row["succeeded"],
                    "failed": row["failed"],
                    "startedAtIso": row["started_at_iso"],
                }
            )
        for row in run_rows:
            items.append(
                {
                    "kind": "run",
                    "id": row["id"],
                    "title": row["title"],
                    "lifecycle": row["lifecycle"],
                    "seed": row["seed"],
                    "startedAtIso": row["started_at_iso"],
                    "batchId": row["batch_id"],
                }
            )
        items.sort(key=lambda x: x.get("startedAtIso") or "", reverse=True)
        return items

    def events_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload_json FROM journal_events
                WHERE run_id = ?
                ORDER BY seq ASC, id ASC
                """,
                (run_id,),
            ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def mark_media(self, run_id: str, *, has_photo: bool | None = None, has_video: bool | None = None) -> None:
        sets: list[str] = []
        args: list[Any] = []
        if has_photo is not None:
            sets.append("has_photo = ?")
            args.append(1 if has_photo else 0)
            if has_photo:
                from xfold.bridge.photo import find_photo

                path = find_photo(run_id)
                sets.append("photo_path = COALESCE(?, photo_path)")
                args.append(_rel_under_data(path))
        if has_video is not None:
            sets.append("has_video = ?")
            args.append(1 if has_video else 0)
            if has_video:
                from xfold.bridge.video import run_dir

                sets.append("video_dir = COALESCE(?, video_dir)")
                args.append(_rel_under_data(run_dir(run_id)))
        if not sets:
            return
        sets.append("updated_at_iso = ?")
        args.append(_iso_now())
        args.append(run_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE experiments SET {', '.join(sets)} WHERE id = ?",
                args,
            )
            # Keep detail_json flags in sync when the row exists.
            row = self._conn.execute(
                "SELECT detail_json FROM experiments WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            detail = json.loads(row["detail_json"])
            if has_photo is not None:
                detail["hasPhoto"] = has_photo
            if has_video is not None:
                detail["hasVideo"] = has_video
            self._conn.execute(
                "UPDATE experiments SET detail_json = ? WHERE id = ?",
                (json.dumps(detail, separators=(",", ":")), run_id),
            )
