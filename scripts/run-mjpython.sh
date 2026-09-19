#!/usr/bin/env bash
# Launch a Python module in the mujoco pixi env.
# Extra args must be forwarded: moon `script` tasks drop `moon run -- …`.
set -euo pipefail
. ./scripts/pixi-path.sh
if [ "$(uname -s)" = Darwin ]; then
  PY=mjpython
else
  PY=python
fi
exec pixi run --environment mujoco -- "$PY" -P "$@"
