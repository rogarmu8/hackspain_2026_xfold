from enum import StrEnum


class CellState(StrEnum):
    PICK = "PICK"
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
    CellState.SPREAD,
    CellState.PRESS,
    CellState.FOLD,
    CellState.CHUTE,
    CellState.BAG,
)
