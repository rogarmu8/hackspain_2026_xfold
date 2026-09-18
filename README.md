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
| **Bridge** (journal + REST/SSE on :8765) | `moon run sim:bridge` |
| **MuJoCo window (the actual scene)** | `moon run sim:view` |
| Mock cell cycle (JSON lines to stdout) | `moon run sim:mock` |
| Dashboard lint | `moon run dashboard:lint` |
| Production dashboard build | `moon run dashboard:build` |
| List projects / tasks | `moon query projects` · `moon query tasks` |

On macOS, `sim:view` runs under `mjpython` (Cocoa main thread). Elsewhere it uses `python -m xfold.view`.

**Live monitor:** start `sim:bridge`, then `dashboard:dev`. The UI probes `http://127.0.0.1:8765` (override with `NEXT_PUBLIC_XFOLD_BRIDGE_URL`). If the bridge is down, the dashboard keeps honest **fixtures**.

- **Binding contract (teammates & agents):** [docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md)
- Transport detail: [docs/BRIDGE.md](docs/BRIDGE.md) · OpenAPI: http://127.0.0.1:8765/docs

### What runs today

- **Bridge:** append-only run journal; mock FSM drives `PICK → … → BAG`; REST commands + SSE events for the control room.
- **Mock CLI:** same cycle printed as JSON lines to stdout (`shirt_in_bag`, same shape as `@xfold/protocol`) — offline / piping.
- **Viewer:** rigid stub in `src/sim/models/cell.xml` — bin, press bed + platen, chute, bag, and a blue shirt proxy that falls onto the press. No cloth mesh and no OpenArm yet.

Build order for cloth + dual-arm: [SOLUTION.md §9](SOLUTION.md#9-build-order-hackathon).

## Who works where

- **Sim / control** — `src/sim/src/xfold` and `src/sim/models`
- **Bridge (sim↔UI)** — `src/sim/src/xfold/bridge` + [docs/BRIDGE.md](docs/BRIDGE.md)
- **Monitor UI** — `src/dashboard/src`
- **Contract** — `packages/protocol/src/index.ts` (keep the Python bridge schema in sync)

**Cycle the cell must complete unattended:**

**bin → two-hand taut → press → ninja fold → tilt / chute → bag**
