# XFOLD

HackSpain '26 · THEKER — automate the shirt press, ninja fold, and bag line.

The current simulation runs a **robot-free line**: a flat shirt rides a belt through a press, a flap folder, a bagger, a seal/label station and into a carton. The simulator's `xfold.line.LINE_PHASES` and observations are the source of truth for the live dashboard. Arm/ninja-fold descriptions below are earlier design context, not the current implementation.

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
| **Everything (bridge + dashboard)** | `moon run pack` · `npm run pack` |
| Same as pack | `moon run dev` · `npm run dev` |
| Dashboard only ([localhost:3000](http://localhost:3000)) | `moon run dashboard:dev` |
| **Bridge** only (journal + REST/SSE on :8765) | `moon run sim:bridge` |
| **The line — belt, press, folder, bagger, carton (no robots)** | `moon run sim:run` |
| Shared plant stub only (`models/cell.xml`: floor, bin, shirt) | `moon run sim:view` |
| Shirt playground (ninja-fold T — drag it) | `moon run sim:shirt-play` |
| Mock cell cycle (JSON lines to stdout) | `moon run sim:mock` |
| Dashboard lint | `moon run dashboard:lint` |
| Production dashboard build | `moon run dashboard:build` |
| List projects / tasks | `moon query projects` · `moon query tasks` |

On macOS the windowed tasks run under `mjpython` (Cocoa main thread) via `scripts/run-mjpython.sh`; elsewhere it is plain `python`. Keep them in a second terminal — they are not part of `pack` / `dev`.

### What goes down the line

`moon run sim:run` asks for the cloth type, then its condition; `-g` skips the
list and `--list-garments` prints all 30 SKUs.

| Condition | What it is | Example |
|---|---|---|
| clean | the SKU as designed | `-g tee` |
| torn | a hole / torn hem, as real geometry | `-g tee_damaged` (alias `tee_torn`) |
| stained | coffee, grease or mud on the base mesh | `-g tee_notgood1..3` (alias `tee_stain1..3`) |
| off square | flat on the belt, heading from the seed | `--skewed` (and `--seed`), or launch condition `skewed` |

Six clean SKUs — `tee`, `work_tee`, `jersey`, `tank`, `polo`, `dress` — times
four conditions. The pose is separate from the SKU, so `-g dress_damaged
--skewed --seed 7` is a torn pinafore put on the belt at a seeded heading.

The dashboard launch form picks type and condition (exact or random, with
weights). Random draws and the skewed heading use `seed`. `XFOLD_GARMENT`
is still the compile-time default for the bridge process.

### Product shot → try-on

Just past the press the belt stops the garment, the line's lights dip and a
flash fires: `qc_cam` takes a square top-down product shot. It lands in
`data/photos/{run}.jpg`, the bridge serves it at `GET /runs/{id}/photo`, and the
run view shows it under **Foto de producto** — the hole in a `_damaged` tee or
the stain on a `_notgood` one is plainly visible.

**Generar look con modelo** sends that shot to OpenAI's image edit endpoint
(`gpt-image-1`) and shows the garment on a model beside it. The call runs
server-side so the key never reaches the browser:

```bash
cp src/dashboard/.env.example src/dashboard/.env.local
# put your key in OPENAI_API_KEY, then restart the dashboard
```

Without `OPENAI_API_KEY` the rest of the dashboard is unaffected — the button
just reports that the key is missing. `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_SIZE`,
`OPENAI_IMAGE_QUALITY`, `TRYON_PROMPT` and `OPENAI_BASE_URL` override the call.

`gpt-image-1` returns base64 rather than a hosted URL, so the route hands the
browser a data URI; nothing is stored. Note that OpenAI gates `gpt-image-1`
behind organisation verification — if the button reports a 403, that is what it
means.

**Live monitor:** `moon run pack` starts bridge + dashboard together. The UI probes `http://127.0.0.1:8765` (override with `NEXT_PUBLIC_XFOLD_BRIDGE_URL`). If the bridge is down, the dashboard keeps honest **fixtures**.

- **Binding contract (teammates & agents):** [docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md)
- Transport detail: [docs/BRIDGE.md](docs/BRIDGE.md) · OpenAPI: http://127.0.0.1:8765/docs

### What runs today

- **Bridge:** append-only run journal; mock FSM drives `PICK → … → BAG`; REST commands + SSE events for the control room.
- **Mock CLI:** same cycle printed as JSON lines to stdout (`shirt_in_bag`, same shape as `@xfold/protocol`) — offline / piping.
- **Viewer / Control 3D:** ninja-fold flex T (`shirt_t.obj`) in `cell.xml`, and the line (`line.xml`). The bridge viewport renders the line when MuJoCo is available.
- **The line** (`sim:run`, `xfold/line.py`): a flat shirt rides a belt under the press, the platen presses it on the belt, the belt runs it onto a FlipFold-style folder, and three flaps fold it (left, right, hem up) into a ~33 × 33 cm pack. The plate under the pack is a peel: it slides between rails into an open plastic bag and pulls back out, the top film drops, a seal bar closes the mouth while a stamp sticks an RFID label on top, and belt 2 carries the bag off its end into a carton. No arms. The camera follows the shirt (`--camera overview|press_cam|fold_cam|bag_cam` for fixed views).

Build order for cloth + dual-arm: [SOLUTION.md §9](SOLUTION.md#9-build-order-hackathon).

## Who works where

- **Sim / control** — `src/sim/src/xfold` and `src/sim/models`
- **Bridge (sim↔UI)** — `src/sim/src/xfold/bridge` + [docs/BRIDGE.md](docs/BRIDGE.md)
- **Monitor UI** — `src/dashboard/src`
- **Contract** — `packages/protocol/src/index.ts` (keep the Python bridge schema in sync)

**Cycle the cell must complete unattended:**

**bin → two-hand taut → press → ninja fold → tilt / chute → bag**
