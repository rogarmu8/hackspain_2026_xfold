"""Isaac port checks that run without Isaac Sim or a GPU.

    pixi run -e mujoco python -B scripts/test-isaac-port.py
    XFOLD_TEST_PHYSICS=1 pixi run -e mujoco python -B scripts/test-isaac-port.py   # + two full cycles

* EngineShim's servo reproduces MuJoCo's press stroke.
* The collider rule matches MuJoCo's contype/conaffinity for cloth and bag.
* The USD stage (needs ``pxr``: ``pip install usd-core``) has every plant geom,
  body, light and camera, the right bodies kinematic, the bag dynamic.
* With XFOLD_TEST_PHYSICS=1: a whole cycle through EngineShim on the MuJoCo
  reference backend goes through the same phases as the native line, at the
  same times, with measurements that agree.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "isaac" / "src"))

from xfold.line import Line, build  # noqa: E402
from xfold.shirt import select_garment  # noqa: E402
from xfold_isaac import compare  # noqa: E402
from xfold_isaac.engine import EngineShim, _Servo, cloth_geoms, collision_mask  # noqa: E402

try:
    import pxr  # noqa: F401

    HAVE_USD = True
except ImportError:
    HAVE_USD = False


def _line():
    select_garment("tee")
    model = build()
    data = mujoco.MjData(model)
    return Line(model, data, repeat=False, seed=7, log=lambda *_: None)


class ServoTests(unittest.TestCase):
    def test_servo_tracks_press_stroke_like_mujoco(self):
        # Free platen (nothing under it): the Python servo against MuJoCo's own.
        select_garment("tee")
        model = build()
        native = mujoco.MjData(model)
        ours = mujoco.MjData(model)
        servo = _Servo(model, 0)
        joint = model.joint("press_stroke")
        for step in range(1500):
            ctrl = -0.4 * min(1.0, step / 500)
            native.ctrl[0] = ours.ctrl[0] = ctrl
            mujoco.mj_step(model, native)
            servo.step(ours, model.opt.timestep)
            mujoco.mj_kinematics(model, ours)
        self.assertAlmostEqual(float(native.qpos[joint.qposadr[0]]), float(ours.qpos[joint.qposadr[0]]), places=3)


class ColliderTests(unittest.TestCase):
    def setUp(self):
        self.line = _line()
        self.model = self.line.model

    def test_colliders_follow_contype_conaffinity(self):
        model = self.model
        collider, with_cloth, with_bag = collision_mask(model, int(self.line._bag))
        name = lambda g: model.geom(g).name  # noqa: E731
        names = {name(g) for g in np.flatnonzero(collider)}
        for expected in ("belt_top", "flap_left", "peel_slab", "platen_heater", "bag_hull", "carton_floor"):
            self.assertIn(expected, names)
        self.assertNotIn("bag_roof", names)  # film: visual only
        self.assertFalse(collider[cloth_geoms(model)].any())
        # The flaps touch cloth only; the carton touches the bag.
        self.assertTrue(with_cloth[model.geom("flap_left").id])
        self.assertFalse(with_bag[model.geom("flap_left").id])
        self.assertTrue(with_bag[model.geom("carton_floor").id])

    def test_flap_swinging_back_drops_its_collider(self):
        model = self.model
        flap = model.geom("flap_left").id
        model.geom_conaffinity[flap] = 0
        self.assertFalse(collision_mask(model, int(self.line._bag))[0][flap])


@unittest.skipUnless(HAVE_USD, "needs pxr (pip install usd-core)")
class UsdSceneTests(unittest.TestCase):
    def test_stage_mirrors_the_model(self):
        from pxr import Usd, UsdGeom, UsdPhysics
        from xfold_isaac.usd_scene import export

        line = _line()
        model, data = line.model, line.data
        mujoco.mj_forward(model, data)
        with tempfile.TemporaryDirectory() as tmp:
            scene = export(Path(tmp) / "line.usda", model, data)
            stage = Usd.Stage.Open(str(Path(tmp) / "line.usda"))
            plant = model.ngeom - len(cloth_geoms(model))
            self.assertEqual(len(scene.geom_paths), plant)
            self.assertEqual(len(scene.light_paths), model.nlight)
            self.assertEqual(len(scene.camera_paths), model.ncam)
            self.assertEqual(model.body(scene.bag).name, "bag")
            # Physics: kinematic bodies are the moving ones something can touch.
            kinematic = {model.body(b).name for b in scene.kinematic}
            self.assertEqual(kinematic, {"press_platen", "flap_left", "flap_right", "flap_bottom", "peel"})
            # Picture: every mocap body, the platen and the bag follow MjData.
            self.assertEqual(len(scene.moving), model.nmocap + 2)
            bag = stage.GetPrimAtPath(scene.body_paths[scene.bag])
            self.assertTrue(bag.HasAPI(UsdPhysics.RigidBodyAPI))
            self.assertFalse(bag.GetAttribute("physics:kinematicEnabled").Get())
            self.assertFalse(any(stage.GetPrimAtPath(p).HasAPI(UsdPhysics.CollisionAPI) for p in scene.geom_paths.values()))
            self.assertEqual(
                UsdGeom.Imageable(stage.GetPrimAtPath("/World/Line")).ComputeVisibility(), UsdGeom.Tokens.invisible
            )
            for path in (scene.cloth_path, scene.cloth_visual_path):
                mesh = UsdGeom.Mesh(stage.GetPrimAtPath(path))
                points = np.array(mesh.GetPointsAttr().Get())
                self.assertEqual(len(points), model.nflexvert)
                np.testing.assert_allclose(points, line._rest, atol=1e-5)
            # A box keeps MuJoCo's half-extents as its scale.
            belt = stage.GetPrimAtPath(scene.geom_paths[model.geom("belt_top").id])
            np.testing.assert_allclose(belt.GetAttribute("xformOp:scale").Get(), model.geom_size[model.geom("belt_top").id])


@unittest.skipUnless(os.environ.get("XFOLD_TEST_PHYSICS"), "set XFOLD_TEST_PHYSICS=1 for full cycles")
class ParityTests(unittest.TestCase):
    """A whole cycle through EngineShim must be the native line's cycle.

    Not bit-identical: the native platen is slowed by the cloth it lands on,
    the shimmed one is a servo that cannot feel it, and the fold amplifies
    that. Same phases, times within a step or two, measurements close.
    """

    def _check(self, garment: str, skewed: bool) -> None:
        native, out_native = compare.record(garment, 7, skewed, "mujoco")
        shimmed, out_shim = compare.record(garment, 7, skewed, "reference")
        self.assertEqual(out_native, out_shim)
        self.assertEqual([(e["state"], e["operation"]) for e in native],
                         [(e["state"], e["operation"]) for e in shimmed])
        for a, b in zip(native, shimmed):
            self.assertLess(abs(a["t"] - b["t"]), 0.1, (a["operation"], a["t"], b["t"]))
            for key, value in a["measurements"].items():
                self.assertAlmostEqual(value, b["measurements"][key], delta=max(0.01, 0.25 * abs(value)), msg=key)

    def test_packed_tee(self):
        self._check("tee", skewed=False)

    def test_skewed_stained_reject(self):
        self._check("tee_notgood2", skewed=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
