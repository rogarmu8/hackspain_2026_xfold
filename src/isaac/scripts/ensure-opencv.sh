#!/usr/bin/env bash
# OpenCV for fold quality. Lives in the Isaac env on the GPU box, not in
# pixi.lock: isaac-sim is linux-only and a laptop cannot re-solve it.
# `.pixi/` is rsync-excluded, so this survives `remote.sh sync`.
set -euo pipefail
cd "$(dirname "$0")/../../.."
. ./scripts/pixi-path.sh 2>/dev/null || true
PY="${1:-}"
if [ -z "$PY" ]; then
  if [ -x .pixi/envs/isaac-sim/bin/python ]; then
    PY=.pixi/envs/isaac-sim/bin/python
  else
    PY="$(command -v python3 || command -v python)"
  fi
fi
if "$PY" -c "import cv2" 2>/dev/null; then
  "$PY" -c "import cv2; print('cv2', cv2.__version__)"
  exit 0
fi
echo "installing opencv-python-headless into $PY" >&2
if "$PY" -m pip --version >/dev/null 2>&1; then
  "$PY" -m pip install --disable-pip-version-check 'opencv-python-headless>=4.10'
elif command -v uv >/dev/null; then
  uv pip install --python "$PY" 'opencv-python-headless>=4.10'
else
  "$PY" -m ensurepip --upgrade
  "$PY" -m pip install --disable-pip-version-check 'opencv-python-headless>=4.10'
fi
"$PY" -c "import cv2; print('cv2', cv2.__version__)"
