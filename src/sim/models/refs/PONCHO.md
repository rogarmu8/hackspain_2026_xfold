# MuJoCo official garment flex reference (poncho)

Upstream (do not vendor the full point cloud here):
- https://github.com/google-deepmind/mujoco/blob/main/model/flex/poncho.xml
- https://github.com/google-deepmind/mujoco/blob/main/model/flex/poncho_edgeequality.xml

Extracted flexcomp settings used by XFOLD:

```xml
<option integrator="discrete" solver="CG" tolerance="1e-6"/>
<flexcomp … radius="0.01" dim="2" mass="1">
  <!-- poncho.xml -->
  <edge equality="vert" damping="0.1"/>
  <!-- poncho_edgeequality.xml -->
  <edge equality="true" damping="0.1"/>
  <elasticity young="3e5" poisson="0" thickness="8e-3" elastic2d="bend" damping="0.02"/>
  <contact solref="0.003"/>
</flexcomp>
```

Notes:
- Poncho is a cape on a mannequin, not a T-shirt — best **parameter** reference.
- Exact `young=3e5` + free fall is rank-deficient on our CLOTH3D mesh; use ~`1e3`
  bend elasticity (or edge-equality only) for the playground.
- CLOTH3D / ClothesNet supply T-shirt geometry; convert with
  `python -m xfold.convert_cloth3d_mesh <flat.obj>`. The converter keeps only the
  front panel: CLOTH3D shirts are closed tubes, and flattening both layers welds
  them into non-manifold edges. It also rewinds every triangle CCW — mixed winding
  is what renders half the shirt as black triangles.
- Drop-test tuning on this mesh: `solref="0.005 1.2"` + `solimp="0.99 0.999 0.0002"`
  plus `<default><joint damping="0.008"/>` gives rebound 0.043 m with the cloth
  resting at +6.6 mm (no floor clipping). Keep `timestep=0.002`; 0.004 triples the
  bounce. Keep edge `damping <= 0.5` or the cloth gains energy.
- Dual-mesh (physics mesh + high-res visual skin) is supported: `<skin>` takes
  `bone` subelements bound to bodies, and flexcomp creates one body per vertex,
  so a subdivided skin can be weighted onto them. `skin/inflate` also decouples
  rendered thickness from the collision `radius`. Not implemented yet — the
  current limit on looks is cloth thickness, not triangle count.
- Cleaned CLOTH3D flats used here:
  https://github.com/tlpss/synthetic-cloth-data (Cloth3D-5-flat-randomized-scale).
