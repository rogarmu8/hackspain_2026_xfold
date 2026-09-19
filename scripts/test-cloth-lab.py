import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np

from xfold.cloth_lab import FOLDER_SLOT, FOLDER_DURATION, LabConfig, ClothLab, SurfaceMetrics, folder_target, run_experiment, save_results


class ClothLabTests(unittest.TestCase):
    def test_triangle_intersections_include_coplanar_overlap(self):
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0],
                              [.2, .2, -1], [.2, .2, 1], [.8, .2, 0]], dtype=float)
        metric = SurfaceMetrics(faces)
        self.assertEqual(metric.intersections(positions), 1)
        positions[3:] = [[.1, .1, 0], [.7, .1, 0], [.1, .7, 0]]
        self.assertEqual(metric.intersections(positions), 1)
        positions[3:, 2] = .01
        self.assertEqual(metric.intersections(positions), 0)
        positions[3:] = [[.8, .8, 0], [1.8, .8, 0], [.8, 1.8, 0]]
        self.assertEqual(metric.intersections(positions), 0)

    def test_adjacent_triangles_are_excluded(self):
        metric = SurfaceMetrics(np.array([[0, 1, 2], [1, 2, 3]]))
        self.assertEqual(metric.intersections(np.array([[0, 0, 0], [1, 0, 0],
                                                       [0, 1, 0], [1, 1, 0]])), 0)

    def test_contact_modes_and_material_constraints(self):
        for contact in ('proxy', 'hybrid', 'native', 'partitioned'):
            for material in ('edge', 'vert', 'elastic'):
                with self.subTest(contact=contact, material=material):
                    lab = ClothLab(LabConfig(resolution=5, contact=contact, material=material))
                    model = lab.model
                    expected = 0 if contact in ('proxy', 'partitioned') else 1 if contact == 'native' else 4
                    self.assertEqual(int(model.flex_contype[0]), expected)
                    self.assertEqual(model.neq, int(material != 'elastic'))
                    if material != 'elastic':
                        eq = mujoco.mjtEq.mjEQ_FLEX if material == 'edge' else mujoco.mjtEq.mjEQ_FLEXVERT
                        self.assertEqual(model.eq_type[0], eq)
                    self.assertAlmostEqual(float(model.body_mass.sum()), .18)

    def test_controller_does_not_write_cloth_state(self):
        for contact in ('hybrid', 'partitioned'):
            with self.subTest(contact=contact):
                lab = ClothLab(LabConfig(scenario='flap', resolution=5, contact=contact))
                lab.data.time = 1.2
                qpos, qvel = lab.data.qpos.copy(), lab.data.qvel.copy()
                with patch('xfold.cloth_lab.mujoco.mj_step') as step:
                    lab.step()
                step.assert_called_once_with(lab.model, lab.data)
                np.testing.assert_array_equal(lab.data.qpos, qpos)
                np.testing.assert_array_equal(lab.data.qvel, qvel)
                self.assertGreater(lab.data.ctrl[0], 0)
                self.assertTrue(np.all(lab.model.geom_conaffinity > 0))
                self.assertEqual(lab.model.nmocap, 0)
                self.assertTrue(lab.model.opt.disableflags & mujoco.mjtDisableBit.mjDSBL_AUTORESET)

    def test_build_is_seeded_and_does_not_use_live_asset_writer(self):
        cfg = LabConfig(resolution=5, seed=12)
        with patch('xfold.shirt.spec_from_mjcf', side_effect=AssertionError('Live writer used')):
            first, second = ClothLab(cfg), ClothLab(cfg)
        np.testing.assert_array_equal(first.data.qpos, second.data.qpos)
        other = ClothLab(replace(cfg, seed=13))
        self.assertFalse(np.array_equal(first.data.qpos, other.data.qpos))

    def test_layers_start_separated(self):
        for layers in (2, 3):
            lab = ClothLab(LabConfig(scenario='layers', resolution=13, layers=layers))
            self.assertEqual(lab.measure()['surface_intersection_pairs'], 0)
            self.assertEqual(lab.model.nflex, 1)

    def test_flap_actuator_moves_without_pinning(self):
        result = run_experiment(LabConfig(scenario='flap', resolution=5, duration=1.2))
        self.assertTrue(result['summary']['numerically_valid'])
        self.assertGreater(result['samples'][-1]['flap_angle_rad'], .1)
        self.assertFalse(result['summary']['flap_schedule_completed'])

    def test_short_runs_are_repeatable_and_json_serializable(self):
        cfg = LabConfig(resolution=5, duration=.04, sample_interval=.02)
        first, second = run_experiment(cfg), run_experiment(cfg)
        self.assertTrue(first['summary']['numerically_valid'])
        self.assertEqual(first['samples'], second['samples'])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'run'
            save_results([first], output)
            self.assertTrue((output / 'summary.json').is_file())
            self.assertTrue((output / 'samples.csv').is_file())
            with self.assertRaises(FileExistsError):
                save_results([second], output)

    def test_rms_speed_is_vector_magnitude(self):
        lab = ClothLab(LabConfig(resolution=5))
        lab.data.qvel[lab.dadr[:, None] + np.arange(3)] = [3, 4, 0]
        self.assertAlmostEqual(lab.measure()['rms_vertex_speed_m_s'], 5)

    def test_contact_parameters_match_between_modes(self):
        lab = ClothLab(LabConfig(resolution=5, edge_timeconst=.005, contact_timeconst=.006))
        spheres = lab.model.geom_group == 3
        np.testing.assert_allclose(lab.model.geom_solref[spheres, 0], .006)
        np.testing.assert_allclose(lab.model.geom_solimp[spheres], np.tile(lab.model.flex_solimp[0], (spheres.sum(), 1)))
        self.assertAlmostEqual(lab.model.eq_solref[0, 0], .005)

    def test_warning_stops_run_without_claiming_success(self):
        cfg = LabConfig(resolution=5, duration=.04)
        lab = ClothLab(cfg)
        def warn():
            lab.data.warning[mujoco.mjtWarning.mjWARN_BADQVEL].number = 1
        with patch.object(lab, 'step', side_effect=warn):
            result = run_experiment(cfg, lab=lab)
        self.assertFalse(result['summary']['numerically_valid'])
        self.assertIsNone(result['summary']['physical_success'])
        self.assertEqual(result['summary']['warnings']['mjWARN_BADQVEL'], 1)

    def test_engine_failure_is_recorded_without_resampling_invalid_state(self):
        cfg = LabConfig(resolution=5, duration=.02)
        lab = ClothLab(cfg)
        with patch.object(lab, 'step', side_effect=mujoco.FatalError('test arena exhausted')), patch.object(lab, 'measure', wraps=lab.measure) as measure:
            result = run_experiment(cfg, lab=lab)
        self.assertFalse(result['summary']['numerically_valid'])
        self.assertIn('test arena exhausted', result['summary']['error'])
        self.assertEqual(measure.call_count, 1)
        with tempfile.TemporaryDirectory() as folder:
            save_results([result], Path(folder) / 'failed-run')

    def test_tee_mesh_and_discrete_integrator(self):
        result = run_experiment(LabConfig(mesh='tee', integrator='discrete', duration=.004))
        self.assertTrue(result['summary']['numerically_valid'])
        self.assertGreater(result['provenance']['vertices'], 100)
        self.assertIsNotNone(result['provenance']['mesh_sha256'])

    def test_contact_partition_preserves_mechanics_and_covers_each_face_once(self):
        base = ClothLab(LabConfig(resolution=7))
        patched = ClothLab(LabConfig(resolution=7, contact='partitioned', patch_triangles=8))
        a, b = base.model, patched.model
        self.assertEqual((a.nbody, a.nv, a.neq), (b.nbody, b.nv, b.neq))
        np.testing.assert_array_equal(a.body_mass, b.body_mass)
        np.testing.assert_array_equal(base.data.qpos, patched.data.qpos)
        np.testing.assert_allclose(base.data.qfrc_passive, patched.data.qfrc_passive)
        self.assertEqual(b.flex_contype[0], 0)
        self.assertGreater(b.nflex, 1)
        np.testing.assert_array_equal(patched.faces, base.faces)
        original = {tuple(face) for face in a.flex_vertbodyid[base.vertex_slice][base.faces]}
        colliders = []
        for f in range(1, b.nflex):
            self.assertLessEqual(b.flex_elemnum[f], 8)
            self.assertEqual(b.flex_group[f], 5)
            self.assertEqual(b.flex_edgedamping[f], 0)
            va, vn = b.flex_vertadr[f], b.flex_vertnum[f]
            ea, en = b.flex_elemdataadr[f], b.flex_elemnum[f]
            bodies = b.flex_vertbodyid[va:va + vn]
            faces = b.flex_elem[ea:ea + en * 3].reshape(-1, 3)
            colliders.extend(tuple(face) for face in bodies[faces])
        self.assertEqual(len(colliders), len(original))
        self.assertEqual(set(colliders), original)
        self.assertEqual(base.measure()['surface_intersection_pairs'], patched.measure()['surface_intersection_pairs'])
        self.assertEqual(patched.data.ncon, 0)
        self.assertNotEqual(base.model_hash, patched.model_hash)
        for lab in (base, patched):
            lab.data.qpos[lab.qadr[len(lab.qadr) // 2] + 2] += .02
            mujoco.mj_forward(lab.model, lab.data)
        np.testing.assert_allclose(base.data.qfrc_passive, patched.data.qfrc_passive)
        for _ in range(10):
            base.step()
            patched.step()
        np.testing.assert_allclose(base.data.qpos, patched.data.qpos, atol=1e-12)

    def test_partitioned_contacts_exceed_global_fifty_without_pair_saturation(self):
        lab = ClothLab(LabConfig(scenario='layers', contact='partitioned', patch_triangles=8))
        pos = lab.data.flexvert_xpos[lab.vertex_slice].copy()
        heights = np.unique(pos[:, 2])
        for index, height in enumerate(heights):
            mask = np.isclose(pos[:, 2], height)
            lab.data.qpos[lab.qadr[mask] + 2] -= index * .003
        mujoco.mj_forward(lab.model, lab.data)
        lab.step()
        self.assertGreater(lab.peak_self_contacts, 50)
        self.assertLess(lab.peak_self_contact_pair_contacts, 50)

    def test_degenerate_triangles_are_not_reported_as_clean_geometry(self):
        lab = ClothLab(LabConfig(resolution=3))
        lab.data.qpos[lab.qadr[0]:lab.qadr[0] + 3] = lab.data.flexvert_xpos[lab.vertex_slice][1] - lab.rest[0]
        sample = lab.measure()
        self.assertGreater(sample['degenerate_triangles'], 0)
        self.assertLess(sample['min_triangle_area_ratio'], 1e-10)

    @unittest.skipUnless(os.environ.get('XFOLD_TEST_MULTILAYER') == '1', 'Set XFOLD_TEST_MULTILAYER=1 for physical regression')
    def test_multilayer_physics_regression(self):
        cfg = LabConfig(scenario='layers', duration=2, timestep=.001, edge_timeconst=.005, sample_interval=.02)
        baseline = run_experiment(cfg)
        self.assertGreater(baseline['summary']['sampled_peak_surface_intersection_pairs'], 0)
        for seed, dt in ((42, .001), (43, .002)):
            with self.subTest(seed=seed, timestep=dt):
                result = run_experiment(replace(cfg, contact='partitioned', seed=seed, timestep=dt))
                summary, final = result['summary'], result['final']
                self.assertTrue(summary['numerically_valid'])
                self.assertEqual(summary['sampled_peak_surface_intersection_pairs'], 0)
                self.assertFalse(summary['self_contact_cap_reached'])
                self.assertGreater(summary['peak_self_contacts'], 50)
                self.assertLess(final['edge_strain_p99'], .01)
                self.assertLess(final['rms_vertex_speed_m_s'], .01)
                self.assertTrue(all(s['degenerate_triangles'] == 0 for s in result['samples']))
                self.assertIsNone(summary['physical_success'])

    def test_folder_has_three_physical_panels_and_bounded_actuators(self):
        lab = ClothLab(LabConfig(scenario='fold', resolution=7, contact='partitioned'))
        self.assertEqual(lab.model.nu, 6)
        self.assertEqual(lab.model.nmocap, 0)
        self.assertTrue(np.all(lab.model.actuator_forcelimited))
        qpos, qvel = lab.data.qpos.copy(), lab.data.qvel.copy()
        collision = lab.model.geom_conaffinity.copy()
        for index, name in enumerate(('left', 'right', 'hem')):
            lab.data.time = 1.5 + index * FOLDER_SLOT
            with patch('xfold.cloth_lab.mujoco.mj_step'):
                lab.step()
            for other in ('left', 'right', 'hem'):
                angle = lab.data.actuator(f'fold_{other}_motor').ctrl[0]
                self.assertEqual(angle > 0, name == other)
            np.testing.assert_array_equal(lab.data.qpos, qpos)
            np.testing.assert_array_equal(lab.data.qvel, qvel)
            np.testing.assert_array_equal(lab.model.geom_conaffinity, collision)
        self.assertEqual(lab.measure()['folder_phase'], 'HEM_CLOSE')

    def test_folder_actuator_moves_in_physics_without_other_panels_folding(self):
        result = run_experiment(LabConfig(scenario='fold', resolution=5, duration=1.2, timestep=.001, contact_timeconst=.002))
        self.assertTrue(result['summary']['numerically_valid'])
        self.assertGreater(result['final']['fold_left_angle_rad'], .1)
        self.assertLess(abs(result['final']['fold_right_angle_rad']), .1)
        self.assertLess(abs(result['final']['fold_hem_angle_rad']), .1)
        self.assertFalse(result['summary']['folder_schedule_completed'])

    def test_folder_is_sized_from_the_cloth(self):
        for mesh in ('grid', 'tee'):
            lab = ClothLab(LabConfig(scenario='fold', mesh=mesh))
            center, half = lab.folder_center, lab.folder_half
            np.testing.assert_allclose(center, (lab.rest[:, :2].min(axis=0) + lab.rest[:, :2].max(axis=0)) / 2)
            np.testing.assert_allclose(half, np.ptp(lab.rest[:, :2], axis=0) / [6, 2])
            self.assertLess(lab.measure()['packet_footprint_fraction'], .5)
            self.assertEqual(lab.model.geom('floor').pos[2], -.5)

    def test_folder_defaults_cover_all_three_panels(self):
        self.assertEqual(LabConfig(scenario='fold').duration, FOLDER_DURATION)
        self.assertEqual(LabConfig().duration, 5.5)
        self.assertEqual(LabConfig(scenario='fold', duration=.02).duration, .02)

    def test_folder_keeps_return_clearance_until_the_panel_is_open(self):
        for t in (3.25, 4, 4.75):
            angle, lift = folder_target(t, .036, .025)
            self.assertAlmostEqual(lift, .061)
        self.assertEqual(folder_target(4.75, .036, .025)[0], 0)
        self.assertEqual(folder_target(5.25, .036, .025), (0, 0))
        self.assertEqual(folder_target(-1, .036, .025), (0, 0))

    def test_folder_checkpoints_are_recorded_even_with_sparse_sampling(self):
        cfg = LabConfig(scenario='fold', resolution=3, duration=FOLDER_DURATION, sample_interval=100)
        lab = ClothLab(cfg)
        def advance_clock():
            lab.data.time += cfg.timestep
        with patch.object(lab, 'step', side_effect=advance_clock):
            result = run_experiment(cfg, lab=lab)
        self.assertEqual(list(result['checkpoints']), ['left', 'right', 'hem'])
        self.assertTrue(result['summary']['folder_schedule_completed'])
        self.assertFalse(result['summary']['folder_footprint_target_met'])
        self.assertIsNone(result['summary']['physical_success'])
        for name, expected in (('left', 6), ('right', 12), ('hem', FOLDER_DURATION)):
            self.assertAlmostEqual(result['checkpoints'][name]['t_s'], expected)

    def test_short_folder_run_does_not_claim_sequence_completion(self):
        result = run_experiment(LabConfig(scenario='fold', resolution=5, duration=.02))
        self.assertFalse(result['summary']['folder_schedule_completed'])
        self.assertEqual(result['checkpoints'], {})
        self.assertIsNone(result['summary']['physical_success'])

    def test_invalid_parameters_are_rejected(self):
        for kwargs in ({'timestep': 0}, {'radius': -1}, {'duration': float('nan')},
                       {'resolution': 2}, {'layers': 4}, {'contact': 'unknown'},
                       {'patch_triangles': 0}, {'patch_triangles': 129}, {'patch_triangles': 1.5},
                       {'fold_return_clearance': -1}, {'scenario': 'fold', 'fold_return_clearance': .08}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ClothLab(LabConfig(**kwargs))


if __name__ == '__main__':
    unittest.main()
