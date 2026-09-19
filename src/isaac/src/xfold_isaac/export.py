"""Write the line's USD stage without Isaac Sim (needs usd-core):

    python -m xfold_isaac.export -g polo            # -> data/isaac/line.usda
"""

from __future__ import annotations

import argparse
from pathlib import Path

import mujoco

from xfold.line import build
from xfold.shirt import select_garment, shirt_config

from .usd_scene import export


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path, nargs="?", default=Path("data/isaac/line.usda"))
    parser.add_argument("-g", "--garment")
    args = parser.parse_args()
    if args.garment:
        select_garment(args.garment)
    model = build()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    scene = export(args.out, model, data)
    print(
        f"{args.out}: {len(scene.geom_paths)} geoms, {len(scene.kinematic)} kinematic bodies, "
        f"cloth {scene.cloth_points} verts ({shirt_config().garment})"
    )


if __name__ == "__main__":
    main()
