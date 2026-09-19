"""Demo the heat press on its own: close on the shirt, steam, open, dump."""

from __future__ import annotations

from pathlib import Path

from .platform import reexec_under_mjpython
from .press_cycle import PressCycle
from .sim_loop import Loop

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "press.xml"


def main() -> None:
    try:
        import mujoco
        import mujoco.viewer
    except ImportError:
        raise SystemExit(
            "MuJoCo is not installed.\nFrom the repo root run:  moon run install-mujoco"
        )

    reexec_under_mjpython("xfold.press")

    if not MODEL_PATH.is_file():
        raise SystemExit(f"Missing scene: {MODEL_PATH}")

    from .shirt import load_mujoco_plugins

    load_mujoco_plugins()
    model = mujoco.MjModel.from_xml_path(MODEL_PATH.as_posix())
    data = mujoco.MjData(model)

    print(f"XFOLD press  {MODEL_PATH}", flush=True)
    print(
        "Cycle: robot-clear loading pose -> slow press + vapour -> full lift -> "
        "slow incline -> reset. Close the window to quit.",
        flush=True,
    )

    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
        viewer.cam.fixedcamid = model.camera("press_cam").id
        loop = Loop(model, data, viewer=viewer)
        press = PressCycle(model, data)

        while loop.running:
            mujoco.mj_resetData(model, data)
            press.park()
            if not loop.hold(1.5):
                break
            if not press.press(loop):
                break
            if not loop.hold(1.0):
                break
            if not press.dump(loop):
                break
            if not loop.hold(1.5):
                break


if __name__ == "__main__":
    main()
