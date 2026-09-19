#!/usr/bin/env bash
# The dashboard's bridge on the Isaac GPU box, reachable here over SSH.
#
#   moon run isaac:bridge          (or as part of `moon run xfold:dev-isaac`)
#
# Syncs the working copy, starts `python -m xfold_isaac.bridge` on the box's
# 127.0.0.1:8765 and forwards it to localhost:$XFOLD_ISAAC_BRIDGE_PORT here
# (default 8766, next to the MuJoCo bridge on 8765). Ctrl-C stops both.
# Settings come from .env (see .env.example).
set -euo pipefail
cd "$(dirname "$0")/../../.."
. ./scripts/load-env.sh
PORT="${XFOLD_ISAAC_BRIDGE_PORT:-8766}"
KEY=(); [ -n "${XFOLD_ISAAC_KEY:-}" ] && KEY=(-i "${XFOLD_ISAAC_KEY/#\~/$HOME}")
# One bridge per box: a previous session that lost its SSH link may still hold the port.
ssh ${KEY[@]+"${KEY[@]}"} -o BatchMode=yes "${XFOLD_ISAAC_HOST:?set XFOLD_ISAAC_HOST in .env}" \
  "pkill -f 'xfold_isaac[.]bridge' || true"
echo "Isaac bridge: http://127.0.0.1:$PORT  (box ${XFOLD_ISAAC_HOST}; Isaac takes ~1 min to boot)"
XFOLD_ISAAC_TUNNEL="$PORT:8765" exec ./src/isaac/scripts/remote.sh \
  python -m xfold_isaac.bridge --port 8765 "$@"
