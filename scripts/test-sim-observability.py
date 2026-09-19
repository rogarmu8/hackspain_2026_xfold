import os
import unittest
from types import SimpleNamespace

from xfold.bridge.journal import Journal
from xfold.bridge.runtime import Runtime
from xfold.line import LINE_PHASES, Line


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Runtime(Journal())
        self.runtime.configure_process(LINE_PHASES, scenario="line", config={"seedApplied": False})
        self.run_id = self.runtime.launch_run(name="test", seed=42, scenario="old-ui")["id"]

    def test_launch_does_not_invent_a_physical_transition(self):
        run = self.runtime.get_run(self.run_id)
        self.assertIsNone(run["currentState"])
        self.assertEqual(run["config"]["scenario"], "line")
        self.assertEqual([s["state"] for s in run["stages"]], [s["state"] for s in LINE_PHASES])
        self.assertFalse(any(e.type == "state_changed" for e in self.runtime.journal.since()))
        started = next(e for e in self.runtime.journal.since() if e.type == "run_started")
        self.assertFalse(started.inputs["seedApplied"])
        self.assertEqual(started.stages, self.runtime.capabilities.process.model_dump()["stages"])
        self.assertEqual(self.runtime.snapshot()["capabilities"]["process"]["scenario"], "line")

    def test_press_duration_excludes_transport(self):
        self.runtime.emit_state(self.run_id, "PRESS", 3.53)
        self.runtime.emit_state(self.run_id, "TO_FOLDER", 11.03)
        self.runtime.emit_state(self.run_id, "FOLD", 15.778)
        run = self.runtime.get_run(self.run_id)
        stages = {s["state"]: s for s in run["stages"]}
        self.assertEqual(stages["PRESS"]["durationSimS"], 7.5)
        self.assertEqual(stages["TO_FOLDER"]["durationSimS"], 4.748)
        self.assertIsNone(run["metrics"]["flatnessPost"])
        self.assertIsNone(run["telemetry"]["shirt_in_bag"])

    def test_duplicate_transition_does_not_reset_duration(self):
        self.runtime.emit_state(self.run_id, "PRESS", 3.53)
        self.runtime.emit_state(self.run_id, "PRESS", 6.03)
        self.runtime.emit_state(self.run_id, "TO_FOLDER", 11.03)
        press = next(s for s in self.runtime.get_run(self.run_id)["stages"] if s["state"] == "PRESS")
        self.assertEqual(press["durationSimS"], 7.5)

    def test_logs_keep_context_and_debug_level(self):
        self.runtime.emit_state(self.run_id, "FOLD", 15)
        self.runtime.emit_log(self.run_id, "bag ready", level="debug", source="bagger", t=20,
                              operation="BAG_READY", station="bagger", parallel=True)
        event = self.runtime.get_run(self.run_id)["events"][-1]
        self.assertEqual((event["stage"], event["source"], event["level"]), ("FOLD", "bagger", "debug"))
        self.assertEqual(event["operation"], "BAG_READY")
        self.assertTrue(event["parallel"])
        self.assertIsNone(self.runtime.get_run(self.run_id)["telemetry"]["operation"])

    def test_only_observed_metrics_are_published(self):
        self.runtime.emit_state(self.run_id, "PRESS", 1)
        self.runtime.emit_metrics(self.run_id, 1, {"flatnessPreM": 0.01})
        self.runtime.emit_state(self.run_id, "TO_FOLDER", 8.5)
        self.runtime.emit_metrics(self.run_id, 8.5, {"flatnessPostM": 0.004})
        self.runtime.finish_success(self.run_id, 9)
        metrics = self.runtime.get_run(self.run_id)["metrics"]
        self.assertEqual(metrics["flatnessPre"], 0.01)
        self.assertEqual(metrics["flatnessPost"], 0.004)
        self.assertIsNone(metrics["shirtInBag"])
        self.assertIsNotNone(metrics["cycleTimeWallS"])

    def test_simulator_emits_distinct_transports_and_exact_time(self):
        events = []
        line = Line.__new__(Line)
        line.data = SimpleNamespace(time=11.03)
        line.cycles = 1
        line.phase = "PRESS"
        line.log = lambda message: None
        line.on_event = events.append
        line._enter("BELT", "to folder", phase="TO_FOLDER")
        self.assertEqual(line.stage, "BELT")
        self.assertEqual(events[0]["state"], "TO_FOLDER")
        self.assertEqual(events[0]["t"], 11.03)
        self.assertEqual(events[0]["operation"], "BELT")

    def test_unknown_phase_is_not_silently_hidden(self):
        with self.assertRaises(ValueError):
            self.runtime.emit_state(self.run_id, "NEW_UNDECLARED_PHASE", 1)

    def test_terminal_run_ignores_late_observations(self):
        self.runtime.emit_state(self.run_id, "PRESS", 1)
        self.runtime.finish_failed(self.run_id, 2, "test")
        self.runtime.emit_state(self.run_id, "TO_FOLDER", 3)
        self.runtime.emit_metrics(self.run_id, 3, {"flatnessPostM": 0.002})
        run = self.runtime.get_run(self.run_id)
        self.assertEqual(run["currentState"], "PRESS")
        self.assertIsNone(run["metrics"]["flatnessPost"])


@unittest.skipUnless(os.environ.get("XFOLD_TEST_PHYSICS") == "1", "set XFOLD_TEST_PHYSICS=1 for full MuJoCo cycle")
class PhysicsObservabilityTests(unittest.TestCase):
    def test_actual_line_cycle(self):
        import mujoco
        import numpy as np
        from xfold.line import build
        from xfold.bridge.line_driver import LineDriver

        runtime = Runtime(Journal())
        driver = LineDriver(runtime, SimpleNamespace())
        run_id = runtime.launch_run(name="headless-test", seed=42, scenario="legacy")["id"]
        model = build()
        data = mujoco.MjData(model)
        pending = []
        line = Line(model, data, repeat=False, log=lambda message: None, on_event=pending.append)
        while not line.finished and data.time < 120:
            line.step()
            for event in pending:
                driver._publish(run_id, event)
            pending.clear()
        self.assertTrue(line.finished)
        self.assertTrue(np.isfinite(data.qpos).all())
        runtime.finish_success(run_id, float(data.time))
        run = runtime.get_run(run_id)
        self.assertTrue(all(s["status"] == "completed" for s in run["stages"]))
        states = [e.state for e in runtime.journal.since() if e.type == "state_changed"]
        self.assertEqual(states, [p["state"] for p in LINE_PHASES])
        press = next(s for s in run["stages"] if s["state"] == "PRESS")
        self.assertEqual(press["durationSimS"], 7.5)
        measurements = run["metrics"]["measurements"]
        self.assertEqual(set(measurements), {"flatnessPreM", "flatnessPostM", "packLengthM", "packWidthM", "packHeightM"})
        self.assertTrue(all(np.isfinite(v) and v >= 0 for v in measurements.values()))
        self.assertIsNone(run["metrics"]["shirtInBag"])
        logs = [e for e in run["events"] if e.get("operation")]
        self.assertEqual(next(e for e in logs if e["operation"] == "PRESS")["stage"], "PRESS")
        self.assertEqual(next(e for e in logs if e["operation"] == "BAG")["stage"], "INSERT")
        self.assertEqual(len([e for e in logs if e["operation"].startswith("FLAP_")]), 3)
        self.assertTrue(any(e["parallel"] and e["operation"] == "BAG_READY" for e in logs))
        print(f"headless line: {data.time:.3f}s sim; measured={measurements}")


if __name__ == "__main__":
    unittest.main()
