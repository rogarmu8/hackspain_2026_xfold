"""Placement inspection from the wrist camera.

The camera on the UR5e wrist renders the bed, OpenCV segments the blue
garment, and the silhouette is back-projected onto the bed plane. The shirt
outline is then fitted against the known footprint, which turns the picture
into a pose in metres and radians - what the controller needs to decide
whether the shirt is straight enough to press.

Two details matter. Only the bed region is inspected, because the crate of
unpressed shirts is blue too and can sit in the same view. And the pose
comes from a shape fit rather than a bounding box: a T-shirt's bounding box
and its area centroid both sit off the garment's own frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .scene import INSPECT_CAMERA
from .shirt import shirt_footprint_polygons

# Slate-blue cloth in HSV, OpenCV convention (hue 0-179).
SHIRT_HSV_LOW = (80, 25, 25)
SHIRT_HSV_HIGH = (140, 255, 255)

# How far past the heated plate we still look, in metres.
ROI_MARGIN = 0.05

# Shape fit: 2 mm cells are finer than the tolerances we care about.
FIT_CELL = 0.002
FIT_HALF_WINDOW = 0.40
COARSE_STEP = math.radians(6.0)
FINE_STEP = math.radians(0.5)

DEFAULT_POSITION_TOLERANCE = 0.015
DEFAULT_YAW_TOLERANCE = math.radians(5.0)
DEFAULT_FIT_FLOOR = 0.80
# A dangling cloth lands crumpled; "on the plate" is the gate until spread exists.
DEFAULT_ON_BED_TOLERANCE = 0.18


@dataclass(frozen=True)
class Placement:
    """What the camera can say about the shirt lying on the bed."""

    found: bool
    center: np.ndarray  # world xy of the garment's own frame
    yaw: float  # radians away from the target orientation
    position_error: float
    yaw_error: float
    fit: float  # overlap between the seen outline and the shirt footprint
    ok: bool

    def describe(self) -> str:
        if not self.found:
            return "no shirt on the bed"
        return (
            f"offset {self.position_error * 1000:5.1f} mm  "
            f"yaw {math.degrees(self.yaw):+5.1f} deg  "
            f"fit {self.fit:4.2f}"
        )


def shirt_panels(model) -> np.ndarray:
    """Deprecated box stand-in; the vision fit uses the rest-mesh triangles."""
    del model
    return np.zeros((0, 4), dtype=float)


def panel_corners(panels: np.ndarray) -> np.ndarray:
    """Corner loops for each panel, shaped (panels, 4, 2)."""
    if len(panels) == 0:
        return np.zeros((0, 4, 2), dtype=float)
    signs = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])
    return panels[:, None, :2] + signs[None, :, :] * panels[:, None, 2:]


def footprint_centroid(polygons) -> np.ndarray:
    """Area centroid of the rest-mesh footprint in the shirt's own frame."""
    weights = []
    centres = []
    for polygon in polygons:
        area = _polygon_area(polygon)
        if abs(area) < 1e-12:
            continue
        weights.append(abs(area))
        centres.append(_polygon_centroid(polygon))
    if not weights:
        return np.zeros(2)
    return np.average(np.asarray(centres), axis=0, weights=weights)


def wrap_to_pi(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


class PlacementCamera:
    def __init__(
        self,
        model,
        *,
        camera: str = INSPECT_CAMERA,
        width: int = 640,
        height: int = 480,
        plane_z: float,
        target_center=(0.0, 0.0),
        target_yaw: float = 0.0,
        roi_half=(0.27, 0.33),
        position_tolerance: float = DEFAULT_POSITION_TOLERANCE,
        yaw_tolerance: float = DEFAULT_YAW_TOLERANCE,
        fit_floor: float = DEFAULT_FIT_FLOOR,
        shape_gate: bool = True,
        on_bed_tolerance: float = DEFAULT_ON_BED_TOLERANCE,
    ) -> None:
        import mujoco

        self.model = model
        self.camera_id = model.camera(camera).id
        self.width = width
        self.height = height
        self.plane_z = plane_z
        self.target_center = np.asarray(target_center, dtype=float)
        self.target_yaw = target_yaw
        self.roi_half = np.asarray(roi_half, dtype=float)
        self.position_tolerance = position_tolerance
        self.yaw_tolerance = yaw_tolerance
        self.fit_floor = fit_floor
        self.shape_gate = shape_gate
        self.on_bed_tolerance = on_bed_tolerance

        self.panel_corners = shirt_footprint_polygons()
        self.footprint_centroid = footprint_centroid(self.panel_corners)
        self.expected_area = float(sum(abs(_polygon_area(p)) for p in self.panel_corners))
        self._footprint_hull = _convex_hull_2d(np.vstack(self.panel_corners))

        self.renderer = mujoco.Renderer(model, height, width)
        # One focal length for both axes; fovy is the vertical opening.
        self.focal = (height / 2.0) / math.tan(
            math.radians(model.cam_fovy[self.camera_id]) / 2.0
        )
        self._fit_origin = self.target_center - FIT_HALF_WINDOW
        self._fit_size = int(round(2 * FIT_HALF_WINDOW / FIT_CELL))

    def close(self) -> None:
        self.renderer.close()

    # --- geometry -----------------------------------------------------------

    def render(self, data) -> np.ndarray:
        self.renderer.update_scene(data, camera=self.camera_id)
        return self.renderer.render()

    def unproject(self, data, pixels) -> np.ndarray:
        """Cast pixels onto the bed plane. Returns world xy, one row per pixel."""
        pixels = np.atleast_2d(np.asarray(pixels, dtype=float))
        origin = data.cam_xpos[self.camera_id]
        rotation = data.cam_xmat[self.camera_id].reshape(3, 3)

        # MuJoCo cameras look down -z, with +x right and +y up in the image.
        local = np.stack(
            [
                (pixels[:, 0] - (self.width - 1) / 2.0) / self.focal,
                -(pixels[:, 1] - (self.height - 1) / 2.0) / self.focal,
                -np.ones(len(pixels)),
            ],
            axis=1,
        )
        rays = local @ rotation.T
        distance = (self.plane_z - origin[2]) / rays[:, 2]
        return origin[:2] + rays[:, :2] * distance[:, None]

    def project(self, data, points) -> np.ndarray:
        points = np.atleast_2d(np.asarray(points, dtype=float))
        origin = data.cam_xpos[self.camera_id]
        rotation = data.cam_xmat[self.camera_id].reshape(3, 3)
        local = (points - origin) @ rotation
        depth = -local[:, 2]
        return np.stack(
            [
                (self.width - 1) / 2.0 + self.focal * local[:, 0] / depth,
                (self.height - 1) / 2.0 - self.focal * local[:, 1] / depth,
            ],
            axis=1,
        )

    def project_plane(self, data, points_xy) -> np.ndarray:
        points_xy = np.atleast_2d(np.asarray(points_xy, dtype=float))
        heights = np.full((len(points_xy), 1), self.plane_z)
        return self.project(data, np.hstack([points_xy, heights]))

    def roi_polygon(self, data) -> np.ndarray:
        """Bed area in pixels: a region of interest fixed by the geometry."""
        half = self.roi_half + ROI_MARGIN
        signs = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])
        return self.project_plane(data, self.target_center + signs * half)

    # --- segmentation and fit ----------------------------------------------

    def mask(self, data, rgb: np.ndarray) -> np.ndarray:
        import cv2

        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        blue = cv2.inRange(hsv, SHIRT_HSV_LOW, SHIRT_HSV_HIGH)
        blue = cv2.morphologyEx(blue, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        blue = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

        roi = np.zeros_like(blue)
        cv2.fillConvexPoly(roi, self.roi_polygon(data).astype(np.int32), 255)
        return cv2.bitwise_and(blue, roi)

    def outline(self, data, rgb: np.ndarray) -> np.ndarray | None:
        """Largest blue silhouette on the bed, back-projected to world xy."""
        import cv2

        contours, _ = cv2.findContours(
            self.mask(data, rgb), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = [c for c in contours if cv2.contourArea(c) > 300]
        if not contours:
            return None
        largest = max(contours, key=cv2.contourArea)
        return self.unproject(data, largest.reshape(-1, 2))

    def inspect(self, data, rgb: np.ndarray | None = None) -> Placement:
        if rgb is None:
            rgb = self.render(data)
        outline = self.outline(data, rgb)
        if outline is None or len(outline) < 3:
            return Placement(
                False, self.target_center.copy(), 0.0, math.inf, math.inf, 0.0, False
            )

        seen = self._raster([outline])
        centroid = _polygon_centroid(outline)
        center, yaw, fit = self._fit_pose(seen, centroid)

        offset = center - self.target_center
        position_error = float(np.linalg.norm(offset))
        yaw_error = abs(wrap_to_pi(yaw - self.target_yaw))
        if self.shape_gate:
            ok = (
                position_error <= self.position_tolerance
                and yaw_error <= self.yaw_tolerance
                and fit >= self.fit_floor
            )
        else:
            ok = position_error <= self.on_bed_tolerance
        return Placement(True, center, yaw, position_error, yaw_error, fit, ok)

    def _fit_pose(self, seen: np.ndarray, centroid: np.ndarray):
        """Rotate the known footprint until it covers the silhouette best.

        For a given yaw the centre follows from the centroid, so this is a
        search over one angle: coarse sweep first, then a local refinement.
        """
        best = (self.target_center.copy(), 0.0, 0.0)
        coarse = np.arange(-math.pi, math.pi, COARSE_STEP)
        for yaw in coarse:
            candidate = self._score(seen, centroid, float(yaw))
            if candidate[2] > best[2]:
                best = candidate
        fine = np.arange(best[1] - COARSE_STEP, best[1] + COARSE_STEP, FINE_STEP)
        for yaw in fine:
            candidate = self._score(seen, centroid, float(yaw))
            if candidate[2] > best[2]:
                best = candidate
        return best

    def _score(self, seen: np.ndarray, centroid: np.ndarray, yaw: float):
        center = centroid - _rotate(self.footprint_centroid, yaw)[0]
        template = self._raster(
            [_rotate(corners, yaw) + center for corners in self.panel_corners]
        )
        union = np.count_nonzero(seen | template)
        if union == 0:
            return center, yaw, 0.0
        overlap = np.count_nonzero(seen & template) / union
        return center, wrap_to_pi(yaw), overlap

    def _raster(self, polygons) -> np.ndarray:
        """Draw world-plane polygons into a fixed grid around the target."""
        import cv2

        grid = np.zeros((self._fit_size, self._fit_size), np.uint8)
        pixels = [
            np.round((np.asarray(p) - self._fit_origin) / FIT_CELL).astype(np.int32)
            for p in polygons
        ]
        cv2.fillPoly(grid, pixels, 1)
        return grid

    # --- debugging ----------------------------------------------------------

    def annotate(self, data, rgb: np.ndarray, placement: Placement) -> np.ndarray:
        """Overlay the region of interest, the silhouette, and the fitted pose."""
        import cv2

        canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        colour = (80, 220, 90) if placement.ok else (70, 90, 240)
        cv2.polylines(
            canvas, [self.roi_polygon(data).astype(np.int32)], True, (90, 90, 90), 1
        )
        contours, _ = cv2.findContours(
            self.mask(data, rgb), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cv2.drawContours(canvas, contours, -1, colour, 1)

        target_px = self.project_plane(data, self.target_center)[0]
        cv2.drawMarker(
            canvas, tuple(target_px.astype(int)), (240, 240, 240), cv2.MARKER_CROSS, 18, 1
        )
        if placement.found:
            world = _rotate(self._footprint_hull, placement.yaw) + placement.center
            cv2.polylines(
                canvas,
                [self.project_plane(data, world).astype(np.int32)],
                True,
                colour,
                2,
            )
        cv2.putText(
            canvas,
            placement.describe(),
            (12, self.height - 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            colour,
            1,
            cv2.LINE_AA,
        )
        return canvas


def _rotate(points: np.ndarray, yaw: float) -> np.ndarray:
    cos, sin = math.cos(yaw), math.sin(yaw)
    rotation = np.array([[cos, -sin], [sin, cos]])
    return np.atleast_2d(points) @ rotation.T


def _convex_hull_2d(points: np.ndarray) -> np.ndarray:
    """Monotone-chain hull, returned as an (n, 2) loop without a duplicate close."""
    pts = np.unique(np.asarray(points, dtype=float), axis=0)
    if len(pts) <= 2:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.asarray(lower[:-1] + upper[:-1], dtype=float)


def _polygon_area(polygon: np.ndarray) -> float:
    x, y = polygon[:, 0], polygon[:, 1]
    return 0.5 * float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum())


def _polygon_centroid(polygon: np.ndarray) -> np.ndarray:
    x, y = polygon[:, 0], polygon[:, 1]
    cross = x * np.roll(y, -1) - np.roll(x, -1) * y
    area = cross.sum() / 2.0
    if abs(area) < 1e-9:
        return polygon.mean(axis=0)
    cx = ((x + np.roll(x, -1)) * cross).sum() / (6.0 * area)
    cy = ((y + np.roll(y, -1)) * cross).sum() / (6.0 * area)
    return np.array([cx, cy])
