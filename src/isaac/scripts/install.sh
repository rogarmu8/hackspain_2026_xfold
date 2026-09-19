#!/usr/bin/env bash
# One-time setup of Isaac Sim 6.1 on a Linux GPU box (Ubuntu 22.04+, NVIDIA
# driver 580+, RTX-class GPU, ~40 GB free). From the repo root on the box:
#   bash src/isaac/scripts/install.sh      (or: moon run isaac:install-sim)
# Installs pixi if missing, then the `isaac-sim` pixi environment
# (torch cu130 + isaacsim[all,extscache] 6.1, pinned in pixi.lock).
set -euo pipefail
cd "$(dirname "$0")/../../.."
if ! command -v pixi >/dev/null && [ ! -x "$HOME/.pixi/bin/pixi" ]; then
  curl -fsSL https://pixi.sh/install.sh | sh
fi
. ./scripts/pixi-path.sh
pixi install --environment isaac-sim
# Importing isaacsim boots Kit (and its EULA prompt), so only look for it.
pixi run --environment isaac-sim -- python -c "import importlib.util as u, xfold.line, xfold_isaac.engine; assert u.find_spec('isaacsim'); print('isaac-sim env ok')"
echo "Next: read NVIDIA's Omniverse EULA, then"
echo "  OMNI_KIT_ACCEPT_EULA=YES moon run isaac:sim -- -g tee --seed 7 --max-seconds 5"
