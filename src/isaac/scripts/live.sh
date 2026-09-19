#!/usr/bin/env bash
# Run the line on the Isaac GPU box and watch it live in a local browser.
#
#   moon run isaac:live -- -g tee --seed 7          (any xfold_isaac.run flags)
#
# Needs XFOLD_ISAAC_HOST / XFOLD_ISAAC_KEY / XFOLD_ISAAC_ACCEPT_EULA like
# remote.sh. The box serves the stream on its own 127.0.0.1; the SSH session
# forwards it to http://localhost:$XFOLD_ISAAC_LIVE_PORT here. Ctrl-C stops the run.
set -euo pipefail
cd "$(dirname "$0")/../../.."
. ./scripts/load-env.sh
PORT="${XFOLD_ISAAC_LIVE_PORT:-8090}"
URL="http://localhost:$PORT"
(
  # Open the page once the tunnel answers (Isaac takes a minute to boot).
  for _ in $(seq 1 240); do
    if curl -fs -o /dev/null "$URL/status"; then
      if command -v open >/dev/null; then open "$URL"; elif command -v xdg-open >/dev/null; then xdg-open "$URL"; fi
      exit 0
    fi
    sleep 1
  done
) &
echo "live view: $URL (opens when Isaac is up)"
XFOLD_ISAAC_TUNNEL="$PORT" exec ./src/isaac/scripts/remote.sh python -m xfold_isaac.run --serve "$PORT" "$@"
