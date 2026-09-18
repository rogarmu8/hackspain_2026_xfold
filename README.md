# XFOLD

HackSpain '26 · THEKER — automate the shirt press and fold line.

Monorepo: MuJoCo cell in `src/sim`, Next.js monitor in `src/dashboard`, shared telemetry types in `packages/protocol`. **Pixi** pins Python + Node. **moon** is how you run everything.

## Layout

```
src/dashboard      Next.js monitor (@xfold/dashboard)
src/sim            Python cell + mock cycle
packages/protocol  Shared telemetry types (@xfold/protocol)
.moon              moon workspace + toolchain
pixi.toml          Shared conda/PyPI env (Python 3.12, Node 22)
CHALLENGE.md       THEKER brief
SOLUTION.md        Technical plan
```

## Install tools (once per machine)

Install the two binaries, then **open a new terminal** (or `source ~/.zshrc`) so they are on `PATH`. After that, only moon.

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

Optional physics stack (MuJoCo, menagerie, mink):

```bash
moon run install-mujoco
```

## Run

Always from the repo root.

| What | Command |
|------|---------|
| Dashboard at [localhost:3000](http://localhost:3000) | `moon run dashboard:dev` |
| Mock cell cycle (JSON lines) | `moon run sim:mock` |
| Dashboard lint | `moon run dashboard:lint` |
| Production dashboard build | `moon run dashboard:build` |
| List projects / tasks | `moon query projects` · `moon query tasks` |

The mock walks `PICK → PLACE → PRESS → DROP → FOLD → PACK` and prints one telemetry JSON object per state. Same shape as `Telemetry` in `packages/protocol`.

## Who works where

- **Sim / control** — `src/sim/src/xfold` and `src/sim/models`
- **Monitor UI** — `src/dashboard/src`
- **Contract between them** — `packages/protocol/src/index.ts` (keep the Python dataclass in sync)

See [SOLUTION.md](SOLUTION.md) for the four-station design and [CHALLENGE.md](CHALLENGE.md) for the brief.
