"""Open the MuJoCo window for the press / fold cell (flex shirt)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from xfold.shirt import CELL_XML, load_mujoco_plugins

MODEL_PATH = CELL_XML


def _reexec_mjpython_on_macos() -> None:
    """Cocoa GUI must run on the macOS main thread; mjpython sets that up."""
    if sys.platform != "darwin":
        return
    try:
        from mujoco import viewer as mujoco_viewer

        if isinstance(
            getattr(mujoco_viewer, "_MJPYTHON", None),
            getattr(mujoco_viewer, "_MjPythonBase", type),
        ):
            return
    except ImportError:
        return

    mjpython = Path(sys.executable).resolve().parent / "mjpython"
    if not mjpython.is_file():
        raise SystemExit(
            "On macOS the viewer must run under mjpython, which was not found.\n"
            "From the repo root run:  moon run install-mujoco && moon run sim:view"
        )
    os.execv(
        os.fsdecode(mjpython),
        [os.fsdecode(mjpython), "-m", "xfold.view", *sys.argv[1:]],
    )


def main() -> None:
    try:
        import mujoco
        import mujoco.viewer
    except ImportError:
        raise SystemExit(
            "MuJoCo is not installed in this env.\n"
            "From the repo root run:  moon run install-mujoco"
        )

    _reexec_mjpython_on_macos()
    load_mujoco_plugins()

    if not MODEL_PATH.is_file():
        raise SystemExit(f"Missing scene: {MODEL_PATH}")

    model = mujoco.MjModel.from_xml_path(MODEL_PATH.as_posix())
    data = mujoco.MjData(model)
    print(f"XFOLD cell  {MODEL_PATH}", flush=True)
    print(
        "Denser flex shirt drops crumpled onto the press. "
        "Physics: gravity + soft contacts + edge cloth. Close window to quit.",
        flush=True,
    )

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            step_start = time.time()
            mujoco.mj_step(model, data)
            viewer.sync()
            leftover = model.opt.timestep - (time.time() - step_start)
            if leftover > 0:
                time.sleep(leftover)


if __name__ == "__main__":
    main()
