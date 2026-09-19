# XFOLD — Automated shirt press + ninja fold line

THEKER Robotics · HackSpain '26 · Team reference

**One-line pitch:** a crumpled shirt is stretched onto a press by two OpenArm hands, ironed, folded with the Japanese / ninja method, then the press bed tips and the packet slides down a chute into a packaging bag — no human in the loop.

This document is the source of truth for the task, the technical approach, and what we reuse vs. build.

---

## 1. Why this task

Industrial folding machines already exist (Amscomatic K-950, NEDCO E-Z Fold, ROQ FOLD). They fold 600–1500 garments/hour **once the shirt is lying flat on the infeed**. The remaining human job is:

1. Pick a garment from a mixed / crumpled pile.
2. Spread it, collar/sleeves oriented, wrinkles down.
3. Fold it (or load a folder).
4. Drop the packet into a bag.

That station is still a person because the garment is deformable, overlapping, and unpredictably posed. THEKER’s brief is exactly this: variability that classical pick-and-place still fails at.

We do **not** invent a new folding machine. Two **Enactic OpenArm v2** arms (7-DOF × 2) do the human job: taut the shirt onto a press, then run the **Japanese / ninja t-shirt fold**. The **press bed itself** becomes the ejector: it lifts, and the packet slides down a chute into open packaging bags. Bags arrive pre-opened; we do not seal.

The ninja fold (the real two-hand method, not a FlipFold jig):

- Shirt is already flat on the platen (the press made that true).
- Left hand holds the crease line (mid-side + shoulder).
- Right hand takes the hem on the same line.
- One coordinated flip; sleeves disappear; result is a retail rectangle (~0.20 × 0.28 m).

That is a real human skill. OpenArm is a real dual-arm platform with a MuJoCo model. Together they score originality and hardware/realism without building a custom four-panel folder.

---

## 2. System at a glance

```
[bin of shirts] --bimanual taut--> [platen press] --ninja fold--> [tilt bed] --chute--> [bags]
  OpenArm L+R                      heated platen     OpenArm L+R     hinge + ramp     open poly bags
```

Four stations, one finite-state machine:

| Step | Station | Perceive | Decide | Execute |
|------|---------|----------|--------|---------|
| 1 | Bin → press | Shirt blob, two grasp points, orientation | Which corners, how far to taut | Both arms pick opposite regions, stretch, lay on the platen |
| 2 | Press | Shirt on plate, wrinkle height | Press long enough | Top platen comes down; optional “steam” relaxation. Arms clear. |
| 3 | Ninja fold | Shirt is flat, AABB vs platen | Crease line + hem | Dual-arm Japanese fold on the press; packet stays on the bed |
| 4 | Chute → bag | Packet on bed / in bag | Tilt far enough | Press bed lifts; shirt slides down the chute into a bag |

Autonomy target for the demo: **one full cycle, unattended, repeatable**. Stretch: N random initial poses / 2–3 sizes without rewriting the controller.

Live WOW: silence for one cycle, then a second shirt (new seed or size) with the same controller.

---

## 3. Design principles (so we finish)

1. **The press flattens, OpenArm folds, the bed ejects.** The robot is always dual-arm (L+R). Pick and taut use both hands. The ninja fold *targets* both hands; if they collide, we fall back to sequential creases with the idle arm parked — still the same two-handed robot, not a single-arm cell.
2. **Cloth is a 2D flex, not a rigid body.** MuJoCo 3 `flexcomp` is the shirt. Do not fake it with a box.
3. **No ROS, no RL, no ACT for the first working demo.** OpenArm’s Cartesian + bimanual stack + our FSM is enough. Skip Torch, SAC, ACT, webcam, catching.
4. **Arms stay on their own sides.** OpenArm’s stated limit: both arms over one centred object collide. Plan left-left / right-right; short height-offset flip only. No crossed-arm origami.
5. **Start rectangular, then become a T-shirt.** A grid cloth that irons and ninja-folds is a working product. A beautiful mesh that explodes is not.
6. **Fold only after the press.** A wrinkled ninja fold fails. The iron is what makes the Japanese method tractable in 48 h.
7. **Scripted cycle first.** Their `openarm cloth` demo is a **single-arm** corner fold on a dual-arm robot. We reuse the cloth + control stack; the two-hand Japanese fold on a pressed shirt is our skill. Do not train a policy until bin → bag works.

---

## 4. Open-source inventory

Verdict key: **USE** = copy into the repo · **ADAPT** = steal the idea, rewrite · **SKIP** = time sink · **INSPIRE** = citation / jury story.

### 4.1 Simulators

| Tool | Verdict | Why |
|------|---------|-----|
| **MuJoCo 3.x** (`pip install mujoco`) | **USE** | Chosen stack. Native cloth via `flexcomp`, adhesion or weld grasp, fast, Python-native. Docs: [mujoco.readthedocs.io](https://mujoco.readthedocs.io) |
| Isaac Sim / GarmentLab | SKIP | Better garments, but GPU + learning curve. Keep as “if MuJoCo cloth dies” fallback. |
| Gazebo / ROS 2 | SKIP for MVP | Extra middleware. |

### 4.2 Dual-arm platform — [openarm-control](https://github.com/Manas-arumalla/openarm-control)

Enactic OpenArm v2, 7-DOF × 2 + grippers, Apache-2.0. Cite Enactic for the MJCF and Manas-arumalla for the control package. **Do not `pip install -e ".[all]"`** — that pulls Torch, SAC, ACT, webcam. Vendor only what the cell needs.

| Resource | Verdict | Notes |
|----------|---------|-------|
| `v2/openarm_mujoco_v2/openarm_v20_bimanual.xml` + meshes | **USE** | Untouched upstream model. Attach our press/chute/bag around it. |
| `openarm_control/kinematics.py` | **USE** | FK + robust LM IK. Replaces mink for this robot. |
| `openarm_control/controller.py` | **USE** | Resolved-rate Cartesian control. |
| `openarm_control/trajectory.py` | **USE** | Quintic paths for pick / taut / fold. |
| `openarm_control/bimanual.py` | **ADAPT** | Parallel motion, sync, collision-aware hand-off on the **dual-arm** model. We add a `NinjaFoldTask`. |
| `openarm_control/cloth.py` | **ADAPT** | 9×9 self-colliding flex + grasp-on-cloth; their demo fold is **one arm** only (**44 %** span reduction). Steal flex/grasp; rewrite motion as Japanese creases (prefer both hands; sequential OK). |
| `openarm_control/grasp.py` / weld-on-grasp | **ADAPT** | Their grasps are MuJoCo equality welds (they say so). Fine for a hackathon if we label it. Prefer **adhesion pads** on the fingertips if welds look fake. |
| `openarm_control/contact/` admittance | **ADAPT** | Optional for the press wipe / crease. Skip if time. |
| Catching, throwing, ACT, SAC, language agent, webcam mimic, YOLO | **SKIP** | Impressive, not our task. |
| mink + MuJoCo Menagerie UR5e | **SKIP** as primary | OpenArm *is* the robot. Still listed in `pixi.toml` `mujoco` feature as a nuclear single-arm fallback only. |

**Collision rule we inherit from them:** two close-mounted 7-DOF arms collide when both reach over one centred object. So:

- **Spread:** left grabs left region, right grabs right region — well separated. This is what their bimanual is good at.
- **Ninja:** left stays on the left crease, right on the hem/right crease. No arm crosses the midline except a brief, height-offset flip.
- **Fallback** if they still collide: sequential creases (left, then right, then hem) with the idle arm parked. Still two arms, still the Japanese geometry, still a complete cycle.

### 4.3 Cloth / garment simulation

| Resource | Verdict | Notes |
|----------|---------|-------|
| MuJoCo `flexcomp` 2D cloth | **USE** | Start from OpenArm’s 9×9 self-colliding cloth, then coarsen if it explodes. |
| **Contact budget: `mjMAXCONPAIR` = 50** | **CONSTRAINT** | See below. Sets the vertex count, so decide it before anything else. |
| Bundled flex models (`flag.xml`, `poncho.xml`, …) | **USE** | Poncho is the closest garment-shaped **param** reference (`refs/PONCHO.md`). |
| Elasticity shell plugin `mujoco.elasticity.shell` | SKIP (3.13 pip) | Only `cable` is registered; use native `<elasticity>` (discrete) or edge equality. |
| CLOTH3D / ClothesNet T-meshes | **USE** | Geometry only — convert with `xfold.convert_cloth3d_mesh` → `shirt_cloth3d.obj`. |
| [Issue #1433 — Shirt/Cloth with flexcomp](https://github.com/google-deepmind/mujoco/issues/1433) | **USE** | Tunings that stop explosions: `internal="false"`, Young ~`1e3–5e3`, damping `1–10`. |
| ICARSC 2026 *Clothing Simulation in MuJoCo* | INSPIRE | Cite on the slide. |

#### The contact budget decides the mesh density

MuJoCo caps **one geom pair at 50 contacts** (`mjMAXCONPAIR`), and an entire
flex against the floor counts as a single pair. A 20×20 grid resting flat has
394 vertices touching and still gets exactly 50 contacts — raising `nconmax`,
`margin` or splitting the floor into tiles changes nothing.

Everything above that ceiling is unsupported. Measured on the 365-vertex shirt:
363 vertices lay on the floor competing for 50 slots, 82 of them hung through
the plane (the “floor overlap”), and because the solver picks a different 50
each step the sheet never stopped moving — a 7.3 Hz ripple, 9.4 mm
peak-to-peak, that no amount of `solref`, `solimp`, friction, `impratio`,
`noslip`, edge damping or elasticity tuning removed. Only the vertex count did.

| Physics verts | Resting ripple | Verts through floor | Real-time factor |
|---|---|---|---|
| 385 | 1.6 mm | 82 | 0.42x |
| 207 | 0.4 mm | 0 | 0.61x |
| **161 (default)** | **0.15 mm** | **0** | **1.1x** |

So 161 vertices is not a compromise on looks, it is the physics budget — and it
lands inside the range §4.3 already called for (OpenArm’s 9×9 = 81, “12×16 is
plenty” = 192). Consequences for the rest of the build:

- **Two knock-on fixes:** the solver is `CG`, not Newton (~2x faster on an
  equality-heavy flex), and there is **no** `<joint damping>` on the cloth. DOF
  damping is absolute-frame drag: at 0.008 it stretched free fall by 1.5x,
  which is what read as a heavy object in slow motion.
- **Folding is the open risk.** Cloth-on-cloth is its own pair with its own
  50-contact cap. A three-layer ninja packet may exceed it and let layers
  interpenetrate. Test at block 5 before trusting the fold.
- The `flatness` metric (§8) is only meaningful below the ripple floor. At 385
  verts the cloth wobbles 1.6 mm at rest, so “the press flattened it” is not
  measurable; at 161 the noise floor is 0.15 mm.

#### Looking like cloth is shading, not triangles

The “it looks like slime” feedback survived every physics fix and went away
with a material change. A saturated `rgba` under MuJoCo’s default specular
gives wet-looking highlights that also wash out the folds. Use a matte,
desaturated `<material specular="0.02" shininess="0.01">` and a low-specular
headlight. Cube textures render white on a flex, so the fabric read has to come
from shading. Also drop `radius` to 0.004: a 2D flex draws as a slab of
half-thickness `radius`, and 0.008 was a 16 mm yoga mat.

**Working shirt XML to start from** (grid, not a mesh):

```xml
<extension>
  <plugin plugin="mujoco.elasticity.shell"/>
</extension>

<worldbody>
  <flexcomp name="shirt" type="grid" dim="2" count="16 20 1"
            spacing="0.03 0.03 0.03" radius="0.004" mass="0.2"
            pos="0 0 0.4" rgba="0.15 0.25 0.55 1">
    <contact internal="false" selfcollide="none" solref="0.004" condim="3"/>
    <edge equality="true" damping="1"/>
    <plugin plugin="mujoco.elasticity.shell">
      <config key="young" value="5e3"/>
      <config key="poisson" value="0"/>
      <config key="thickness" value="0.004"/>
    </plugin>
  </flexcomp>
</worldbody>
```

If this diverges: lower Young, raise damping, disable internal contacts, reduce `count`. OpenArm’s 9×9 is a proven foldable sheet; a 12×16 grid is plenty for a shirt demo.

T-shirt shape later: generate a T-outline mesh in Python (or a low-poly OBJ) and switch `type="mesh" file="shirt.obj"`. Same contact/elasticity block as above.

### 4.4 Mechanisms we build ourselves (no good OSS)

There is no open ninja-fold cell. There is no open shirt-press-plus-chute. These plus the two-hand Japanese fold are what the jury should remember:

1. **Press station** — bottom bed + descending top platen. “Hot air / steam” is **not** thermal physics (MuJoCo has none). Model it as:
   - Downward platen contact (ironing).
   - Optional: while pressed, temporarily raise cloth damping / lower Young so wrinkles relax (“steam”).
2. **Tilting press bed** — hinge on the chute-side edge. After the fold, the bed lifts (~40–60°) so the packet slides off.
3. **Chute** — rigid ramp from the press lip down to the bag mouth. Low-friction geom. Side walls so the packet does not fall off.
4. **Packaging bags** — open-top poly bags at the foot of the chute. Success = shirt AABB inside a bag. Pre-opened; no sealer.

`model/flex/press.xml` in MuJoCo: steal contact/solver ideas, not the geometry.

### 4.5 Perception

In MuJoCo we cheat honestly and then replace:

| Signal | MVP | Stretch |
|--------|-----|---------|
| Shirt pose | Flex vertex positions (`data.flexvert_*`) | RGB-D camera in MJCF |
| Grasp points | Two extrema of the top layer (left/right) | Depth peaks + normals |
| Stretch quality | XY AABB vs shirt rest size | Same, shown live |
| Flatness | Variance of vertex z | Same, shown live |
| On-bed / in-bag | AABB of vertices vs station volumes | Camera classifier |

A top-down camera (`<camera/>` + `mujoco.Renderer`) is enough for the “we perceive” story. Do not train YOLO / ACT unless the pipeline already runs from ground-truth vertices.

---

## 5. Station design

### Station 1 — Bimanual pick and taut

**Scene:** open crate, 1 shirt (MVP) or 2–3 (stretch), crumpled by dropping it in at reset. OpenArm torso behind the press, bin to one side so both arms can reach without crossing.

**Motion:**

1. Both arms hover over the bin, one on each half of the shirt.
2. Grasp interior vertices (avoid edges so the cloth does not dribble off).
3. Lift and **taut** — increase the distance between the two grippers until the XY span is close to rest size.
4. Lay onto the press bed, more or less stretched. A short wipe along the platen helps.
5. Retract clear of the descending platen.

**Failure modes:** shirt sticks to crate, arms collide, miss the platen. Mitigations: low-friction crate, keep arms on their halves, then **the press finishes flattening**. Step 1 does not need a perfect spread — “more or less stretched” is the spec.

### Station 2 — Press / “hot air”

**Scene:** bottom bed the size of a shirt. Top platen on a vertical slider. Arms parked outside the press envelope.

**Sequence:** lower platen → hold 1–2 s (steam relaxation) → raise platen. Shirt stays on the bed.

```python
def set_steam(model, on: bool):
    model.flex_edgedamping[:] = 10.0 if on else 1.0
```

Heat + moisture lowers fabric bending stiffness. Say so on the slide. Not thermodynamics.

### Station 3 — Japanese / ninja fold (two hands, on the press)

The shirt is already ironed. That is the only reason this fold is demoable. Always crease **against the platen**.

**Target sequence (true ninja, both grippers):**

1. Left arm pinches the crease line (mid-height, left third). Right arm pinches the same line at the hem.
2. Coordinated lift-and-flip so the left third lands on the centre. Pause.
3. Mirror for the right third (roles swap, still no midline cross).
4. Hem up toward the collar (both arms, or one folds while the other parks).
5. Packet settles on the bed.

**Fallback sequence** (if the coordinated flip collides): left third → right third → hem, same Japanese geometry, **one gripper active at a time**. The other arm stays parked. The platform is still dual-arm; only the fold motion is serialized. Document that as an obstacle we solved, not a downgrade to a one-arm cell.

Do not fold in free space.

### Station 4 — Tilt, chute, bag

```
press bed hinge at the chute-side edge, 0 → ~50°
chute: ~0.6–0.9 m ramp, ~35° down, side walls 4 cm
bag mouth at the foot, opening ~0.25 × 0.18 m
```

After the fold:

1. Top platen is already up; arms are clear.
2. Bed hinge drives to the dump angle.
3. Packet slides onto the chute and into an open bag.
4. Bed returns to horizontal for the next cycle.

Slightly sticky bed while folding, lower friction on dump. Bags are pre-opened; we do not bag-seal.

---

## 6. Software architecture

Monorepo (moon + npm workspaces). Commands: see [README.md](README.md).

```
src/sim/
  models/
    cell.xml              # press, chute, bag, bin (rigid stub)
    openarm/              # vendored OpenArm v2 MJCF + meshes (next)
  src/xfold/
    fsm.py                # PICK → SPREAD → PRESS → FOLD → CHUTE → BAG
    telemetry.py
    mock_cycle.py
    scene.py              # MjSpec: OpenArm bimanual + our cell
    shirt.py              # flexcomp factory
    ninja.py              # crease points + dual-arm fold script
    control/              # OpenArm IK / Cartesian / bimanual wrapper
src/dashboard/
packages/protocol/
.moon/
```

**Control style:** hybrid.

- Machines: joint position setpoints (platen slider, bed hinge).
- Arms: OpenArm resolved-rate Cartesian + LM IK, one Cartesian target per hand. Collision check between left and right upper arms before every coordinated move.
- Grasp: weld (OpenArm default) or adhesion pads; open/close `ctrl` 0/1.

**Loop:** `mj_step` at 500 Hz physics, FSM at ~50 Hz, IK inner iterate per control tick.

Do **not** put the FSM inside XML. XML is the plant. Python is the cell controller.

Vendor OpenArm as a copy or git submodule under `src/sim/models/openarm` + a thin Python wrapper. We do not take their CLI, RL/ACT extras, or showcase demos into the demo path.

---

## 7. Variability we commit to

| Axis | MVP (must) | Stretch (valued) |
|------|------------------|------------------|
| Initial pose | Random yaw, small crumple from a drop | Fully wadded, overlapping pile |
| Shirt size | One adult T | S / M / L via `shirt.py` spacing/count |
| Shirt shape | Rectangle cloth | T-mesh (sleeves) |
| Colour / texture | One | Two colours (visual only) |
| Scene | Fixed cell | Slight press/chute offset |

Generalization story: **the FSM and metrics are garment-agnostic**. Size enters as “bounding box vs platen and bag mouth”. If the shirt is too wide for the bag, we fail visibly and log it — that is still a system.

We will not claim pants, towels, or collared shirts unless we actually run them.

---

## 8. Metrics (Axis B — iteration with numbers)

Log every cycle to CSV from hour one of a working loop.

| Metric | Definition | Target |
|--------|------------|--------|
| `success` | Shirt AABB inside a bag at t_end | > 80% on 20 trials |
| `cycle_time_s` | Pick start → bag | Measure; improve |
| `flatness` | std(z) of vertices after press | Lower than pre-press |
| `span_ratio` | XY span after SPREAD / rest span | Closer to 1 after taut |
| `fold_error` | \|final AABB − 0.20×0.28 m\| | Small |
| `grasp_fail` | Grasp lost during pick or fold | Count |
| `arm_collision` | Left/right geom contact during cycle | 0 on demo seeds |
| `on_bed` | Centroid over press after SPREAD | Binary |
| `in_bag` | Centroid inside bag after CHUTE | Binary |

Show: **flatness before vs after press**, **span_ratio after taut**, **success vs trial index**.

Reset protocol: drop the shirt from a random pose above the bin, wait 0.5 s, then run. Same seed list for A/B of controller versions.

---

## 9. Build order (hackathon)

Do not mount both arms on the shirt until the cloth and the press exist.

| Block | Hours | Done when |
|-------|-------|-----------|
| **0. Empty cell** | 1 | Floor, lights, bin, press, tilt bed, chute, bags. Rigid only. `moon run sim:view` opens. |
| **1. Shirt lives** | 2 | Grid cloth drops, stays stable 10 s. Steal OpenArm `cloth.py` tunings if needed. |
| **2. Press flattens a wrinkled shirt** | 2 | `flatness` drops. Steam damping if needed. **First demo-able clip.** |
| **3. OpenArm in the cell** | 2 | Bimanual MJCF attached, both arms IK to parked poses, no explosion. |
| **4. Bimanual taut onto the press** | 2 | Two-handed pick + stretch; `span_ratio` improves. |
| **5. Ninja fold on a pre-laid shirt** | 3 | Dual-arm Japanese fold (fallback: sequential). Packet on the bed. |
| **6. Tilt + chute** | 1 | Bed dumps; packet in a bag. |
| **7. Full FSM** | 3 | Bin → bag, no keyboard. |
| **8. Randomization + metrics** | 2 | `eval.py`, CSV, one chart. |
| **9. T-shirt mesh / second size** | leftover | Only after 7 works. |
| **10. Slide + backup video** | last 2 | One slide, 30–60 s video. Physical chute + bags on the table. |

Hard gates:

- Cloth exploding after block 1 → coarsen the grid, do not add arms.
- Arms colliding in block 5 → sequential ninja, do not debug a dual-arm planner overnight.

---

## 10. Risks

| Risk | Likelihood | Mitigation |
|------|------------|-----------|
| Flex explodes or tunnels | High | Coarser grid, `internal=false`, smaller Young, `implicitfast` |
| OpenArm dual-arm collides on a centred shirt | High | Side-staying ninja; sequential fallback |
| Weld grasp looks fake / pops | Medium | Larger contact; switch to adhesion pads |
| Stretch leaves a crumpled heap | Medium | Two-hand taut; press finishes flattening |
| Ninja fold unfolds mid-crease | High | Fold only after press; crease against the bed; pause |
| Packet unfolds on the chute | Medium | Dump after settle; side walls; short steep chute |
| OpenArm vendor pull is huge | Medium | Copy MJCF + kinematics/controller/bimanual/cloth only |
| Too slow for live demo | Medium | Backup video; live run with one known seed |

Nuclear fallback: **mocap pads + scripted machines**, no arms. Worse story, complete cycle still beats a broken dual-arm.

---

## 11. Jury mapping

**Axis A — vision**

- Real bottleneck: crumpled shirt → flat bagged packet. Folding machines exist; the person is still there.
- Original move: two OpenArm hands taut onto a press, Japanese / ninja fold on the iron, tilting bed, chute into bags.
- Obstacles we expect to show: cloth stability, dual-arm collision on a centred garment, crease rebound, dump unfolding — and the changes that fixed them.

**Axis B — depth**

- Variability: deformable object + pose + (stretch) size.
- Autonomy: FSM, no teleop.
- Metrics: flatness, span ratio, fold error, success, collisions, cycle time.
- Generalization: size as a parameter of `shirt.py`, same controller. Second cycle live.
- Hardware: OpenArm is a real **dual-arm** platform; press + chute + open bags on the table. Sequential fold fallback still counts as dual-arm.

**One slide should contain:**

1. Photo of the human task (crumpled pile / person doing the ninja fold into a bag).
2. 4-station diagram (bimanual taut → press → ninja fold → chute/bag).
3. One metric chart (flatness or success).
4. Variability we handle vs. what we do not. Credit: OpenArm v2 (Enactic) + openarm-control.

---

## 12. Dependencies (MVP)

Root: Pixi (`pixi.toml`) pins Python 3.12 + Node 22. Moon runs tasks.

Sim (Pixi env `mujoco` via `moon run install-mujoco`):

```text
python >= 3.12
numpy
mujoco >= 3.2
# still in pixi as fallback only — not the demo robot:
mujoco-menagerie
mink
```

Vendored next (not a Pixi extra until we copy it): OpenArm v2 MJCF (Enactic) + `openarm_control` kinematics / controller / trajectory / bimanual / cloth (Apache-2.0).

Dashboard: Next.js 16. Protocol package is TypeScript-only.

No ROS, no CUDA, no Isaac, no `pip install -e ".[all]"` on openarm-control. Viewer: `moon run sim:view`. On macOS, prefer `python` over `mjpython` (the latter crashed in this repo).

---

## 13. What we will not do

- Dual-arm origami in free space, or arms crossing over the shirt.
- Simulate real thermodynamics of an iron.
- Train RL / ACT / YOLO before a scripted cycle works.
- Pull catching, throwing, language skills, or webcam mimic from OpenArm.
- Port MELFA into MuJoCo during the hackathon.
- Promise pants, towels, and collared shirts on day one.
- Seal bags.

Those can be “next” on the slide. The demo is one shirt, bin to bag, on a **dual-arm OpenArm**, every time.
