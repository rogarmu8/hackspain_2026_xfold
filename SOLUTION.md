# XFOLD — Automated shirt press + fold line

THEKER Robotics · HackSpain '26 · Team reference

**One-line pitch:** a crumpled shirt leaves a bin, gets pressed flat, drops onto a FlipFold-style folder, and is packed into a box — no human in the loop.

This document is the source of truth for the task, the technical approach, and what we reuse vs. build.

---

## 1. Why this task

Industrial folding machines already exist (Amscomatic K-950, NEDCO E-Z Fold, ROQ FOLD). They fold 600–1500 garments/hour **once the shirt is lying flat on the infeed**. The remaining human job is:

1. Pick a garment from a mixed / crumpled pile.
2. Spread it, collar/sleeves oriented, wrinkles down.
3. Load the folder.
4. Pack the folded piece.

That load station is still a person because the garment is deformable, overlapping, and unpredictably posed. THEKER’s brief is exactly this: variability that classical pick-and-place still fails at.

We do **not** try to origami-fold cloth with robot fingers. Retail and fulfilment already solved folding with a jig. We automate the jig, the press, the transfer, and the packing.

The folding board in the brief is a FlipFold:

- Open: ~24" × 27"
- Closed fold: ~9" × 12" rectangle
- Sequence: left flap → right flap → bottom flap

That is a real, cheap, physical terminal. It scores the hardware/realism extra points and is simulable in MuJoCo as four hinged panels.

---

## 2. System at a glance

```
[bin of shirts] --pick--> [hot-air / platen press] --drop--> [FlipFold] --peel--> [output box]
     arm + suction              heated platen              4 hinged flaps         pizza-peel spatula
```

Four stations, one finite-state machine:

| Step | Station | Perceive | Decide | Execute |
|------|---------|----------|--------|---------|
| 1 | Bin → press | Shirt blob, grasp point, orientation | Where to grab, how to drop | Arm + suction/spatula places shirt on platen |
| 2 | Press | Shirt on plate, wrinkle height | Press long enough | Top platen comes down; optional “steam” relaxation |
| 3 | Transfer | Shirt is flat | Retract floor | Press floor slides out; shirt falls onto folder |
| 4 | Fold + pack | Shirt centred on board | Flap sequence + peel path | FlipFold folds; peel slides under and dumps into box |

Autonomy target for the demo: **one full cycle, unattended, repeatable**. Stretch: N random initial poses / 2–3 sizes without rewriting the controller.

---

## 3. Design principles (so we finish)

1. **Machines do geometry, the robot does variability.** Press and FlipFold are scripted mechanisms. The arm only handles the parts that change (pick, place, pack).
2. **Cloth is a 2D flex, not a rigid body.** MuJoCo 3 `flexcomp` is the shirt. Do not fake it with a box.
3. **No ROS for the first working demo.** Mink + Menagerie + a Python FSM is enough. ROS/MoveIt is a day of glue.
4. **No RL unless the scripted pipeline already works.** Judges score end-to-end autonomy and measured iteration, not a training curve on a broken scene.
5. **Start rectangular, then become a T-shirt.** A grid cloth that irons and folds is a working product. A beautiful mesh that explodes is not.

---

## 4. Open-source inventory

Verdict key: **USE** = copy into the repo · **ADAPT** = steal the idea, rewrite · **SKIP** = time sink · **INSPIRE** = citation / jury story.

### 4.1 Simulators

| Tool | Verdict | Why |
|------|---------|-----|
| **MuJoCo 3.x** (`pip install mujoco`) | **USE** | Chosen stack. Native cloth via `flexcomp`, adhesion (suction), fast, Python-native. Docs: [mujoco.readthedocs.io](https://mujoco.readthedocs.io) |
| Isaac Sim / GarmentLab | SKIP | Better garments, but GPU + learning curve. Keep as “if MuJoCo cloth dies” fallback. [garmentlab.github.io](https://garmentlab.github.io) |
| Gazebo / ROS 2 | SKIP for MVP | Extra middleware. Only if we later want MELFA/MoveIt. |

### 4.2 Cloth / garment simulation (the risky part)

| Resource | Verdict | Notes |
|----------|---------|-------|
| MuJoCo `flexcomp` 2D cloth | **USE** | Official replacement for deprecated `composite cloth`. Types: `grid` (start here) and `mesh` (T-shirt OBJ later). |
| Bundled flex models in `google-deepmind/mujoco` `model/flex/` | **USE** | Copy parameters from `flag.xml`, `hammock.xml`, `trampoline.xml`, `pinch.xml`, `poncho.xml`. Poncho is the closest garment-shaped example. |
| Elasticity shell plugin `mujoco.elasticity.shell` | **USE** | Young / Poisson / thickness for cloth bending. |
| [Issue #1433 — Shirt/Cloth with flexcomp](https://github.com/google-deepmind/mujoco/issues/1433) | **USE** | Exact T-shirt XML and the tunings that stop it exploding: `internal="false"`, Young ~`5e3`, damping `1–10`. |
| ICARSC 2026 paper *Clothing Simulation in MuJoCo* | INSPIRE | Extends rectangular cloth macros to arbitrary T-shirt meshes; sim-to-real comparison. Cite on the slide. |
| [hietalajulius/dynamic-cloth-folding](https://github.com/hietalajulius/dynamic-cloth-folding) | SKIP | IROS 2022, **MuJoCo 2.1 + old composite cloth**, CUDA 11.6. Idea only: visual feedback fold. |
| SoftGym / PyFleX, Isaac GarmentLab | SKIP | Different engine. |
| `navigator8972/gripper_cloth_envs`, `BOBaraki/cloth-manipulation` | SKIP | Pre-MuJoCo-3, mujoco-py. |

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

If this diverges: lower Young, raise damping, disable internal contacts, reduce `count`. A 12×16 grid is plenty for a demo.

T-shirt shape later: generate a T-outline mesh in Python (or a low-poly OBJ) and switch `type="mesh" file="shirt.obj"`. Same contact/elasticity block as above.

### 4.3 Robots, grippers, IK

| Resource | Verdict | Notes |
|----------|---------|-------|
| [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) / `pip install mujoco-menagerie` | **USE** | Ready MJCF arms. Recommended: **UR5e** (reach, industrial look) or **Panda**. Attach gripper via `MjSpec.attach`. |
| Robotiq 2F-85 (Menagerie) | ADAPT | Fine for pinch, worse than suction for cloth. Keep as backup. |
| **Adhesion actuator** | **USE** | Official vacuum. Example: [`model/adhesion/active_adhesion.xml`](https://github.com/google-deepmind/mujoco/tree/main/model/adhesion). `<adhesion name="vacuum" body="peel_pad" ctrlrange="0 1" gain="20"/>` plus `gap` on the pad geom for suction-at-a-distance. |
| [mink](https://github.com/kevinzakka/mink) | **USE** | Differential IK on MuJoCo, joint limits, collision avoidance. Copy `examples/arm_ur5e.py` / `arm_ur5e_actuators.py`. |
| Pinocchio | SKIP | Mink already sits on MuJoCo. |
| MELFA ROS 2 driver | SKIP for sim MVP | URDF + MoveIt, not MJCF. Only if we want sponsor hardware later. Conversion via `mujoco_ros2_control` is extra days. |
| MoveIt 2 | SKIP | Mink covers Cartesian motion for a scripted cell. |

**End-effector choice:** a **pizza-peel / transfer blade** with a suction pad on the underside.

- Thin box geom = peel.
- Child body with a disc + `adhesion` = vacuum.
- Same tool for bin pick (step 1) and box pack (step 4). One tool, two uses, original, hardware-coherent.

Pinch grippers fight cloth. Suction + a blade is how bakeries and some garment baggers already transfer flats.

### 4.4 Mechanisms we build ourselves (no good OSS)

There is no open FlipFold MJCF. There is no open shirt-press cell. These are our original assets and what the jury should remember:

1. **Press station** — bottom plate + descending top platen. “Hot air / steam” is **not** thermal physics (MuJoCo has none). Model it as:
   - Downward platen contact (ironing).
   - Optional: while pressed, temporarily raise cloth damping / lower Young so wrinkles relax (“steam”).
   - Optional visual: translucent force field / particles. Skip if it costs time.
2. **Retractable floor** — slide joint on the press base so the shirt falls onto the folder.
3. **FlipFold** — four panels, hinge joints, position actuators, hole pattern as visual cylinders (can be cosmetic). Sequence: left → right → bottom. Living hinges ≈ hinge joints with limits `0 → π`.
4. **Output box** — simple open-top box; peel dumps the folded shirt in.

`model/flex/press.xml` is a soft-body press example (3D flex vs 3D flex). Steal contact/solver ideas, not the geometry.

### 4.5 Perception

In MuJoCo we can cheat honestly and then replace:

| Signal | MVP | Stretch |
|--------|-----|---------|
| Shirt pose | Flex vertex positions (`data.flexvert_*`) | RGB-D camera in MJCF |
| Grasp point | Highest vertex / centroid of top 10% | Depth peak + normal |
| Flatness | Variance of vertex z | Same, shown live |
| On-folder / in-box | AABB of vertices vs station volumes | Camera classifier |

A top-down camera (`<camera/>` + `mujoco.Renderer`) is enough for the “we perceive” story. Do not train a detector unless the pipeline already runs from ground-truth vertices.

---

## 5. Station design

### Station 1 — Bin pick and lay-flat

**Scene:** open crate, 1 shirt (MVP) or 2–3 (stretch), slightly crumpled by dropping it in at reset.

**Motion:**

1. Hover over bin.
2. Grasp = suction on a high, interior vertex (avoid edges so the shirt does not dribble off).
3. Lift, translate over press, lower, release with a small lateral wipe so it spreads.
4. Retract.

**Failure modes:** shirt sticks to crate, folds on itself, misses the platen. Mitigations: crate walls with low friction, wipe motion, then **the press is allowed to finish the flattening**. Step 1 does not need a perfect spread.

### Station 2 — Press / “hot air”

**Scene:** bottom plate the size of a shirt. Top platen on a vertical slider.

**Sequence:** lower platen → hold 1–2 s (apply steam relaxation) → raise platen.

**Steam model (one function):**

```python
def set_steam(model, on: bool):
    # flex edge damping / elasticity — indices filled at load time
    model.flex_edgedamping[:] = 10.0 if on else 1.0
```

That is a legitimate engineering abstraction: heat + moisture lowers fabric bending stiffness. Say so on the slide.

### Station 3 — Drop onto folder

Press floor is a slide joint. Retract it; shirt falls ~5–15 cm onto the FlipFold, which sits directly below, centred.

Keep the drop short so the shirt does not re-crumple. In a real cell this is a transfer belt; a disappearing floor is the MuJoCo-simple version of “the conveyor base is removed”.

### Station 4 — FlipFold + pizza-peel pack

**Kinematics (adult FlipFold, metres):**

```
left flap (0.22 x 0.60)  |  upper centre (0.24 x 0.30)
                         |  lower centre (0.24 x 0.30)   <- folds up last
right flap (0.22 x 0.60) |
```

Hinge axes along the long inner edges. Actuate with `<position>` actuators, 0.4–0.6 s per flap, pause so cloth settles.

After the fold:

1. Open the side flaps just enough, or peel under the centre panel (slot / gap under the board).
2. Suction on, slide peel under the packet, lift, dump in box, suction off.

A 2–3 mm gap under the centre panel, or a slightly raised board on feet (the real FlipFold has bumpers), makes the peel physically honest.

---

## 6. Software architecture

```
xfold/
  models/           # MJCF: scene, shirt, press, folder, peel, box
  robots/           # Menagerie overlays / attached UR5e
  xfold/
    scene.py        # MjSpec assembly
    shirt.py        # flexcomp factory (size variants)
    control/
      fsm.py        # states: PICK, PLACE, PRESS, DROP, FOLD, PACK, RESET
      ik.py         # mink wrapper
      machines.py   # press / folder / floor setpoints
    perceive.py     # vertices → grasp, flatness, in-box
    metrics.py      # logged every cycle
  scripts/
    demo.py         # viewer loop
    eval.py         # N randomized trials, no viewer
  data/             # csv logs for the slide
```

**Control style:** hybrid.

- Machines: joint position setpoints (trivial).
- Arm: mink `FrameTask` on peel tip + `PostureTask` + `ConfigurationLimit`. Optional collision pairs: peel vs press frame, arm vs bin.
- Suction: `data.ctrl[adhesion_id] = 0 or 1`.

**Loop:** `mj_step` at 500 Hz physics, FSM at ~50 Hz, mink inner iterate 5–20 times per control tick (copy mink UR5e example).

Do **not** put the FSM inside XML. XML is the plant. Python is the cell controller.

---

## 7. Variability we commit to

Be explicit; the jury grades this.

| Axis | MVP (must) | Stretch (valued) |
|------------------|------------------|
| Initial pose | Random yaw, small crumple from a drop | Fully wadded, overlapping pile |
| Shirt size | One adult T | S / M / L via `shirt.py` spacing/count |
| Shirt shape | Rectangle cloth | T-mesh (sleeves) |
| Colour / texture | One | Two colours (visual only) |
| Scene | Fixed cell | Slight press/folder offset |

Generalization story: **the FSM and metrics are garment-agnostic**. Size enters as “bounding box vs FlipFold panel size”. If the shirt is too wide, we fail visibly and log it — that is still a system.

We will not claim arbitrary garment categories (pants, towels) unless we actually run them.

---

## 8. Metrics (Eje B — iteration with numbers)

Log every cycle to CSV from hour one of a working loop.

| Metric | Definition | Target |
|--------|------------|--------|
| `success` | Shirt AABB inside the box at t_end | > 80% on 20 trials |
| `cycle_time_s` | Pick start → box | Measure; improve |
| `flatness` | std(z) of vertices after press | Lower than pre-press |
| `fold_error` | \|final AABB − 0.23×0.30 m\| | Small |
| `grasp_fail` | Suction lost during transfer | Count |
| `on_folder` | Centroid over FlipFold after drop | Binary |

Show a plot: **flatness before vs after press**, and **success rate vs trial index**. That is the “measured iteration” bullet.

Reset protocol: drop the shirt from a random pose above the bin, wait 0.5 s, then run. Same seed list for A/B of controller versions.

---

## 9. Build order (hackathon)

Do not build all four stations in parallel until station 0 exists.

| Block | Hours | Done when |
|-------|-------|-----------|
| **0. Empty cell** | 1 | Floor, lights, bin, press plates, FlipFold panels, box. Rigid only. Viewer opens. |
| **1. Shirt lives** | 2 | Grid cloth drops, stays stable 10 s, collides with floor. |
| **2. FlipFold folds a pre-laid shirt** | 2 | Scripted flaps produce a packet. **First demo-able clip.** |
| **3. Press flattens a wrinkled shirt** | 2 | `flatness` drops. Steam damping trick if needed. |
| **4. Drop transfer** | 1 | Retract floor, shirt lands on folder, still foldable. |
| **5. Arm + peel + suction** | 3 | UR5e from Menagerie, mink to mocap target, adhesion lifts cloth. |
| **6. Full FSM** | 3 | Bin → box, no keyboard. |
| **7. Randomization + metrics** | 2 | `eval.py`, CSV, one chart. |
| **8. T-shirt mesh / second size** | leftover | Only after 6 works. |
| **9. Slide + backup video** | last 2 | One slide, 30–60 s video. |

Hard gate: if cloth is still exploding after block 1, shrink the grid, do not add the arm.

---

## 10. Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Flex explodes or tunnels | High | Coarser grid, `internal=false`, smaller Young, implicit integrator `implicitfast` |
| Suction does not grab flex verts | Medium | Larger pad, bigger `gap`, weld a proxy vertex body if needed |
| Shirt re-crumples on drop | Medium | Short drop, slightly sticky folder surface while landing |
| Mink fights the peel orientation | Medium | Position-only task (`orientation_cost=0`) for pick |
| Full T-shirt mesh is unstable | High | Stay rectangular; add sleeves as a second flex or a T-grid |
| Too slow for live demo | Medium | `eval.py` video as backup; live run with one known seed |

Nuclear fallback (still a valid THEKER demo): **no arm**. Scripted suction mocap body + machines. Worse story, but a complete cycle beats a broken Panda.

---

## 11. Jury mapping

**Eje A — vision**

- Real bottleneck: loading and packing around existing folders, not inventing cloth origami.
- Original move: press + disappearing floor + FlipFold + shared pizza-peel tool.
- Obstacles we expect to show: cloth stability, suction-on-flex, drop re-wrinkling — and the parameter / mechanism changes that fixed them.

**Eje B — depth**

- Variability: deformable object + pose + (stretch) size.
- Autonomy: FSM, no teleop.
- Metrics: flatness, success, cycle time.
- Generalization: size as a parameter of `shirt.py`, same controller.
- Hardware: FlipFold terminal + peel, physically plausible.

**One slide should contain:**

1. Photo of the human task (pile of shirts / operator at a folder infeed).
2. 4-station diagram.
3. One metric chart (flatness or success).
4. Variability we handle vs. what we do not.

---

## 12. Dependencies (MVP)

```text
python >= 3.11
mujoco
mujoco-menagerie
mink
numpy
matplotlib   # plots for the slide
```

No ROS, no CUDA, no Isaac. Viewer: `mujoco.viewer.launch_passive`. On macOS mink examples sometimes need `mjpython`; try normal `python` first.

---

## 13. What we will not do

- Fold with dexterous fingers or dual-arm origami.
- Simulate real thermodynamics of an iron.
- Train RL / imitation before a scripted cycle works.
- Port MELFA into MuJoCo during the hackathon.
- Promise pants, towels, and collared shirts on day one.

Those can be “next” on the slide. The demo is one shirt, bin to box, every time.
