"""Build an OpenUSD stage from the compiled line model.

line.xml stays the only description of the plant. This walks the compiled
MjModel, after xfold.line.build() has moved the press onto the belt and
picked the bag label, and writes one prim per body and per geom, named as
in the MJCF. Nothing is re-authored by hand, so a change to line.xml shows
up in Isaac the next run.

  * Two trees (see build_stage): ROOT for physics, hidden; VISUAL for the
    picture. Bodies are flattened in both at their world pose. In ROOT a
    static body is plain colliders, a mocap or jointed body with a collider
    is a kinematic rigid body that the backend teleports every step (which is
    what MuJoCo does to a mocap body too), and the bag, the one free body, is
    a dynamic rigid body.
  * Geoms keep their local pose, and a size that can be rewritten (Line
    reshapes the bag's films, scrolls belt slats, puffs steam).
  * A geom gets a collider only if MuJoCo's contype/conaffinity would let it
    touch the cloth or the bag (engine.collision_mask). Collision groups keep
    the bag off colliders that only the cloth may touch, as in MuJoCo.
  * The cloth is a triangle mesh in flex vertex order, textured with the
    garment's print. Its physics (a PhysX surface deformable) is added by the
    Isaac backend, which needs PhysX's own schemas. Textured boxes (bag
    stickers, the floor checker) are UV meshes; UsdGeom.Cube has no UVs.
  * Lights and cameras keep their MuJoCo names and poses.

Only ``pxr`` is needed: usd-core on a laptop, or the copy inside Isaac Sim.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import mujoco
import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade, Vt

from .engine import VISIBLE_GROUPS, cloth_geoms, collision_mask, geom_color

ROOT = "/World/Line"
VISUAL = "/World/Visual"
LOOKS = "/World/Looks"
PHYSICS = "/World/Physics"
CLOTH_NAME = "shirt"
# A MuJoCo plane is infinite when its size is 0; a slab this big covers the hall.
PLANE_HALF = 25.0
PLANE_THICKNESS = 0.02
# MuJoCo light levels are 0..1; RTX lights are in nits. Tuned on the L4 box
# against the MuJoCo render of the same camera, not physically derived.
LIGHT_GAIN = 6.0e4
LIGHT_RADIUS = 0.08
DOME_GAIN = 900.0
# offwidth x offheight in line.xml.
CAMERA_ASPECT = 1280.0 / 960.0
FOCAL_LENGTH = 18.0

_GEOM = mujoco.mjtGeom


@dataclass
class SceneMap:
    """Where each piece of the MuJoCo model lives on the stage."""

    # Physics prims (ROOT): bodies with a collider, and the bag.
    body_paths: dict[int, str] = field(default_factory=dict)
    collider_paths: dict[int, str] = field(default_factory=dict)
    # Render prims (VISUAL): every body and plant geom.
    visual_body_paths: dict[int, str] = field(default_factory=dict)
    geom_paths: dict[int, str] = field(default_factory=dict)
    # Bodies whose visual copy follows MjData every frame.
    moving: list[int] = field(default_factory=list)
    geom_kind: dict[int, int] = field(default_factory=dict)
    material_paths: dict[int, str] = field(default_factory=dict)
    kinematic: list[int] = field(default_factory=list)
    bag: int | None = None
    cloth_path: str = f"{ROOT}/{CLOTH_NAME}"
    cloth_visual_path: str = f"{VISUAL}/{CLOTH_NAME}"
    cloth_points: int = 0
    light_paths: dict[int, str] = field(default_factory=dict)
    dome_path: str = "/World/Lights/headlight"
    camera_paths: dict[str, str] = field(default_factory=dict)
    collider: np.ndarray | None = None


def _name(raw: str, fallback: str, taken: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", raw) if raw else fallback
    if not base or base[0].isdigit():
        base = f"_{base}"
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}_{n}"
    taken.add(name)
    return name


def _quat(wxyz) -> Gf.Quatd:
    w, x, y, z = (float(v) for v in wxyz)
    return Gf.Quatd(w, x, y, z)


def _mat_quat(mat9) -> np.ndarray:
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, np.asarray(mat9, dtype=float).ravel())
    return quat


def _xform_ops(prim: UsdGeom.Xformable, pos, quat, scale=(1.0, 1.0, 1.0)) -> None:
    prim.ClearXformOpOrder()
    prim.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*(float(v) for v in pos)))
    prim.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(_quat(quat))
    prim.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*(float(v) for v in scale)))


def _moving_bodies(model) -> tuple[np.ndarray, int | None]:
    """Per body: does anything move it (mocap, a joint, a moving parent)?

    Returns the flags and the free-jointed body, if there is exactly one.
    """
    moving = np.zeros(model.nbody, dtype=bool)
    free = None
    for body in range(1, model.nbody):
        joints = range(model.body_jntadr[body], model.body_jntadr[body] + model.body_jntnum[body])
        kinds = {int(model.jnt_type[j]) for j in joints}
        if int(mujoco.mjtJoint.mjJNT_FREE) in kinds:
            if free is not None:
                raise NotImplementedError("more than one free body")
            free = body
            continue
        moving[body] = (
            model.body_mocapid[body] >= 0 or bool(kinds) or moving[model.body_parentid[body]]
        )
    return moving, free


def geom_scale(kind: int, size: np.ndarray) -> tuple[float, float, float]:
    """xformOp:scale for a geom of this MuJoCo type and size (1 if sized by attribute)."""
    if kind == _GEOM.mjGEOM_BOX or kind == _GEOM.mjGEOM_ELLIPSOID:
        return float(size[0]), float(size[1]), float(size[2])
    if kind == _GEOM.mjGEOM_SPHERE:
        return (float(size[0]),) * 3
    return 1.0, 1.0, 1.0


def set_geom_shape(prim: Usd.Prim, kind: int, size: np.ndarray) -> None:
    """Radius and height for the geoms USD sizes by attribute, not by scale."""
    if kind == _GEOM.mjGEOM_CYLINDER:
        cyl = UsdGeom.Cylinder(prim)
        cyl.GetRadiusAttr().Set(float(size[0]))
        cyl.GetHeightAttr().Set(2.0 * float(size[1]))
    elif kind == _GEOM.mjGEOM_CAPSULE:
        cap = UsdGeom.Capsule(prim)
        cap.GetRadiusAttr().Set(float(size[0]))
        # USD's capsule height is the cylinder between the caps, as in MuJoCo.
        cap.GetHeightAttr().Set(2.0 * float(size[1]))


def _geom_texture(model, geom: int) -> int:
    mat = int(model.geom_matid[geom])
    if mat < 0:
        return -1
    return int(model.mat_texid[mat].max())


def _unit_box_mesh(stage: Usd.Stage, path: str) -> Usd.Prim:
    """Unit cube [-1, 1] with UVs on every face (UsdGeom.Cube has none)."""
    faces = (
        ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),
        ((1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)),
        ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)),
        ((-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)),
        ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)),
        ((-1, -1, 1), (1, -1, 1), (1, -1, -1), (-1, -1, -1)),
    )
    # Title is at the top of the PNG; USD v=0 is the bottom of the image.
    uvs = ((0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0))
    points = [p for face in faces for p in face]
    st = [uv for _ in faces for uv in uvs]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr([Gf.Vec3f(*p) for p in points])
    mesh.CreateFaceVertexCountsAttr([4] * 6)
    mesh.CreateFaceVertexIndicesAttr(list(range(24)))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(True)
    primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    )
    primvar.Set([Gf.Vec2f(*uv) for uv in st])
    return mesh.GetPrim()


def _define_geom(stage: Usd.Stage, path: str, kind: int, *, textured: bool = False) -> Usd.Prim | None:
    if kind in (_GEOM.mjGEOM_BOX, _GEOM.mjGEOM_PLANE):
        if textured:
            return _unit_box_mesh(stage, path)
        cube = UsdGeom.Cube.Define(stage, path)
        cube.GetSizeAttr().Set(2.0)  # unit half-extent, sized by scale
        return cube.GetPrim()
    if kind in (_GEOM.mjGEOM_SPHERE, _GEOM.mjGEOM_ELLIPSOID):
        sphere = UsdGeom.Sphere.Define(stage, path)
        sphere.GetRadiusAttr().Set(1.0)
        return sphere.GetPrim()
    if kind == _GEOM.mjGEOM_CYLINDER:
        cyl = UsdGeom.Cylinder.Define(stage, path)
        cyl.GetAxisAttr().Set(UsdGeom.Tokens.z)
        return cyl.GetPrim()
    if kind == _GEOM.mjGEOM_CAPSULE:
        cap = UsdGeom.Capsule.Define(stage, path)
        cap.GetAxisAttr().Set(UsdGeom.Tokens.z)
        return cap.GetPrim()
    return None


def _preview_material(stage: Usd.Stage, path: str, rgba, *, roughness: float = 0.6) -> UsdShade.Material:
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*(float(c) for c in rgba[:3])))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(rgba[3]))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def set_material_color(stage: Usd.Stage, path: str, rgba) -> None:
    shader = UsdShade.Shader(stage.GetPrimAtPath(f"{path}/shader"))
    if not stage.GetPrimAtPath(f"{path}/image"):
        shader.GetInput("diffuseColor").Set(Gf.Vec3f(*(float(c) for c in rgba[:3])))
    shader.GetInput("opacity").Set(float(rgba[3]))


def geom_visible(model, geom: int, rgba) -> bool:
    return int(model.geom_group[geom]) < VISIBLE_GROUPS and float(rgba[3]) > 0.0


def write_texture(model, tex: int, path: Path) -> Path:
    """Dump a compiled MuJoCo texture to PNG, whatever its source (file or builtin)."""
    from PIL import Image

    width, height = int(model.tex_width[tex]), int(model.tex_height[tex])
    channels = int(model.tex_nchannel[tex])
    start = int(model.tex_adr[tex])
    pixels = np.asarray(model.tex_data[start : start + width * height * channels], dtype=np.uint8)
    image = pixels.reshape(height, width, channels)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image.squeeze() if channels == 1 else image).save(path)
    return path


def build_stage(stage: Usd.Stage, model, data, *, texture_dir: Path) -> SceneMap:
    """Populate ``stage`` from ``model`` posed as in ``data`` (after mj_forward).

    Two trees. ROOT holds physics only, hidden: colliders, rigid bodies and
    the deformable cloth. VISUAL holds what the camera sees, with no physics
    at all, posed every rendered frame from MjData, which EngineShim keeps
    equal to the PhysX state. Keeping them apart means the picture never
    depends on how PhysX publishes its results (GPU pipeline, Fabric), and
    Line's visual edits (films, slats, steam) never touch a physics prim.

    Call it before Line runs its first step: the cloth is written at the pose
    ``data`` has, which is its rest shape right after build().
    """
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Imageable(UsdGeom.Xform.Define(stage, ROOT)).MakeInvisible()
    UsdGeom.Xform.Define(stage, VISUAL)
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))

    scene_prim = UsdPhysics.Scene.Define(stage, f"{PHYSICS}/scene")
    gravity = np.asarray(model.opt.gravity, dtype=float)
    magnitude = float(np.linalg.norm(gravity))
    if magnitude:
        scene_prim.CreateGravityDirectionAttr(Gf.Vec3f(*(gravity / magnitude)))
        scene_prim.CreateGravityMagnitudeAttr(magnitude)

    scene = SceneMap()
    moving, free = _moving_bodies(model)
    scene.bag = free
    collider, with_cloth, with_bag = collision_mask(model, free)
    scene.collider = collider
    skip = set(cloth_geoms(model).tolist())
    flex_bodies = set(np.asarray(model.flex_vertbodyid).tolist())

    groups = _collision_groups(stage)
    friction_materials: dict[float, UsdShade.Material] = {}

    taken: set[str] = {CLOTH_NAME}
    for body in range(model.nbody):
        if body in flex_bodies:
            continue
        geoms = [g for g in range(model.body_geomadr[body], model.body_geomadr[body] + model.body_geomnum[body])
                 if g not in skip]
        if not geoms and body != free:
            continue
        name = _name(model.body(body).name, "world" if body == 0 else f"body_{body}", taken)
        visual_path = f"{VISUAL}/{name}"
        _xform_ops(UsdGeom.Xform.Define(stage, visual_path), data.xpos[body], data.xquat[body])
        scene.visual_body_paths[body] = visual_path
        if moving[body] or body == free:
            scene.moving.append(body)

        # Physics copy: only the geoms something can touch.
        solid = [g for g in geoms if collider[g]]
        if solid or body == free:
            path = f"{ROOT}/{name}"
            xform = UsdGeom.Xform.Define(stage, path)
            _xform_ops(xform, data.xpos[body], data.xquat[body])
            scene.body_paths[body] = path
            prim = xform.GetPrim()
            if body == free:
                UsdPhysics.RigidBodyAPI.Apply(prim)
                mass = UsdPhysics.MassAPI.Apply(prim)
                mass.CreateMassAttr(float(model.body_mass[body]))
                mass.CreateCenterOfMassAttr(Gf.Vec3f(*(float(v) for v in model.body_ipos[body])))
                mass.CreateDiagonalInertiaAttr(Gf.Vec3f(*(float(v) for v in model.body_inertia[body])))
                mass.CreatePrincipalAxesAttr(Gf.Quatf(*(float(v) for v in model.body_iquat[body])))
            elif moving[body]:
                rigid = UsdPhysics.RigidBodyAPI.Apply(prim)
                rigid.CreateKinematicEnabledAttr(True)
                UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(1.0)
                scene.kinematic.append(body)

        geom_taken: set[str] = set()
        for geom in geoms:
            kind = int(model.geom_type[geom])
            gname = _name(model.geom(geom).name, f"geom_{geom}", geom_taken)
            size = np.array(model.geom_size[geom], dtype=float)
            pos = np.array(model.geom_pos[geom], dtype=float)
            quat = np.array(model.geom_quat[geom], dtype=float)
            if kind == _GEOM.mjGEOM_PLANE:
                scale = (float(size[0]) or PLANE_HALF, float(size[1]) or PLANE_HALF, PLANE_THICKNESS)
                rot = np.zeros(9)
                mujoco.mju_quat2Mat(rot, quat)
                pos = pos - rot.reshape(3, 3)[:, 2] * PLANE_THICKNESS
            else:
                scale = geom_scale(kind, size)

            gpath = f"{visual_path}/{gname}"
            tex = _geom_texture(model, geom)
            textured = tex >= 0 and kind in (_GEOM.mjGEOM_BOX, _GEOM.mjGEOM_PLANE)
            gprim = _define_geom(stage, gpath, kind, textured=textured)
            if gprim is None:
                print(f"usd_scene: skipped geom {gname} of unsupported type {kind}", flush=True)
                continue
            _xform_ops(UsdGeom.Xformable(gprim), pos, quat, scale)
            set_geom_shape(gprim, kind, size)
            scene.geom_paths[geom] = gpath
            scene.geom_kind[geom] = kind
            rgba = geom_color(model, geom)
            mpath = f"{LOOKS}/{name}_{gname}"
            material = _preview_material(stage, mpath, rgba)
            if textured:
                png = write_texture(model, tex, texture_dir / f"{model.texture(tex).name or gname}.png")
                _texture_material(stage, material, png)
            UsdShade.MaterialBindingAPI.Apply(gprim).Bind(material)
            scene.material_paths[geom] = mpath
            if not geom_visible(model, geom, rgba):
                UsdGeom.Imageable(gprim).MakeInvisible()

            if not collider[geom]:
                continue
            if kind == _GEOM.mjGEOM_ELLIPSOID and len(set(np.round(size, 6))) > 1:
                print(f"usd_scene: ellipsoid {gname} collides in MuJoCo; PhysX gets no collider", flush=True)
                continue
            cpath = f"{scene.body_paths[body]}/{gname}"
            cprim = _define_geom(stage, cpath, kind)
            _xform_ops(UsdGeom.Xformable(cprim), pos, quat, scale)
            set_geom_shape(cprim, kind, size)
            UsdPhysics.CollisionAPI.Apply(cprim)
            scene.collider_paths[geom] = cpath
            friction = round(float(model.geom_friction[geom, 0]), 4)
            if friction not in friction_materials:
                friction_materials[friction] = _friction_material(stage, friction)
            UsdShade.MaterialBindingAPI.Apply(cprim).Bind(
                friction_materials[friction], UsdShade.Tokens.weakerThanDescendants, "physics"
            )
            if body == free:
                group = "bag"
            elif with_cloth[geom] and not with_bag[geom]:
                group = "cloth_only"
            else:
                group = "shared"
            groups[group].GetCollidersCollectionAPI().GetIncludesRel().AddTarget(cpath)

    _build_cloth(stage, model, data, scene, texture_dir)
    if free is not None:
        # Collision groups cover rigid pairs; the cloth-bag pair is filtered
        # on the body as well, since the cloth is not a plain collider.
        UsdPhysics.FilteredPairsAPI.Apply(stage.GetPrimAtPath(scene.body_paths[free])).GetFilteredPairsRel().AddTarget(
            scene.cloth_path
        )
        groups["cloth"].GetCollidersCollectionAPI().GetIncludesRel().AddTarget(scene.cloth_path)
    _build_lights(stage, model, data, scene)
    _build_cameras(stage, model, data, scene)
    return scene


def _collision_groups(stage: Usd.Stage) -> dict[str, UsdPhysics.CollisionGroup]:
    """Four groups: MuJoCo lets the bag touch neither the cloth nor the
    flaps, peel and rails that are only there for the cloth."""
    groups = {
        name: UsdPhysics.CollisionGroup.Define(stage, f"{PHYSICS}/groups/{name}")
        for name in ("shared", "cloth_only", "bag", "cloth")
    }
    groups["bag"].CreateFilteredGroupsRel().AddTarget(groups["cloth_only"].GetPath())
    groups["bag"].GetFilteredGroupsRel().AddTarget(groups["cloth"].GetPath())
    return groups


def _friction_material(stage: Usd.Stage, friction: float) -> UsdShade.Material:
    path = f"{PHYSICS}/friction_{str(friction).replace('.', 'p')}"
    material = UsdShade.Material.Define(stage, path)
    api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    api.CreateStaticFrictionAttr(friction)
    api.CreateDynamicFrictionAttr(friction)
    api.CreateRestitutionAttr(0.0)
    return material


def cloth_mesh(model, flex: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Triangles (local vertex ids), and UVs with their per-corner indices."""
    if int(model.flex_dim[flex]) != 2:
        raise NotImplementedError("only 2D (surface) flexes are supported")
    adr, count = int(model.flex_elemadr[flex]), int(model.flex_elemnum[flex])
    tris = np.asarray(model.flex_elem[adr * 3 : (adr + count) * 3], dtype=np.int32).reshape(count, 3)
    uv = uv_ids = None
    tex_adr = int(model.flex_texcoordadr[flex])
    if tex_adr >= 0:
        corners = np.asarray(model.flex_elemtexcoord[adr * 3 : (adr + count) * 3], dtype=np.int32)
        if corners.size and corners.min() >= 0:
            nvert = int(model.flex_vertnum[flex])
            uv = np.asarray(model.flex_texcoord[tex_adr : tex_adr + nvert], dtype=float).copy()
            uv_ids = corners.reshape(count, 3)
    return tris, uv, uv_ids


def _cloth_mesh_prim(stage: Usd.Stage, path: str, points: np.ndarray, tris: np.ndarray) -> UsdGeom.Mesh:
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points.astype(np.float32)))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(tris)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(tris.ravel()))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(True)
    return mesh


def set_cloth_points(stage: Usd.Stage, scene: SceneMap, points: np.ndarray) -> None:
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(scene.cloth_visual_path))
    mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(np.asarray(points, dtype=np.float32)))
    lo, hi = points.min(axis=0), points.max(axis=0)
    mesh.GetExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*(float(v) for v in lo)), Gf.Vec3f(*(float(v) for v in hi))]))


def _build_cloth(stage: Usd.Stage, model, data, scene: SceneMap, texture_dir: Path) -> None:
    tris, uv, uv_ids = cloth_mesh(model)
    start = int(model.flex_vertadr[0])
    count = int(model.flex_vertnum[0])
    points = np.asarray(data.flexvert_xpos[start : start + count], dtype=float)
    _cloth_mesh_prim(stage, scene.cloth_path, points, tris)
    mesh = _cloth_mesh_prim(stage, scene.cloth_visual_path, points, tris)
    mesh.CreateExtentAttr()
    set_cloth_points(stage, scene, points)
    scene.cloth_points = count

    mat = int(model.flex_matid[0])
    rgba = model.mat_rgba[mat] if mat >= 0 else np.array([0.9, 0.9, 0.9, 1.0])
    material = _preview_material(stage, f"{LOOKS}/{CLOTH_NAME}", rgba, roughness=0.9)
    tex = int(model.mat_texid[mat].max()) if mat >= 0 else -1
    if uv is not None and tex >= 0:
        # MuJoCo samples row 0 of the image at v = 0; USD puts v = 0 at the bottom.
        st = uv.copy()
        st[:, 1] = 1.0 - st[:, 1]
        primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
        )
        primvar.Set(Vt.Vec2fArray.FromNumpy(st.astype(np.float32)))
        primvar.SetIndices(Vt.IntArray.FromNumpy(uv_ids.ravel()))
        png = write_texture(model, tex, texture_dir / f"{model.texture(tex).name or 'cloth'}.png")
        _texture_material(stage, material, png)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)


def _texture_material(stage: Usd.Stage, material: UsdShade.Material, png: Path) -> None:
    path = material.GetPath()
    reader = UsdShade.Shader.Define(stage, f"{path}/st")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    image = UsdShade.Shader.Define(stage, f"{path}/image")
    image.CreateIdAttr("UsdUVTexture")
    image.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(png))
    image.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    image.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    image.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    shader = UsdShade.Shader(stage.GetPrimAtPath(f"{path}/shader"))
    shader.GetInput("diffuseColor").ConnectToSource(image.ConnectableAPI(), "rgb")


def light_intensity(diffuse) -> tuple[float, Gf.Vec3f]:
    peak = float(np.max(diffuse))
    if peak <= 0.0:
        return 0.0, Gf.Vec3f(1.0, 1.0, 1.0)
    return LIGHT_GAIN * peak, Gf.Vec3f(*(float(c) / peak for c in diffuse))


def dome_intensity(model) -> float:
    head = model.vis.headlight
    return DOME_GAIN * (float(np.mean(head.ambient)) + 0.5 * float(np.mean(head.diffuse)))


def _build_lights(stage: Usd.Stage, model, data, scene: SceneMap) -> None:
    UsdGeom.Xform.Define(stage, "/World/Lights")
    dome = UsdLux.DomeLight.Define(stage, scene.dome_path)
    dome.CreateIntensityAttr(dome_intensity(model))
    taken: set[str] = set()
    for light in range(model.nlight):
        name = _name(model.light(light).name, f"light_{light}", taken)
        path = f"/World/Lights/{name}"
        directional = int(model.light_type[light]) == int(mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)
        if directional:
            lux = UsdLux.DistantLight.Define(stage, path)
        else:
            lux = UsdLux.SphereLight.Define(stage, path)
            lux.CreateRadiusAttr(LIGHT_RADIUS)
            shaping = UsdLux.ShapingAPI.Apply(lux.GetPrim())
            shaping.CreateShapingConeAngleAttr(float(model.light_cutoff[light]))
            shaping.CreateShapingConeSoftnessAttr(0.3)
        intensity, color = light_intensity(model.light_diffuse[light])
        lux.CreateIntensityAttr(intensity)
        lux.CreateColorAttr(color)
        UsdLux.ShadowAPI.Apply(lux.GetPrim()).CreateShadowEnableAttr(bool(model.light_castshadow[light]))
        # USD lights shine down their -Z, like a MuJoCo light down its dir.
        _xform_ops(UsdGeom.Xformable(lux), data.light_xpos[light], _look_quat(data.light_xdir[light]))
        scene.light_paths[light] = path


def _look_quat(direction, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Quaternion taking local -Z onto ``direction``, local +Y toward ``up``."""
    forward = np.asarray(direction, dtype=float)
    forward = forward / (np.linalg.norm(forward) or 1.0)
    z = -forward
    up = np.asarray(up, dtype=float)
    if abs(float(z @ up)) > 0.999:
        up = np.array([0.0, 1.0, 0.0])
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return _mat_quat(np.column_stack([x, y, z]))


def _build_cameras(stage: Usd.Stage, model, data, scene: SceneMap) -> None:
    UsdGeom.Xform.Define(stage, "/World/Cameras")
    taken: set[str] = set()
    for cam in range(model.ncam):
        name = _name(model.camera(cam).name, f"camera_{cam}", taken)
        path = f"/World/Cameras/{name}"
        camera = UsdGeom.Camera.Define(stage, path)
        set_camera_fov(camera, float(model.cam_fovy[cam]))
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
        # A MuJoCo camera also looks down its -Z with +Y up.
        _xform_ops(camera, data.cam_xpos[cam], _mat_quat(data.cam_xmat[cam]))
        scene.camera_paths[model.camera(cam).name or name] = path


def set_camera_fov(camera: UsdGeom.Camera, fovy_deg: float, aspect: float = CAMERA_ASPECT) -> None:
    vertical = 2.0 * FOCAL_LENGTH * math.tan(math.radians(fovy_deg) / 2.0)
    camera.CreateFocalLengthAttr(FOCAL_LENGTH)
    camera.CreateVerticalApertureAttr(vertical)
    camera.CreateHorizontalApertureAttr(vertical * aspect)


def export(path: Path, model, data) -> SceneMap:
    """Write the stage to a .usda file (for a look in usdview or Isaac's GUI)."""
    stage = Usd.Stage.CreateNew(str(path))
    scene = build_stage(stage, model, data, texture_dir=path.parent / "textures")
    stage.GetRootLayer().Save()
    return scene
