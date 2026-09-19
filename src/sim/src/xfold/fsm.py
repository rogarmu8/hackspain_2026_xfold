"""Cell FSM stage names shared by mock driver, Real MuJoCo controllers, and protocol.

AGENT: arm track — emit these via runtime.emit_state(...). Do not invent parallel stage strings.
AGENT: cloth track — you usually do not change this file; stages come from the cell controller.
See docs/INTEGRATION_CONTRACT.md §4b.
"""

from enum import StrEnum


class CellState(StrEnum):
    PICK = "PICK"
    ORIENT = "ORIENT"
    SPREAD = "SPREAD"
    PRESS = "PRESS"
    FOLD = "FOLD"
    CHUTE = "CHUTE"
    BAG = "BAG"
    RESET = "RESET"


CELL_STATES = tuple(CellState)

# One unattended cycle, matching SOLUTION.md.
CYCLE = (
    CellState.PICK,
    CellState.ORIENT,
    CellState.SPREAD,
    CellState.PRESS,
    CellState.FOLD,
    CellState.CHUTE,
    CellState.BAG,
)
