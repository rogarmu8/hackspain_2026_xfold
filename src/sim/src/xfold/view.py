"""Open the MuJoCo window for the press / fold cell (flex shirt)."""

from __future__ import annotations

from pathlib import Path

from .platform import reexec_under_mjpython
from .shirt import load_mjcf
from .sim_loop import Loop

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "cell.xml"


def main() -> None:
    try:
        import mujoco
        import mujoco.viewer
    except ImportError:
        raise SystemExit(
            "MuJoCo is not installed in this env.\n"
            "From the repo root run:  moon run install-mujoco"
        )

    reexec_under_mjpython("xfold.view")

    if not MODEL_PATH.is_file():
        raise SystemExit(f"Missing scene: {MODEL_PATH}")

    model, data = load_mjcf(MODEL_PATH, claws=False)
    print(f"XFOLD cell  {MODEL_PATH}", flush=True)
    print(
        "Flex shirt drops crumpled onto the press. "
        "Physics: gravity + soft contacts + edge cloth. Close window to quit.",
        flush=True,
    )

    with mujoco.viewer.launch_passive(model, data) as viewer:
        loop = Loop(model, data, viewer=viewer)
        while loop.step():
            pass


if __name__ == "__main__":
    main()
