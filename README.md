# XFOLD

HackSpain '26 · THEKER — automate the shirt press, ninja fold, and bag line.

A crumpled shirt is stretched onto a press by **two OpenArm hands**, ironed, folded with the Japanese / ninja method, then dumped down a chute into a packaging bag — no human in the loop.

- Plan (source of truth): [SOLUTION.md](SOLUTION.md)
- Brief: [CHALLENGE.md](CHALLENGE.md)

Monorepo: MuJoCo cell in `src/sim`, Next.js monitor in `src/dashboard`, shared telemetry in `packages/protocol`. **Pixi** pins Python + Node. **moon** runs every day-to-day command.

## Layout

```
src/dashboard      Next.js monitor (@xfold/dashboard)
src/sim            Python cell + mock cycle + MJCF
packages/protocol  Shared telemetry types (@xfold/protocol)
.moon              moon workspace + toolchain
pixi.toml          Shared conda/PyPI env (Python 3.12, Node 22)
CHALLENGE.md       THEKER brief
SOLUTION.md        Technical plan
```

## Robot

**Enactic OpenArm v2** — dual-arm, 7-DOF × 2 + grippers, MuJoCo MJCF.

Control / sim stack we vendor from: [Manas-arumalla/openarm-control](https://github.com/Manas-arumalla/openarm-control) (Apache-2.0).

| We take | We skip |
|---------|---------|
| Bimanual MJCF + meshes | RL (SAC / PPO), ACT |
| IK, Cartesian, trajectories | Catching, throwing, language agent |
| Bimanual coordination | Webcam mimic, YOLO |
| Cloth flex tunings + grasp-on-cloth | Their single-arm `openarm cloth` *motion* as the fold |

Their cloth demo uses **one arm** on a **two-arm** robot. Our cycle uses both arms for taut; the ninja fold prefers both hands and falls back to sequential creases if they collide. Details in [SOLUTION.md](SOLUTION.md).

## Install tools (once per machine)

Install the two binaries. Moon runs in a non-interactive shell, so it will **not** see PATH changes from `~/.zshrc`. It looks for Pixi in `~/.pixi/bin` and Homebrew via `scripts/pixi-path.sh`. After installing, you can keep using moon immediately.

### macOS / Linux

```bash
# Pixi — moon uses this for the shared Python/Node env
curl -fsSL https://pixi.sh/install.sh | sh

# moon — this is the only command you use day to day
bash <(curl -fsSL https://moonrepo.dev/install/moon.sh)
echo 'export PATH="$HOME/.moon/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Homebrew for Pixi if you prefer:

```bash
brew install pixi
# moon has no brew formula; use the script above
```

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"
irm https://moonrepo.dev/install/moon.ps1 | iex
```

Check:

```bash
pixi --version
moon --version
```

## First-time setup (this repo)

```bash
git clone https://github.com/rogarmu8/hackspain_2026_xfold.git
cd hackspain_2026_xfold
moon run setup
```

`moon run setup` creates the Pixi env from `pixi.lock` and installs npm workspaces.

Physics stack (MuJoCo). Required to open the viewer:

```bash
moon run install-mujoco
```

## Run

Always from the repo root.

| What | Command |
|------|---------|
| Dashboard at [localhost:3000](http://localhost:3000) | `moon run dashboard:dev` |
| MuJoCo viewer (full cell + flex shirt) | `moon run sim:view` |
| Shirt playground (CLOTH3D cloth — drag it) | `moon run sim:shirt-play` |
| Shirt playground, high-detail mesh | `moon run sim:shirt-play-hi` |
| Shirt playground (poncho-style elasticity) | `moon run sim:shirt-play-poncho` |
| Flex shirt 10 s stability smoke | `moon run sim:shirt-smoke` |
| Mock cell cycle (JSON lines) | `moon run sim:mock` |
| Dashboard lint | `moon run dashboard:lint` |
| Production dashboard build | `moon run dashboard:build` |
| List projects / tasks | `moon query projects` · `moon query tasks` |

On macOS, `sim:view` runs under `mjpython` (Cocoa main thread). Elsewhere it uses `python -m xfold.view`.

### What runs today

- **Mock:** `PICK → SPREAD → PRESS → FOLD → CHUTE → BAG` — one JSON telemetry line per state (`shirt_in_bag`, same shape as `@xfold/protocol`).
- **Viewer:** full cell (`moon run sim:view`) or shirt playground (`moon run sim:shirt-play`) — **adult T-shirt** sized for the Japanese / ninja fold (`models/shirt_t.obj`: 0.60×0.64 m body, short sleeves, crew neck). Thirds are 0.20 m so the packet can land on 0.20×0.28 m. Edge equality, no joint damping.
- **Ninja fold demo:** press **N** or double-click the orange button in the playground. Scripted sequential Japanese fold: left third → right third → hem to collar (the dual-arm fallback in [SOLUTION.md §5.3](SOLUTION.md#station-3--japanese--ninja-fold-two-hands-on-the-press)). **N** again cancels.
- **Grabbing the cloth (trackpad friendly):** press **G** to pinch (the vertex you double-clicked, else the highest one), **arrows** to steer relative to the camera, **E/Q** to lift/lower, **X** to stop, **R** to reset. Each tap adds speed — the viewer delivers no key-repeat. MuJoCo's own Ctrl+right-drag still works if you have a mouse.
- **Why ~150 verts:** MuJoCo caps a geom pair at 50 contacts (`mjMAXCONPAIR`) and the whole cloth-vs-floor interaction is one pair. Past ~160 vertices the extra ones get no support. Full measurements in [SOLUTION.md §4.3](SOLUTION.md#43-cloth--garment-simulation). Regenerate with `python -m xfold.generate_shirt_mesh --spacing 0.052`.
- **Ninja landmarks:** `xfold.ninja.landmarks` picks the crease-line vertices (left/right third + hem + collar) for the dual-arm fold in [SOLUTION.md §5.3](SOLUTION.md#station-3--japanese--ninja-fold-two-hands-on-the-press). The playground demo (`N` / orange button) uses those panels.
- **Cloth tuning gotchas** (all measured on a drop test):
  - Edge `damping` above ~0.5 makes the equality constraints pump energy and the shirt flies off the floor.
  - **No `<joint damping>` on the cloth.** It is absolute-frame drag, so it slowed free fall by 1.5x and read as a heavy object in slow motion. It hides the ripple instead of fixing it; the vertex count is the fix.
  - `solver="CG"` is ~2x faster than Newton on this equality-heavy flex at the same accuracy. Keep `timestep="0.002"` — a bigger step buys speed but reintroduces floor clipping.
  - A 2D flex renders as a slab of half-thickness `radius`; 0.008 looked like a yoga mat. 0.004 is the thinnest that still never clips.
  - **Slime is a shading bug, not a mesh bug.** Saturated `rgba` + MuJoCo's default specular = wet highlights that also flatten the folds. Use a matte `<material specular="0.02" shininess="0.01">`. Cube textures render white on a flex.
  - `flatskin="true"` forces flat shading and makes the cloth look faceted; MuJoCo's default (`false`, smooth) is what you want.
  - The viewer loop must render at ~60 Hz and step physics to catch up. Calling `viewer.sync()` once per 2 ms step rendered at 500 Hz and dropped the playground to a fraction of realtime.
- **Stills for the pitch:** `moon run sim:shirt-shot` renders wide / grazing / top PNGs into `shots/` (needs a GPU context, so run it from a normal terminal).
- **Shirt smoke:** `moon run sim:shirt-smoke` — headless 10 s stability check.
- **Shell FEM:** not usable on pip MuJoCo 3.13 (`mujoco.elasticity.shell` removed). Default cloth = edge equality (poncho params). Native `<elasticity>` lives in the poncho playground only.

Build order for cloth + dual-arm: [SOLUTION.md §9](SOLUTION.md#9-build-order-hackathon).

## Who works where

- **Sim / control** — `src/sim/src/xfold` and `src/sim/models`
- **Monitor UI** — `src/dashboard/src`
- **Contract** — `packages/protocol/src/index.ts` (keep the Python dataclass in sync)

**Cycle the cell must complete unattended:**

**bin → two-hand taut → press → ninja fold → tilt / chute → bag**
