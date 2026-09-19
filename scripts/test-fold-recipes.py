"""Fold-recipe selection and kinematic pack size for every catalogue panel.

    pixi run -e mujoco python -B scripts/test-fold-recipes.py
"""

from __future__ import annotations

import unittest

import numpy as np

from xfold.fold_recipe import (
    FOLDER_MAX_LENGTH,
    PACK_MAX_LENGTH,
    PACK_MAX_WIDTH,
    apply_recipe,
    choose_fold_recipe,
    pack_ok,
)
from xfold.generate_shirt_mesh import DEFAULT_SPACING, build_panel, shirt_outline


def _world_from_style(style: str) -> np.ndarray:
    verts, _ = build_panel(DEFAULT_SPACING, style=style)
    # Same mapping as line.flat_shirt: collar (+Y obj) → +X world.
    world = np.empty((len(verts), 3), dtype=float)
    world[:, 0] = verts[:, 1] - 0.5 * (verts[:, 1].min() + verts[:, 1].max())
    world[:, 1] = -verts[:, 0]
    world[:, 2] = 0.0
    return world


def _rest_xy(style: str) -> np.ndarray:
    verts, _ = build_panel(DEFAULT_SPACING, style=style)
    # Controller frame: collar +x, left +y (shirt.mesh_to_shirt).
    return np.column_stack((verts[:, 1], verts[:, 0]))


class RecipeChoiceTests(unittest.TestCase):
    def test_tee_is_flipfold(self):
        recipe = choose_fold_recipe(rest_xy=_rest_xy("tee"))
        self.assertEqual(recipe.kind, "flipfold")
        self.assertFalse(recipe.prefold)
        self.assertEqual(recipe.side_mode, "both")
        self.assertEqual(recipe.cross_folds, 1)
        self.assertLessEqual(recipe.length_m, FOLDER_MAX_LENGTH)

    def test_dress_gets_waist_prefold(self):
        recipe = choose_fold_recipe(rest_xy=_rest_xy("dress"))
        self.assertEqual(recipe.kind, "prefold_flipfold")
        self.assertTrue(recipe.prefold)
        self.assertEqual(recipe.side_mode, "both")
        self.assertGreater(recipe.length_m, FOLDER_MAX_LENGTH)

    def test_trousers_get_crease_and_crosses(self):
        recipe = choose_fold_recipe(rest_xy=_rest_xy("trousers"))
        self.assertEqual(recipe.kind, "pants")
        self.assertEqual(recipe.side_mode, "crease")
        self.assertGreaterEqual(recipe.cross_folds, 1)
        self.assertGreater(recipe.crotch, 0.50)
        self.assertGreater(recipe.length_m, FOLDER_MAX_LENGTH)

    def test_jersey_is_long_enough_for_prefold(self):
        recipe = choose_fold_recipe(rest_xy=_rest_xy("jersey"))
        self.assertIn(recipe.kind, ("prefold_flipfold", "flipfold"))
        if recipe.length_m > FOLDER_MAX_LENGTH:
            self.assertTrue(recipe.prefold)

    def test_opencv_mask_agrees_on_trousers(self):
        try:
            import cv2
        except ImportError:
            self.skipTest("opencv not installed")
        poly = shirt_outline("trousers")
        # Raster a top-down QC-like mask: collar up, metres → pixels.
        scale = 400.0
        xs = poly[:, 0]
        ys = poly[:, 1]
        u = ((-xs) - (-xs).min()) * scale
        v = ((-ys) - (-ys).min()) * scale
        w = int(np.ceil(u.max())) + 8
        h = int(np.ceil(v.max())) + 8
        mask = np.zeros((h, w), np.uint8)
        pts = np.column_stack((u, v)).astype(np.int32)
        cv2.fillPoly(mask, [pts], 255)
        rgb = np.repeat(mask[:, :, None], 3, axis=2)
        recipe = choose_fold_recipe(rgb=rgb, metres_per_px=1.0 / scale)
        self.assertEqual(recipe.kind, "pants")
        self.assertGreater(recipe.crotch, 0.4)


class PackSizeTests(unittest.TestCase):
    def test_every_catalogue_style_packs(self):
        for style in ("tee", "work_tee", "jersey", "tank", "polo", "dress", "trousers"):
            with self.subTest(style=style):
                rest = _rest_xy("tee" if style == "work_tee" else style)
                recipe = choose_fold_recipe(rest_xy=rest)
                packed = apply_recipe(_world_from_style("tee" if style == "work_tee" else style), recipe)
                span = packed.max(axis=0) - packed.min(axis=0)
                self.assertTrue(
                    pack_ok(packed),
                    f"{style} {recipe.kind} packed {span[0]*100:.1f}×{span[1]*100:.1f} cm "
                    f"(max {PACK_MAX_LENGTH*100:.0f}×{PACK_MAX_WIDTH*100:.0f})",
                )

    def test_flat_shirt_tee_matches_flipfold(self):
        # flat_shirt needs the live mesh; skip if shirt_t.obj is the only compiled one.
        recipe = choose_fold_recipe(rest_xy=_rest_xy("tee"))
        world = _world_from_style("tee")
        packed = apply_recipe(world, recipe)
        self.assertLess(float(np.ptp(packed[:, 0])), float(np.ptp(world[:, 0])) * 0.6)


if __name__ == "__main__":
    unittest.main()
