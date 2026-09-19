#!/usr/bin/env bash
# Run something on the Isaac GPU box from a laptop: sync the repo, then run
# the command there inside the Isaac env.
#
#   XFOLD_ISAAC_HOST=ubuntu@<box>  XFOLD_ISAAC_KEY=~/path/to/key.pem   (in .env, see .env.example)
#   src/isaac/scripts/remote.sh sync                  # rsync only
#   src/isaac/scripts/remote.sh python -m xfold_isaac.run -g tee --seed 7 --events data/isaac/tee.jsonl
#   src/isaac/scripts/remote.sh fetch data/isaac      # copy results back
#
# The command runs in the box's `isaac-sim` pixi environment, which needs
# `remote.sh bash src/isaac/scripts/install.sh` once. Isaac Sim will not
# start until NVIDIA's EULA is accepted: set XFOLD_ISAAC_ACCEPT_EULA=YES here
# once you have read it, and it is passed on as OMNI_KIT_ACCEPT_EULA.
set -euo pipefail
cd "$(dirname "$0")/../../.."
. ./scripts/load-env.sh
: "${XFOLD_ISAAC_HOST:?set XFOLD_ISAAC_HOST=user@host (in .env, see .env.example)}"
KEY=(); [ -n "${XFOLD_ISAAC_KEY:-}" ] && KEY=(-i "${XFOLD_ISAAC_KEY/#\~/$HOME}")
DIR="${XFOLD_ISAAC_DIR:-xfold}"
TUNNEL=()
# XFOLD_ISAAC_TUNNEL=LOCAL[:REMOTE] forwards localhost:LOCAL here to the box's
# 127.0.0.1:REMOTE (REMOTE defaults to LOCAL). Used by live.sh and bridge.sh.
if [ -n "${XFOLD_ISAAC_TUNNEL:-}" ]; then
  local_port="${XFOLD_ISAAC_TUNNEL%%:*}"
  remote_port="${XFOLD_ISAAC_TUNNEL#*:}"
  TUNNEL=(-L "$local_port:127.0.0.1:$remote_port" -o ExitOnForwardFailure=yes -o ServerAliveInterval=30)
fi
# -t: Ctrl-C here stops the run there.
SSH=(ssh -t ${KEY[@]+"${KEY[@]}"} ${TUNNEL[@]+"${TUNNEL[@]}"} -o BatchMode=yes "$XFOLD_ISAAC_HOST")

sync() {
  rsync -az --delete -e "ssh ${KEY[*]} -o BatchMode=yes" \
    --exclude node_modules --exclude .pixi --exclude .next --exclude data --exclude .git \
    --exclude __pycache__ --exclude MUJOCO_LOG.TXT --exclude shots \
    ./ "$XFOLD_ISAAC_HOST:$DIR/"
}

case "${1:-}" in
  sync) sync ;;
  fetch)
    shift
    for path in "${@:-data/isaac}"; do
      mkdir -p "$(dirname "$path")"
      rsync -az -e "ssh ${KEY[*]} -o BatchMode=yes" "$XFOLD_ISAAC_HOST:$DIR/$path" "$(dirname "$path")/"
    done ;;
  "") echo "usage: $0 sync | fetch [paths] | <command...>" >&2; exit 2 ;;
  *)
    sync
    if [ "$1" = bash ]; then
      run=("$@")  # a script on the box, e.g. the installer
    else
      run=(bash scripts/pixi-run.sh isaac-sim "$@")
    fi
    "${SSH[@]}" "cd $DIR && export OMNI_KIT_ACCEPT_EULA=${XFOLD_ISAAC_ACCEPT_EULA:-} && $(printf '%q ' "${run[@]}")" ;;
esac
