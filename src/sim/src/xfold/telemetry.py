from __future__ import annotations

from dataclasses import asdict, dataclass

from xfold.fsm import CellState


@dataclass(frozen=True)
class Telemetry:
    t: float
    state: str
    cycle: int
    flatness: float | None
    shirt_in_bag: bool

    @classmethod
    def snapshot(
        cls,
        *,
        t: float,
        state: CellState,
        cycle: int,
        flatness: float | None = None,
        shirt_in_bag: bool = False,
    ) -> Telemetry:
        return cls(
            t=round(t, 3),
            state=state.value,
            cycle=cycle,
            flatness=flatness,
            shirt_in_bag=shirt_in_bag,
        )

    def to_dict(self) -> dict:
        return asdict(self)
