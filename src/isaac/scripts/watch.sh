#!/usr/bin/env bash
# Send one cycle to the Isaac GPU box, then watch the video here.
#
#   moon run isaac:watch                              # tee, seed 0
#   moon run isaac:watch -- -g polo --seed 3 --camera overview
#
# Takes ~5 min (Isaac boot + 46 s of line at ~0.2x real time). Leaves
# data/isaac/<name>.mp4 / .jsonl / _qc.png here and opens the video.
# Needs XFOLD_ISAAC_HOST / XFOLD_ISAAC_KEY / XFOLD_ISAAC_ACCEPT_EULA (remote.sh).
set -euo pipefail
cd "$(dirname "$0")/../../.."
. ./scripts/load-env.sh
name="${XFOLD_ISAAC_NAME:-run-$(date +%Y%m%d-%H%M%S)}"
out="data/isaac/$name"
echo "running on ${XFOLD_ISAAC_HOST:?set XFOLD_ISAAC_HOST=user@host} -> $out.mp4"
./src/isaac/scripts/remote.sh python -m xfold_isaac.run \
  --video "$out.mp4" --events "$out.jsonl" --photo "${out}_qc.png" "$@"
./src/isaac/scripts/remote.sh fetch "$out.mp4" "$out.jsonl"
# No QC photo if the run stopped before the camera (--max-seconds).
./src/isaac/scripts/remote.sh fetch "${out}_qc.png" 2>/dev/null || true
echo "video: $out.mp4"
if [ -z "${XFOLD_ISAAC_NO_OPEN:-}" ]; then
  if command -v open >/dev/null; then open "$out.mp4"; elif command -v xdg-open >/dev/null; then xdg-open "$out.mp4"; fi
fi
