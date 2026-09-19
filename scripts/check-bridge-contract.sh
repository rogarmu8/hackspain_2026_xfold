#!/usr/bin/env bash
# Quick check that protocol event names match the Python Literal union.
# Usage (repo root): pixi run bash scripts/check-bridge-contract.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pixi run python -P <<'PY'
from pathlib import Path
import re

ts = Path("packages/protocol/src/index.ts").read_text()
py = Path("src/sim/src/xfold/bridge/schema.py").read_text()

def block(src: str, name: str) -> set[str]:
    m = re.search(rf"export const {name} = \[([\s\S]*?)\] as const", src)
    if not m:
        raise SystemExit(f"missing {name} in protocol")
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))

events_ts = block(ts, "JOURNAL_EVENT_TYPES")
cmds_ts = block(ts, "COMMAND_KINDS")

events_py = set(re.findall(r'"([a-z_]+)"', re.search(r"JournalEventType = Literal\[([\s\S]*?)\]", py).group(1)))
cmds_py = set(re.findall(r'"([a-z_]+)"', re.search(r"CommandKind = Literal\[([\s\S]*?)\]", py).group(1)))

def upper_block(src: str, name: str) -> set[str]:
    m = re.search(rf"export const {name} = \[([\s\S]*?)\] as const", src)
    if not m:
        raise SystemExit(f"missing {name} in protocol")
    return set(re.findall(r'"([A-Z_]+)"', m.group(1)))

states_ts = upper_block(ts, "CELL_STATES")
states_py = set(re.findall(r'"([A-Z_]+)"', re.search(r"^CellState = Literal\[([\s\S]*?)\]", py, re.M).group(1)))
cycle_ts = upper_block(ts, "PRODUCTIVE_CYCLE")

assert events_ts == events_py, (events_ts ^ events_py)
assert cmds_ts == cmds_py, (cmds_ts ^ cmds_py)
assert states_ts == states_py, (states_ts ^ states_py)
assert "ORIENT" in states_ts and "ORIENT" in cycle_ts
print("bridge contract ok:", sorted(events_ts), sorted(cmds_ts), sorted(states_ts))
PY
