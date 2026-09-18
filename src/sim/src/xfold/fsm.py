from enum import StrEnum


class CellState(StrEnum):
    PICK = "PICK"
    PLACE = "PLACE"
    PRESS = "PRESS"
    DROP = "DROP"
    FOLD = "FOLD"
    PACK = "PACK"
    RESET = "RESET"


CELL_STATES = tuple(CellState)

# One unattended cycle, matching SOLUTION.md.
CYCLE = (
    CellState.PICK,
    CellState.PLACE,
    CellState.PRESS,
    CellState.DROP,
    CellState.FOLD,
    CellState.PACK,
)
