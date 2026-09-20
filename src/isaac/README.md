# xfold-isaac — the line on NVIDIA Isaac Sim

The same simulation as `moon run sim:run`, with PhysX doing the physics and
RTX doing the pictures. It is not a second line: it runs
`xfold.line.Line` unchanged, on the plant compiled from `src/sim/models/line.xml`.
`LINE_PHASES` and `Line.on_event` stay the source of truth for the process
(AGENTS.md); this project only swaps the engine underneath.

```
line.xml ──build()──► MjModel ──usd_scene──► USD stage (Isaac)
                          │
                 Line (unchanged) ── self._mujoco = EngineShim
                          │ mj_step
                          ▼
     write cloth / bag / kinematic poses ──► PhysX step ──► read cloth / bag
```

| Piece | MuJoCo line | Isaac port |
|---|---|---|
| Cloth | flex + edge equality + bend FEM | PhysX surface deformable on the same mesh, node *i* = flex vertex *i* |
| Bag | free body | dynamic rigid body (origin/COM and body/world spin converted) |
| Flaps, peel (touch the cloth) | mocap bodies | kinematic rigid bodies, teleported (same as mocap: no friction drag); a flap swinging back empty is parked 50 m down instead of having its collider toggled, which crashed PhysX's GPU solver |
| Picker, QC arm, seal bar, stamp… (touch nothing) | mocap bodies | no physics prim; drawn only |
| Press platen | slide joint + position servo | kinematic body; `_Servo` integrates MuJoCo's servo (kp, kv, damping, gravcomp) |
| Belts | cloth/bag velocity set by Line | unchanged (Line writes the velocities) |
| Timestep | 2 ms (shirt.toml) | 5.5 ms by default, which is what puts the line at ~1x realtime (`--timestep 0.002` matches MuJoCo step for step) |
| Colliders | contype/conaffinity | collider iff MuJoCo lets it touch cloth or bag; collision groups keep the bag off cloth-only parts |
| What the camera sees | the model itself | a separate physics-free tree (`/World/Visual`) posed from MjData on rendered frames; the physics tree (`/World/Line`) is hidden. Bag films, slats, steam and the QC flash are edits to it |
| Cameras / lights | line.xml | same names and poses; RTX intensities tuned by constant |

## Layout

```
src/xfold_isaac/
  engine.py         EngineShim + Backend protocol + press servo (no Isaac import)
  reference.py      MujocoBackend: the protocol on a shadow MjData, for tests
  usd_scene.py      compiled MjModel -> USD (pxr only)
  isaac_backend.py  the protocol on Isaac Sim 6.1 (DeformablePrim, RigidPrim)
  run.py            CLI on the GPU box: events, video, QC photo
  compare.py        record a MuJoCo run; diff two event logs
  export.py         write line.usda without Isaac (usd-core)
scripts/install.sh  one-time setup on the box (pixi + the isaac-sim env)
scripts/remote.sh   sync + run on the box from a laptop (moon isaac:remote / isaac:fetch)
```

## Commands

Everything runs through moon + pixi, like the rest of the repo. Two pixi
environments: `isaac` (any laptop; adds usd-core and this package to the
mujoco env) and `isaac-sim` (Isaac Sim 6.1 + CUDA torch; Linux, glibc 2.35+,
NVIDIA RTX only).

On a laptop, no GPU:

```bash
moon run isaac:install                  # pixi install -e isaac
moon run isaac:test                     # adapter, press servo, colliders, USD stage (~2 s)
moon run isaac:parity                   # + two full cycles vs the native MuJoCo line (~2 min)
moon run isaac:export -- -g polo        # -> data/isaac/line.usda, the stage Isaac loads
moon run isaac:record -- -g tee --seed 7 --out data/isaac/tee_mujoco.jsonl
moon run isaac:compare -- data/isaac/tee_mujoco.jsonl data/isaac/tee.jsonl
```

`parity` runs the line through `EngineShim` on `MujocoBackend` and checks it
against the native line: same phases, times within 0.1 s, measurements
within 25 %. Not bit-identical: the native platen is slowed by the cloth it
lands on, the shimmed one cannot feel it.

On the GPU box, from a laptop (host and key from env, never committed; the
working copy is synced first, the command runs in the box's `isaac-sim` env):

```bash
export XFOLD_ISAAC_HOST=ubuntu@<box> XFOLD_ISAAC_KEY=~/path/key.pem
export XFOLD_ISAAC_ACCEPT_EULA=YES      # only once you have read NVIDIA's Omniverse EULA
moon run isaac:watch -- -g tee --seed 7   # one cycle on the box, video back here and opened (~5 min)
moon run isaac:remote -- bash src/isaac/scripts/install.sh               # once, ~25 GB
moon run isaac:remote -- python -m xfold_isaac.run -g tee --seed 7 --max-seconds 5
moon run isaac:remote -- python -m xfold_isaac.run -g polo --seed 3 \
    --events data/isaac/polo.jsonl --video data/isaac/polo.mp4 --photo data/isaac/polo_qc.png
moon run isaac:fetch                    # the box's data/isaac -> here
```

On the box itself (with moon there): `moon run isaac:install-sim`, then
`OMNI_KIT_ACCEPT_EULA=YES moon run isaac:sim -- -g tee --seed 7 ...`. Without
moon, `bash scripts/pixi-run.sh isaac-sim python -m xfold_isaac.run ...` is
the same thing.

First launch compiles RTX shaders for several minutes. After that, on the L4 a
cycle runs at **~1x realtime** (47 s simulated in 45 s) plus a minute of Isaac
start-up. `--profile` prints where a step goes: ~5.3 ms, of which PhysX is
~3.2 ms and the rest is moving the cloth and the bag across the boundary.

Measured against MuJoCo for `-g tee --seed 7`: same 29 events and outcome,
folded pack 30.7 x 32.5 cm x 31 mm vs MuJoCo's 31.0 x 33.1 cm x 33 mm, phases
drifting ~1 s over the cycle. A packed polo and a skewed stained reject
(diverted to the stained tote) behave too.

`run.py` flags worth knowing: `--profile`, `--timestep`, `--camera overview|qc_cam|…|follow`,
`--fps`, `--size`, `--usd out.usda` (save the built stage), and the cloth
material: `--youngs`, `--poisson`, `--bend`, `--cloth-damping`,
`--no-self-collision`.

## The dashboard on Isaac

```bash
cp .env.example .env         # once: box host, key, EULA, ports
moon run xfold:dev-isaac     # Isaac bridge on the box + dashboard on http://localhost:3001
moon run xfold:dev           # the MuJoCo stack, unchanged, on :3000 (both can run at once)
```

`moon run isaac:bridge` syncs the working copy, starts `python -m xfold_isaac.bridge` on the
box's 127.0.0.1:8765 and forwards it here to 127.0.0.1:8766 over SSH; `dashboard:dev-isaac`
points the dashboard at that (or at `XFOLD_ISAAC_BRIDGE_URL` if set). The live view, the run
video (HLS, recorded and served on the box), the QC photo and the console all come from Isaac.
Launch runs from the dashboard as usual; a cycle takes ~4-5 min of wall time.
Experiments persist on the box in `data/experiments.sqlite` (same bridge code as
MuJoCo): after a restart, `GET /experiments` and `GET /runs/{id}` still return
finished runs. Video and QC photos stay under `data/video/` and `data/photos/`.
`rsync` from the laptop excludes `data/`, so the catalogue is not wiped on sync.

One render per frame, at two sizes: 1920x1080 into the run's recording (24 fps of sim time,
so replay lines up with the timeline), and a 960x540 copy for the live view. The live view is
JPEG frames, not the recording — at 0.2x realtime a 2 s HLS segment takes ~10 s to fill, so
watching the video live left the viewport black for the first half minute. The bridge says so
with `/capabilities.liveVideo = false`, and the dashboard switches to the video once the run
ends. `--size`, `--video-size` and `--video-fps` on `xfold_isaac.bridge` change all of this.

## Machine speed and concurrency

Runs carry a machine speed (1 … 20) like the MuJoCo line: `xfold_isaac.run --speed 4`, or the
dashboard's launch form. Isaac runs **one** experiment at a time (`maxConcurrentRuns` = 1): Kit is
a single stage on a single thread, so further launches queue. The MuJoCo bridge runs three at once.

## Known gaps
- Label stickers and the floor checker are flat colours: USD cubes carry no UVs.
- Cloth stiffness and light gains are first guesses, tuned against the MuJoCo
  render, not measured.
- Pixels only when asked (`--video`, `--photo`); the headless default renders
  twice a second to keep Kit alive.
- Replay scrubbing re-renders from saved positions on MuJoCo only
  (`recordingSeek`); on Isaac the run's video is the replay.
