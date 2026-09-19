"""The press motions: close on the shirt, steam it, open, tilt to dump."""

from __future__ import annotations

from .shirt import set_steam
from .sim_loop import smoothstep
from .steam import SteamField

# press_stroke commands. 0 is the robot-loading height, PRESSED squeezes the shirt.
OPEN = 0.0
PRESSED = -0.755

# press_tilt commands, radians.
FLAT = 0.0
DUMP = 0.78


class PressCycle:
    def __init__(self, model, data) -> None:
        self.model = model
        self.data = data
        self.tilt = model.actuator("press_tilt").id
        self.stroke = model.actuator("press_stroke").id
        self.steam = SteamField(model)

    def park(self) -> None:
        """Loading pose: bed flat, platen up, no vapour."""
        self.data.ctrl[self.tilt] = FLAT
        self.data.ctrl[self.stroke] = OPEN
        set_steam(self.model, False)
        self.steam.reset()
        self.steam.follow(self.data)

    def press(self, loop, close: float = 4.0, steam: float = 5.0, lift: float = 3.5) -> bool:
        if not self._drive(loop, self.stroke, PRESSED, close):
            set_steam(self.model, False)
            return False
        set_steam(self.model, True)
        steamed = self.steam.pulse(loop, steam)
        set_steam(self.model, False)
        return steamed and self._drive(loop, self.stroke, OPEN, lift)

    def dump(self, loop, tilt: float = 3.0, settle: float = 2.5, back: float = 3.0) -> bool:
        return (
            self._drive(loop, self.tilt, DUMP, tilt)
            and self._hold(loop, settle)
            and self._drive(loop, self.tilt, FLAT, back)
        )

    def _drive(self, loop, actuator: int, target: float, seconds: float) -> bool:
        start = float(self.data.ctrl[actuator])
        steps = loop.steps_for(seconds)
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            self.data.ctrl[actuator] = start + (target - start) * blend
            self.steam.follow(self.data)
            if not loop.step():
                return False
        return loop.running

    def _hold(self, loop, seconds: float) -> bool:
        for _ in range(loop.steps_for(seconds)):
            self.steam.follow(self.data)
            if not loop.step():
                return False
        return loop.running
