from __future__ import annotations

import json
import time

from xfold.fsm import CYCLE, CellState
from xfold.telemetry import Telemetry

HOLD_S = 0.25


def run_mock_cycle(cycle: int = 1) -> list[Telemetry]:
    """Walk the cell FSM and print JSON lines. Physics comes later."""
    frames: list[Telemetry] = []
    t = 0.0
    for state in CYCLE:
        flatness = 0.002 if state in {CellState.DROP, CellState.FOLD, CellState.PACK} else None
        frame = Telemetry.snapshot(
            t=t,
            state=state,
            cycle=cycle,
            flatness=flatness,
            shirt_in_box=state is CellState.PACK,
        )
        frames.append(frame)
        print(json.dumps(frame.to_dict()), flush=True)
        time.sleep(HOLD_S)
        t += HOLD_S
    return frames


def main() -> None:
    print("# xfold mock cycle (no MuJoCo yet)", flush=True)
    run_mock_cycle()


if __name__ == "__main__":
    main()
