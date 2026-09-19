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


class LineModelFixture(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        import mujoco
        import xfold.shirt as shirt

        self.enterContext(patch.dict(os.environ, {"XFOLD_CLOTH_CONTACT": "legacy"}))
        for attr in ('_CFG', '_MESH_CACHE', 'SHIRT_MESH'):
            self.enterContext(patch.object(shirt, attr, getattr(shirt, attr)))
        shirt.select_garment('tee')

        def memory_spec(path, cfg=None):
            cfg = cfg or shirt.shirt_config()
            cloth = shirt.SHIRT_XML.read_text().replace('shirt_t.obj', cfg.mesh).replace('shirt_print.png', cfg.texture)
            scene = path.read_text().replace('shirt_t.obj', cfg.mesh).replace('shirt_print.png', cfg.texture)
            with mujoco.MjVfs() as vfs:
                vfs[str(path)] = scene.encode()
                vfs[str(path.parent / 'shirt.xml')] = cloth.encode()
                return mujoco.MjSpec.from_file(str(path), vfs=vfs)

        self.enterContext(patch('xfold.line.spec_from_mjcf', side_effect=memory_spec))


class LineContactTests(LineModelFixture):
    def test_partitioned_line_keeps_canonical_shirt_and_bag_filtering(self):
        import mujoco
        import numpy as np
        from xfold.line import build
        from xfold.shirt import shirt_vertex_positions, shirt_vertex_qposadr, shirt_vertex_bodies

        legacy, native = build(cloth_contact='legacy'), build(cloth_contact='partitioned')
        self.assertEqual(legacy.nq, native.nq)
        self.assertEqual(legacy.nv, native.nv)
        np.testing.assert_array_equal(legacy.body_mass, native.body_mass)
        data = mujoco.MjData(native)
        line = Line(native, data, repeat=False, seed=42, log=lambda message: None)
        self.assertEqual(len(line.positions()), legacy.nflexvert)
        self.assertEqual(len(shirt_vertex_positions(native, data)), legacy.nflexvert)
        self.assertEqual(len(shirt_vertex_bodies(native)), legacy.nflexvert)
        self.assertEqual(len(np.unique(shirt_vertex_qposadr(native))), legacy.nflexvert)
        self.assertGreater(native.nflexvert, legacy.nflexvert)
        self.assertEqual(line.cloth_contact, 'partitioned')
        bag = native.geom('bag_hull').id
        self.assertFalse(np.any((native.geom_contype | native.geom_conaffinity) & 8))
        for f in range(1, native.nflex):
            self.assertEqual(native.flex_contype[f], 8)
            self.assertEqual(native.flex_conaffinity[f], 8)
            self.assertFalse((native.flex_contype[f] & native.geom_conaffinity[bag]) or
                             (native.geom_contype[bag] & native.flex_conaffinity[f]))
        self.assertTrue(native.opt.disableflags & mujoco.mjtDisableBit.mjDSBL_AUTORESET)

    def test_flatness_uses_unweighted_physical_vertices_only(self):
        import mujoco
        import numpy as np
        from xfold.line import build
        from xfold.shirt import flatness, shirt_vertex_qposadr, shirt_vertex_slice

        model = build(cloth_contact='partitioned')
        data = mujoco.MjData(model)
        data.qpos[shirt_vertex_qposadr(model)[0] + 2] = .08
        mujoco.mj_forward(model, data)
        z = data.flexvert_xpos[shirt_vertex_slice(model), 2]
        self.assertAlmostEqual(flatness(model, data), float(np.std(z)))
        self.assertNotAlmostEqual(flatness(model, data), float(np.std(data.flexvert_xpos[:, 2])))

    def test_steam_does_not_add_elastic_forces_to_collision_patches(self):
        import mujoco
        import numpy as np
        from xfold.line import build
        from xfold.shirt import set_steam

        model = build(cloth_contact='partitioned')
        for on in (True, False):
            set_steam(model, on)
            self.assertGreater(model.flex_edgedamping[0], 0)
            np.testing.assert_array_equal(model.flex_edgedamping[1:], 0)

    def test_selection_is_validated_and_environment_can_be_overridden(self):
        from unittest.mock import patch
        from xfold.line import build

        with patch.dict(os.environ, {'XFOLD_CLOTH_CONTACT': 'partitioned'}):
            self.assertGreater(build().nflex, 1)
            self.assertEqual(build(cloth_contact='legacy').nflex, 1)
        with self.assertRaises(ValueError):
            build(cloth_contact='typo')

    def test_shared_session_preserves_mode_across_garment_rebuilds(self):
        from xfold.bridge.sim_session import SimSession
        from xfold.shirt import load_shirt_mesh, shirt_contact_patch_ids

        session = SimSession(cloth_contact='partitioned')
        self.addCleanup(session.stop)
        self.assertTrue(session.start())
        self.assertEqual(session.kind, 'line')
        for garment in ('jersey', 'tank', 'tee'):
            session.ensure_garment(garment)
            self.assertTrue(shirt_contact_patch_ids(session.model))
            line = Line(session.model, session.data, repeat=False, seed=42, log=lambda message: None)
            line.step()
            self.assertEqual(len(line.positions()), len(load_shirt_mesh()[0]))
            self.assertEqual(line.cloth_contact, 'partitioned')
            model = session.model
            session.ensure_garment(garment)
            self.assertIs(session.model, model)

    def test_driver_pause_resume_cancel_and_new_run(self):
        import threading
        import time
        import numpy as np
        from unittest.mock import patch
        from xfold.bridge.sim_session import SimSession
        from xfold.bridge.line_driver import LineDriver
        from xfold.bridge.schema import CommandRequest

        session = SimSession(cloth_contact='partitioned')
        self.addCleanup(session.stop)
        self.assertTrue(session.start())
        runtime = Runtime(Journal())
        driver = LineDriver(runtime, session)
        self.addCleanup(driver.stop)
        recorder = self.enterContext(patch('xfold.bridge.line_driver.TrajectoryRecorder'))
        recorder.return_value.finalize.return_value = None
        progress, paused = threading.Event(), threading.Event()
        first_states = []
        original_step, original_wait = Line.step, runtime.wait_wake

        def step(line):
            original_step(line)
            if abs(line.data.time - line.dt) < 1e-9:
                first_states.append(line.data.qpos.copy())
            if line.data.time >= .02:
                progress.set()

        def wait(timeout):
            active = runtime.driver_active_run()
            if active is not None and active.paused:
                paused.set()
            return original_wait(timeout)

        self.enterContext(patch.object(Line, 'step', step))
        self.enterContext(patch.object(runtime, 'wait_wake', wait))

        def command(kind, run_id, suffix):
            reply = runtime.handle_command(CommandRequest(clientCommandId=f'{kind}-{suffix}', kind=kind, runId=run_id))
            self.assertEqual(reply['status'], 'accepted')

        try:
            run_id = runtime.launch_run(name='pause-test', seed=42, scenario='line')['id']
            command('pause_run', run_id, 'initial')
            driver.start()
            self.assertTrue(paused.wait(5))
            self.assertEqual(session.sim_time(), 0)
            paused.clear()
            command('resume_run', run_id, 'first')
            self.assertTrue(progress.wait(5))
            command('pause_run', run_id, 'mid-run')
            self.assertTrue(paused.wait(5))
            frozen_time, frozen_qpos = session.sim_time(), session.copy_qpos()
            time.sleep(.03)
            self.assertEqual(session.sim_time(), frozen_time)
            np.testing.assert_array_equal(session.copy_qpos(), frozen_qpos)
            command('cancel_run', run_id, 'first')
            driver.stop()
            self.assertEqual(runtime.get_run(run_id)['lifecycle'], 'cancelled')
            self.assertEqual(session.sim_time(), frozen_time)
            progress.clear()
            second = runtime.launch_run(name='restart-test', seed=42, scenario='line')['id']
            driver.start()
            self.assertTrue(progress.wait(5))
            command('cancel_run', second, 'second')
            driver.stop()
            self.assertEqual(len(first_states), 2)
            np.testing.assert_allclose(first_states[0], first_states[1], atol=1e-9)
            self.assertEqual(runtime.get_run(second)['config']['inputs']['clothContactMode'], 'partitioned')
        finally:
            driver.stop()

    @unittest.skipUnless(os.environ.get('XFOLD_TEST_RENDER') == '1', 'set XFOLD_TEST_RENDER=1 for offscreen viewport')
    def test_live_and_replay_viewport_preserve_physical_state(self):
        import numpy as np
        from xfold.bridge.sim_session import SimSession

        session = SimSession(width=160, height=90, cloth_contact='partitioned')
        self.addCleanup(session.stop)
        self.assertTrue(session.start())
        line = Line(session.model, session.data, repeat=False, seed=42, log=lambda message: None)
        line.step()
        qpos, qvel, t = session.copy_qpos(), session.data.qvel.copy(), session.sim_time()
        for frame in (session.render_jpeg(), session.seek_render(qpos)):
            self.assertIsNotNone(frame)
            self.assertEqual(frame[1], 'image/jpeg')
            self.assertTrue(frame[0].startswith(b'\xff\xd8'))
        np.testing.assert_array_equal(session.copy_qpos(), qpos)
        np.testing.assert_array_equal(session.data.qvel, qvel)
        self.assertEqual(session.sim_time(), t)

    def test_explicit_experimental_compile_failure_does_not_fall_back_to_another_plant(self):
        from unittest.mock import patch
        from xfold.bridge.sim_session import SimSession

        session = SimSession(cloth_contact='partitioned')
        with patch('xfold.line.build', side_effect=ValueError('test compile failure')), patch.object(session, '_compile_press_cell') as fallback:
            self.assertFalse(session.start())
            self.assertFalse(session.ok)
            fallback.assert_not_called()

    def test_experimental_numerical_warning_is_not_reported_as_completion(self):
        import mujoco
        from xfold.line import build

        model = build(cloth_contact='partitioned')
        data = mujoco.MjData(model)
        line = Line(model, data, repeat=False, seed=42, log=lambda message: None)
        line.step()
        data.warning[mujoco.mjtWarning.mjWARN_BADQVEL].number = 1
        with self.assertRaisesRegex(RuntimeError, 'Experimental cloth physics failed'):
            line.step()
        self.assertFalse(line.finished)

    def test_driver_records_mode_without_reusing_vertex_counts_for_other_skus(self):
        from xfold.line import build
        from xfold.bridge.line_driver import LineDriver

        model = build(cloth_contact='partitioned')
        runtime = Runtime(Journal())
        LineDriver(runtime, SimpleNamespace(model=model))
        run_id = runtime.launch_run(name='contact-mode', seed=42, scenario='line', cloth_type='jersey')['id']
        inputs = runtime.get_run(run_id)['config']['inputs']
        self.assertEqual(inputs['clothContactMode'], 'partitioned')
        self.assertFalse(inputs['clothLayerProjection'])
        self.assertTrue(inputs['clothScriptedMotion'])
        self.assertNotIn('clothPhysicsVertices', inputs)
        event = next(e for e in runtime.journal.since() if e.type == 'run_started')
        self.assertEqual(event.inputs['clothContactMode'], 'partitioned')


@unittest.skipUnless(os.environ.get("XFOLD_TEST_PHYSICS") == "1", "set XFOLD_TEST_PHYSICS=1 for full MuJoCo cycle")
class PhysicsObservabilityTests(LineModelFixture):
    def test_seeded_spawn_reports_actual_pose(self):
        import mujoco
        import numpy as np
        from xfold.line import SPAWN_X, build, operator_shirt

        for mode in ('legacy', 'partitioned'):
            model = build(cloth_contact=mode)
            poses = []
            for seed in (7, 7, 8):
                events, positions = [], []
                def observe(event):
                    events.append(event)
                    positions.append(line.positions().copy())
                expected = operator_shirt(SPAWN_X, np.random.default_rng(seed))
                line = Line(model, mujoco.MjData(model), repeat=False, skewed=True, seed=seed,
                            log=lambda message: None, on_event=observe)
                line.step()
                measured = events[0]['measurements']
                pose = (measured['spawnYawRad'], measured['spawnOffsetYM'])
                self.assertEqual(pose, (expected.yaw, expected.dy))
                np.testing.assert_allclose(positions[0], expected.world, atol=1e-12)
                poses.append(pose)
            self.assertEqual(poses[0], poses[1])
            self.assertNotEqual(poses[0], poses[2])

    def test_partitioned_line_cycle_and_reset(self):
        import mujoco
        import numpy as np
        from unittest.mock import patch
        from xfold.line import build
        from xfold.bridge.line_driver import LineDriver
        from xfold.shirt import shirt_vertex_positions

        model = build(cloth_contact='partitioned')
        data = mujoco.MjData(model)
        runtime = Runtime(Journal())
        driver = LineDriver(runtime, SimpleNamespace(model=model))
        run_id = runtime.launch_run(name='partitioned-headless', seed=42, scenario='line')['id']
        pending = []
        line = Line(model, data, repeat=False, seed=42, on_event=pending.append, log=lambda message: None)
        line.step()
        start = data.qpos.copy()
        with patch('xfold.line._Layers', side_effect=AssertionError('Legacy projection used with native contact')):
            while not line.finished and data.time < 120:
                line.step()
                for event in pending:
                    driver._publish(run_id, event)
                    if event['operation'] in ('FLAP_LEFT', 'FLAP_RIGHT', 'FLAP_BOTTOM', 'PACK_MEASURED', 'DONE'):
                        print('partitioned line', event['operation'], event['t'], event['measurements'], flush=True)
                pending.clear()
        self.assertTrue(line.finished)
        self.assertTrue(np.isfinite(data.qpos).all())
        self.assertFalse(np.any(data.warning.number))
        self.assertIsNone(line._layers)
        self.assertEqual(len(line.positions()), 384)
        mujoco.mj_forward(model, data)
        np.testing.assert_allclose(line.positions(), shirt_vertex_positions(model, data), atol=1e-9)
        runtime.finish_success(run_id, float(data.time))
        run = runtime.get_run(run_id)
        self.assertEqual(run['config']['inputs']['clothContactMode'], 'partitioned')
        self.assertTrue(all(s['status'] == 'completed' for s in run['stages']))
        self.assertIsNone(run['metrics']['shirtInBag'])
        reset = Line(model, data, repeat=False, seed=42, log=lambda message: None)
        reset.step()
        np.testing.assert_allclose(data.qpos, start, atol=1e-9)
        self.assertIsNone(reset._layers)

    def test_partitioned_skewed_jersey_cycle(self):
        import mujoco
        import numpy as np
        from xfold.line import build
        from xfold.shirt import select_garment

        select_garment('jersey')
        model = build(cloth_contact='partitioned')
        data = mujoco.MjData(model)
        events = []
        line = Line(model, data, repeat=False, seed=7, skewed=True, log=lambda message: None, on_event=events.append)
        while not line.finished and data.time < 120:
            line.step()
        self.assertTrue(line.finished)
        self.assertFalse(np.any(data.warning.number))
        self.assertIsNone(line._layers)
        self.assertEqual(len(line.positions()), 588)
        states = list(dict.fromkeys(e['state'] for e in events))
        self.assertEqual(states, [p['state'] for p in LINE_PHASES])
        measured = next(e['measurements'] for e in events if e['operation'] == 'PACK_MEASURED')
        self.assertTrue(all(np.isfinite(value) and value >= 0 for value in measured.values()))
        print(f'partitioned skewed jersey: {data.time:.3f}s sim; measured={measured}', flush=True)

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
        self.assertEqual(press["durationSimS"], 7.7)
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
