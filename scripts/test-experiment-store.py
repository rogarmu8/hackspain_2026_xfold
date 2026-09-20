"""SQLite experiment catalogue: survives a bridge restart."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from xfold.bridge.experiments import ExperimentStore
from xfold.bridge.journal import Journal
from xfold.bridge.runtime import Runtime
from xfold.line import LINE_PHASES


class ExperimentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "experiments.sqlite"
        self.store = ExperimentStore(self.db)
        self.journal = Journal()
        self.runtime = Runtime(self.journal, store=self.store)
        self.runtime.configure_process(LINE_PHASES, scenario="line", config={"seedApplied": False})
        self.runtime.capabilities.engine = "isaac"

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def test_run_survives_restart(self) -> None:
        run_id = self.runtime.launch_run(name="persist-me", seed=7, scenario="line")["id"]
        self.runtime.emit_state(run_id, "LOAD", 0.0)
        self.runtime.emit_metrics(run_id, 1.2, {"packLengthM": 0.31})
        self.runtime.finish_success(run_id, 12.5)

        detail = self.store.get_run(run_id)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["lifecycle"], "succeeded")
        self.assertEqual(detail["seed"], 7)
        self.assertAlmostEqual(detail["metrics"]["cycleTimeSimS"], 12.5)
        self.assertEqual(detail["config"]["inputs"]["garment"], detail["garment"])

        events = self.store.events_for_run(run_id)
        types = [e["type"] for e in events]
        self.assertIn("run_started", types)
        self.assertIn("state_changed", types)
        self.assertIn("run_finished", types)

        self.store.close()
        # Fresh Runtime + store on the same file: no in-memory runs.
        store2 = ExperimentStore(self.db)
        runtime2 = Runtime(Journal(), store=store2)
        runtime2.configure_process(LINE_PHASES, scenario="line", config={"seedApplied": False})

        restored = runtime2.get_run(run_id)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored["lifecycle"], "succeeded")
        self.assertEqual(restored["name"], "persist-me")

        experiments = runtime2.list_experiments()
        self.assertTrue(any(e["id"] == run_id and e["kind"] == "run" for e in experiments))

        timeline_events = runtime2.events_for_run(run_id)
        self.assertGreaterEqual(len(timeline_events), 3)

        # Numbering continues past the persisted max.
        next_id = runtime2.launch_run(name="next", seed=8, scenario="line")["id"]
        self.assertNotEqual(next_id, run_id)
        self.assertGreater(int(next_id.split("-")[1]), int(run_id.split("-")[1]))
        store2.close()
        self.store = ExperimentStore(self.db)  # tearDown closes self.store

    def test_batch_listed_after_restart(self) -> None:
        batch_id = self.runtime.launch_batch(
            name="batch-persist",
            count=2,
            base_seed=1,
            scenario="line",
        )["id"]
        # Finish the active child so the batch advances.
        active = self.runtime.active_run_id
        self.assertIsNotNone(active)
        assert active is not None
        self.runtime.finish_success(active, 5.0)
        active2 = self.runtime.active_run_id
        self.assertIsNotNone(active2)
        assert active2 is not None
        self.runtime.finish_success(active2, 5.0)

        self.store.close()
        store2 = ExperimentStore(self.db)
        runtime2 = Runtime(Journal(), store=store2)
        experiments = runtime2.list_experiments()
        batch = next(e for e in experiments if e["id"] == batch_id)
        self.assertEqual(batch["kind"], "batch")
        self.assertEqual(batch["lifecycle"], "succeeded")
        self.assertEqual(batch["finished"], 2)
        store2.close()
        self.store = ExperimentStore(self.db)

    def test_delete_run_drops_catalogue_and_events(self) -> None:
        run_id = self.runtime.launch_run(name="drop-me", seed=3, scenario="line")["id"]
        self.runtime.finish_success(run_id, 4.0)
        self.assertIsNotNone(self.store.get_run(run_id))
        self.assertTrue(any(r["id"] == run_id for r in self.runtime.list_runs()))

        out = self.runtime.delete_run(run_id)
        self.assertEqual(out["id"], run_id)
        self.assertIsNone(self.store.get_run(run_id))
        self.assertFalse(any(r["id"] == run_id for r in self.runtime.list_runs()))
        self.assertFalse(any(e["id"] == run_id for e in self.runtime.list_experiments()))
        self.assertEqual(self.store.events_for_run(run_id), [])
        types = [e.type for e in self.journal.since(0)]
        self.assertIn("run_deleted", types)
        with self.assertRaises(KeyError):
            self.runtime.delete_run(run_id)

    def test_cancel_force_quits_and_delete_still_works(self) -> None:
        from xfold.bridge.schema import CommandRequest

        run_id = self.runtime.launch_run(name="force-quit", seed=4, scenario="line")["id"]
        run = self.runtime.runs[run_id]
        self.assertEqual(run.lifecycle, "running")
        ack = self.runtime.handle_command(
            CommandRequest(clientCommandId="c1", kind="cancel_run", runId=run_id)
        )
        self.assertEqual(ack["status"], "accepted")
        self.assertTrue(run.cancel_requested)
        self.assertEqual(run.lifecycle, "cancelled")
        out = self.runtime.delete_run(run_id)
        self.assertEqual(out["id"], run_id)
        self.assertIsNone(self.store.get_run(run_id))
        self.assertFalse(any(r["id"] == run_id for r in self.runtime.list_runs()))

    def test_memory_store_for_ephemeral_bridge(self) -> None:
        store = ExperimentStore(":memory:")
        runtime = Runtime(Journal(), store=store)
        runtime.configure_process(LINE_PHASES, scenario="line", config={"seedApplied": False})
        run_id = runtime.launch_run(name="ephemeral", seed=1, scenario="line")["id"]
        runtime.finish_failed(run_id, 1.0, reason="boom")
        self.assertEqual(store.get_run(run_id)["lifecycle"], "failed")
        store.close()

    def test_schema_migrates_and_is_idempotent(self) -> None:
        from xfold.bridge.experiments import SCHEMA_VERSION

        self.assertEqual(self.store.schema_version, SCHEMA_VERSION)
        version = int(
            self.store._conn.execute("PRAGMA user_version").fetchone()[0]  # noqa: SLF001
        )
        self.assertEqual(version, SCHEMA_VERSION)

        self.store.close()
        again = ExperimentStore(self.db)
        self.assertEqual(again.schema_version, SCHEMA_VERSION)
        again.close()
        self.store = ExperimentStore(self.db)

    def test_legacy_unversioned_file_upgrades(self) -> None:
        """DBs written before user_version still open; migrate sets v1."""
        import sqlite3

        from xfold.bridge.experiments import SCHEMA_VERSION, _migrate_v1

        legacy = Path(self._tmp.name) / "legacy.sqlite"
        conn = sqlite3.connect(str(legacy))
        _migrate_v1(conn)  # tables as shipped in the first commit
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()

        store = ExperimentStore(legacy)
        self.assertEqual(store.schema_version, SCHEMA_VERSION)
        version = int(
            store._conn.execute("PRAGMA user_version").fetchone()[0]  # noqa: SLF001
        )
        self.assertEqual(version, SCHEMA_VERSION)
        store.close()

    def test_newer_schema_is_rejected(self) -> None:
        import sqlite3

        future = Path(self._tmp.name) / "future.sqlite"
        conn = sqlite3.connect(str(future))
        conn.execute("PRAGMA user_version = 99")
        conn.close()
        with self.assertRaises(RuntimeError) as ctx:
            ExperimentStore(future)
        self.assertIn("v99", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
