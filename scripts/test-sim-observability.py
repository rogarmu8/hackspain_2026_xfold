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

    def test_qc_reject_bins(self):
        from xfold.garments import qc_reject_bin

        self.assertEqual(qc_reject_bin("tee_notgood2"), "stained")
        self.assertEqual(qc_reject_bin("polo_damaged"), "broken")
        self.assertIsNone(qc_reject_bin("tee"))
        self.assertIsNone(qc_reject_bin("custom"))
        states = [p["state"] for p in LINE_PHASES]
        self.assertEqual(states[states.index("PHOTO") + 1], "SORT")

    def test_qc_arm_paths_stay_west_of_camera_post(self):
        import math
        import numpy as np
        from xfold.line import (
            QC_BIN_XY,
            QC_CUP_HOME,
            QC_CUP_LIFT_Z,
            QC_DROP_WATCH_S,
            QC_POLE_XY,
            QC_SUCTION_R,
            QC_X,
            _arm_hits_pole,
            _cup_path,
            _in_qc_keepout,
            _qc_ik,
        )

        self.assertGreaterEqual(QC_DROP_WATCH_S, 1.0)
        self.assertLess(QC_SUCTION_R, 0.10)
        hover = np.array([QC_X, 0.0, QC_CUP_LIFT_Z])
        over = np.array([QC_BIN_XY["broken"][0], QC_BIN_XY["broken"][1], QC_CUP_LIFT_Z])
        for start, end in ((QC_CUP_HOME, hover), (hover, over), (over, QC_CUP_HOME)):
            prev = np.asarray(start, dtype=float)
            for point in _cup_path(start, end):
                for blend in np.linspace(0.0, 1.0, 8):
                    cup = prev + blend * (point - prev)
                    self.assertFalse(_in_qc_keepout(cup, 0.05), cup)
                    _c, shoulder, elbow, wrist, _yaw = _qc_ik(cup)
                    self.assertFalse(_arm_hits_pole(shoulder, elbow, wrist), cup)
                    self.assertGreater(
                        math.hypot(cup[0] - QC_POLE_XY[0], cup[1] - QC_POLE_XY[1]),
                        0.22,
                    )
                prev = np.asarray(point, dtype=float)

    def test_qc_reject_is_success_with_garment_mark(self):
        from xfold.garments import grade_line_outcome, garment_result_label

        self.assertEqual(grade_line_outcome("stained", "tee_notgood2"), (True, None))
        self.assertEqual(grade_line_outcome("broken", "polo_damaged"), (True, None))
        self.assertEqual(grade_line_outcome("packed", "tee"), (True, None))
        ok, reason = grade_line_outcome("packed", "tee_notgood1")
        self.assertFalse(ok)
        self.assertIn("stained", reason)
        self.assertEqual(garment_result_label("tee_notgood1"), "Stained")
        self.runtime.emit_state(self.run_id, "SORT", 1)
        self.runtime.finish_success(self.run_id, 2)
        run = self.runtime.get_run(self.run_id)
        self.assertEqual(run["lifecycle"], "succeeded")
        self.assertIsNone(run["failReason"])

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

    def test_qc_capture_observations(self):
        from pathlib import Path
        from unittest.mock import Mock, patch
        from xfold.bridge.line_driver import LineDriver

        for result, operation in ((None, "PHOTO_UNAVAILABLE"), ((b"jpeg", "image/jpeg"), "PHOTO_SAVED")):
            with self.subTest(operation=operation):
                events = []
                line = Line.__new__(Line)
                line.phase = "PHOTO"
                line.data = SimpleNamespace(time=14.5)
                line.on_event = events.append
                driver = LineDriver.__new__(LineDriver)
                driver.runtime = self.runtime
                driver.session = SimpleNamespace(render_photo=Mock(return_value=result))
                with patch("xfold.bridge.line_driver.save_photo", return_value=Path("test.jpg")) as save:
                    name = driver._capture_photo(self.run_id, line)
                    self.assertEqual(name, "test.jpg" if result else None)
                    self.assertEqual(save.call_count, int(result is not None))
                self.assertEqual(events[0]["operation"], operation)
                self.assertEqual(events[0]["state"], "PHOTO")
                driver._publish(self.run_id, events[0])
                log = self.runtime.get_run(self.run_id)["events"][-1]
                self.assertEqual(log["station"], "qc")
                self.assertEqual(log["level"], "info" if result else "warning")

    def test_qc_camera_failure_keeps_structured_warning(self):
        from unittest.mock import Mock

        events = []
        line = Line.__new__(Line)
        line.data = SimpleNamespace(time=14)
        line.dt = 0.002
        line.cycles = 1
        line.phase = "TO_QC"
        line.log = lambda message: None
        line.on_event = events.append
        line.on_photo = Mock(side_effect=RuntimeError("camera unavailable"))
        line._set_flash = lambda level: None
        for _ in line._shoot():
            line.data.time += line.dt
        line.on_photo.assert_called_once()
        warning = next(e for e in events if e["operation"] == "PHOTO_FAILED")
        self.assertEqual((warning["state"], warning["station"], warning["level"]), ("PHOTO", "qc", "warning"))

    def test_selected_garment_replaces_startup_inputs(self):
        from xfold.garments import resolve_garment

        self.runtime.finish_success(self.run_id, 0)
        run_id = self.runtime.launch_run(name="jersey", seed=8, scenario="legacy",
                                         cloth_type="jersey", cloth_condition="damaged")["id"]
        run = self.runtime.get_run(run_id)
        item = resolve_garment("jersey_damaged")
        self.assertEqual(run["config"]["inputs"]["mesh"], item.mesh)
        self.assertEqual(run["config"]["inputs"]["texture"], item.texture)
        self.assertEqual(run["config"]["inputs"]["garment"], run["garment"])
        self.assertFalse(run["config"]["inputs"]["seedApplied"])
        started = next(e for e in self.runtime.journal.since() if e.type == "run_started" and e.runId == run_id)
        self.assertEqual(started.inputs, run["config"]["inputs"])

    def test_weighted_inputs_are_reproducible_and_record_seed_usage(self):
        from xfold.garments import CLOTH_TYPE_KEYS, CLOTH_CONDITION_KEYS

        configs = []
        for _ in range(2):
            runtime = Runtime(Journal())
            runtime.configure_process(LINE_PHASES, scenario="line", config={"seedApplied": True})
            run_id = runtime.launch_run(
                name="weighted", seed=42, scenario="line", cloth_type="random", cloth_condition="random",
                cloth_weights={key: float(key == "polo") for key in CLOTH_TYPE_KEYS},
                condition_weights={key: float(key == "skewed") for key in CLOTH_CONDITION_KEYS},
            )["id"]
            config = runtime.get_run(run_id)["config"]
            self.assertEqual(config["garment"], "polo")
            self.assertEqual(config["clothCondition"], "skewed")
            self.assertTrue(config["inputs"]["seedApplied"])
            configs.append(config)
        self.assertEqual(configs[0], configs[1])

    def test_batch_inputs_match_each_resolved_sku(self):
        from xfold.garments import resolve_garment

        runtime = Runtime(Journal())
        runtime.configure_process(LINE_PHASES, scenario="line", config={"seedApplied": True})
        runtime.launch_batch(name="mixed", count=4, base_seed=10, scenario="legacy",
                             cloth_mix="list", cloth_types=["tee", "jersey"],
                             condition_mix="list", conditions=["good", "notgood", "skewed"])
        for index, run in enumerate(list(runtime.runs.values())):
            item = resolve_garment(run.garment)
            self.assertEqual(run.inputs["mesh"], item.mesh)
            self.assertEqual(run.inputs["texture"], item.texture)
            self.assertEqual(run.inputs["seed"], 10 + index)
            self.assertTrue(run.inputs["seedApplied"])
            started = next(e for e in runtime.journal.since() if e.type == "run_started" and e.runId == run.id)
            self.assertEqual(started.inputs, run.inputs)
            runtime.finish_success(run.id, 1)

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
    def test_seeded_spawn_reports_actual_pose(self):
        import mujoco
        from xfold.line import build, skew_pose

        model = build()
        poses = []
        for seed in (7, 7, 8):
            events = []
            line = Line(model, mujoco.MjData(model), repeat=False, skewed=True, seed=seed,
                        log=lambda message: None, on_event=events.append)
            line.step()
            measured = events[0]["measurements"]
            pose = (measured["spawnYawRad"], measured["spawnOffsetYM"])
            self.assertEqual(pose, skew_pose(seed))
            poses.append(pose)
        self.assertEqual(poses[0], poses[1])
        self.assertNotEqual(poses[0], poses[2])

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
        photos = []
        line = Line(model, data, repeat=False, log=lambda message: None, on_event=pending.append, seed=42,
                    on_photo=lambda: photos.append((line.phase, float(data.time))))
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
        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0][0], "PHOTO")
        photo = next(s for s in run["stages"] if s["state"] == "PHOTO")
        self.assertEqual(photo["durationSimS"], 1.02)
        self.assertGreater(photos[0][1], photo["startedAtSimS"])
        measurements = run["metrics"]["measurements"]
        self.assertEqual(set(measurements), {"flatnessPreM", "flatnessPostM", "packLengthM", "packWidthM", "packHeightM", "spawnYawRad", "spawnOffsetYM"})
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
