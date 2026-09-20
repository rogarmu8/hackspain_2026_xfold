#!/usr/bin/env bash
# The dashboard's bridge on the Isaac GPU box, reachable here over SSH.
#
#   moon run isaac:bridge          (or as part of `moon run xfold:dev-isaac`)
#
# Forwards the box's 127.0.0.1:8765 to localhost:$XFOLD_ISAAC_BRIDGE_PORT
# (default 8766). If systemd (or anything) already serves /health, this is
# an SSH tunnel only — it must not start a second Isaac or pkill the live one.
# Settings come from .env (see .env.example).
set -euo pipefail
cd "$(dirname "$0")/../../.."
. ./scripts/load-env.sh
PORT="${XFOLD_ISAAC_BRIDGE_PORT:-8766}"
KEY=(); [ -n "${XFOLD_ISAAC_KEY:-}" ] && KEY=(-i "${XFOLD_ISAAC_KEY/#\~/$HOME}")
HOST="${XFOLD_ISAAC_HOST:?set XFOLD_ISAAC_HOST in .env}"
# Reuse the box process when it is already up (systemd or a leftover SSH
# start). A second Isaac on :8765 kills the first and knocks Vercel Offline.
remote_ready() {
  ssh ${KEY[@]+"${KEY[@]}"} -o BatchMode=yes "$HOST" \
    'export XDG_RUNTIME_DIR=/run/user/$(id -u)
     if systemctl --user is-active --quiet xfold-isaac-bridge.service; then exit 0; fi
     curl -sf --max-time 2 http://127.0.0.1:8765/health >/dev/null'
}
if remote_ready; then
  echo "Isaac bridge already on the box — SSH tunnel only: http://127.0.0.1:$PORT"
  exec ssh ${KEY[@]+"${KEY[@]}"} -o BatchMode=yes -o ServerAliveInterval=30 \
    -N -L "$PORT:127.0.0.1:8765" "$HOST"
fi
echo "Isaac bridge: http://127.0.0.1:$PORT  (box $HOST; Isaac takes ~1 min to boot)"
XFOLD_ISAAC_TUNNEL="$PORT:8765" exec ./src/isaac/scripts/remote.sh \
  python -m xfold_isaac.bridge --port 8765 "$@"
