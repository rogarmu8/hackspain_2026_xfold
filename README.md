<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="src/dashboard/public/brand/xfold-logo-reverse.svg">
    <img src="src/dashboard/public/brand/xfold-logo-primary.svg" alt="XFOLD" width="320">
  </picture>
</p>

<p align="center">HackSpain '26 · THEKER — a simulated industrial line that presses, folds and bags shirts, with a live control-room dashboard.</p>

---

## What it is

A shirt lands flat on a belt. It rides under a hot platen press, onto a
FlipFold-style folder that creases it in three flaps, onto a peel that slides
the pack into a plastic bag, past a seal bar and an RFID stamp, and off the end
of belt 2 into a carton. No human, no robot arm — machines do the geometry.

All of it is **simulated physics**, not an animation: the cloth is real
deformable fabric, the flaps really push it, and the fold either comes out
square or it doesn't. Every cycle is recorded — phases, timings, measurements,
a product photo and a video — and streamed to a web dashboard you watch it on.

## Architecture

```
  ┌──────────────┐   journal    ┌──────────────┐   REST + SSE   ┌──────────────┐
  │  simulation  │ ───events──► │    bridge    │ ─────────────► │  dashboard   │
  │  (physics)   │ ◄──commands─ │ (Python API) │ ◄───launch──── │  (browser)   │
  └──────────────┘              └──────────────┘                └──────────────┘
   MuJoCo or Isaac Sim           run history, video              Next.js UI
```

Three pieces, one contract:

- **Simulation** (`src/sim`) — the plant is an XML model (belts, press, folder,
  bagger, cameras); the process is Python (`xfold/line.py`), a state machine
  that walks a shirt through the phases and measures the result.
- **Bridge** (`src/sim/.../bridge`) — the only thing the browser talks to. It
  keeps an append-only journal of every run, serves it over plain HTTP
  (REST for commands, SSE for live events), and records video per run.
- **Dashboard** (`src/dashboard`) — a Next.js control room: launch a run, watch
  the camera live, scrub the replay, read the measurements. If the bridge is
  down it falls back to fixtures instead of lying.

The same line runs on **two physics engines**: MuJoCo on a laptop, and NVIDIA
**Isaac Sim / PhysX** on a GPU box (`src/isaac`) for RTX-quality pictures. The
process code is identical — only the engine underneath is swapped.

## Toolchain

Two tools, and they install everything else. Nothing is global, no
`pip install`, no Node version juggling.

| Tool | What it does for us | Install |
|---|---|---|
| **[pixi](https://pixi.sh)** | Pins Python 3.12, Node 22, MuJoCo, Isaac Sim — one locked env per machine, from `pixi.toml` / `pixi.lock`. | [pixi.sh/latest/installation](https://pixi.sh/latest/installation/) |
| **[moon](https://moonrepo.dev)** | Runs every command in the monorepo (`moon run <task>`), in the right project, with the pixi env already loaded. | [moonrepo.dev/docs/install](https://moonrepo.dev/docs/install) |

```bash
pixi --version && moon --version   # check both are on PATH
```

## Run it

```bash
git clone https://github.com/rogarmu8/hackspain_2026_xfold.git
cd hackspain_2026_xfold
moon run setup             # pixi env + npm workspaces
moon run install-mujoco    # physics
```

Then start the app:

| | Command | Opens |
|---|---|---|
| **The app, on Isaac Sim** (GPU box) | **`moon run xfold:dev-isaac`** | http://localhost:3001 |
| The app, on MuJoCo (any laptop) | `moon run xfold:dev` | http://localhost:3000 |
| The line in a 3D viewer, no UI | `moon run sim:run` | MuJoCo window |

`xfold:dev-isaac` needs the GPU box configured once — copy `.env.example` to
`.env` and fill in the host and key. It opens an SSH tunnel to the bridge
running on the box and serves the dashboard locally. Both stacks can run side
by side. `moon query tasks` lists everything else.

## Compute

Isaac Sim runs on a dedicated Linux GPU box; the laptops only drive it.

| | |
|---|---|
| GPU | NVIDIA L4, 24 GB — RTX-class required |
| OS | Ubuntu 22.04+ (glibc 2.35+), NVIDIA driver 580+ |
| Disk | ~40 GB free (Isaac Sim 6.1 + shader cache is ~25 GB) |
| Runtime | Python 3.12, Isaac Sim 6.1, CUDA torch — installed by `moon run isaac:install-sim` |
| Speed | ~1x realtime: a 47 s cycle in 45 s, plus ~1 min of Isaac start-up |

Everything except Isaac itself runs fine on a laptop — MuJoCo, the bridge, the
dashboard and the full test suite need no GPU.

## Where things are

```
src/sim         physics line + bridge (Python, MuJoCo)
src/isaac       the same line on Isaac Sim / PhysX
src/dashboard   Next.js control room
packages/protocol   shared wire types (TS ↔ Python)
models/ robots/     MJCF plant + robot assets
```

- Plan and build order: [SOLUTION.md](SOLUTION.md) · Brief: [CHALLENGE.md](CHALLENGE.md) · Log: [TRACKING.md](TRACKING.md)
- Sim ↔ UI contract: [docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md) · [docs/BRIDGE.md](docs/BRIDGE.md)
- Isaac port: [src/isaac/README.md](src/isaac/README.md)
- Working on this repo (or pointing an agent at it): [AGENTS.md](AGENTS.md)
