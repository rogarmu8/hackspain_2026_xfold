"""Open the starter cell using MuJoCo's passive viewer."""

from pathlib import Path
import time

import mujoco
import mujoco.viewer


def main() -> None:
    scene = Path(__file__).resolve().parents[2] / "models" / "cell.xml"
    model = mujoco.MjModel.from_xml_path(str(scene))
    data = mujoco.MjData(model)
    with mujoco.viewer.launch_passive(model, data) as viewer:
        print(f"Viewer ready: {scene}", flush=True)
        while viewer.is_running():
            started = time.monotonic()
            mujoco.mj_step(model, data)
            viewer.sync()
            time.sleep(max(0.0, model.opt.timestep - (time.monotonic() - started)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
