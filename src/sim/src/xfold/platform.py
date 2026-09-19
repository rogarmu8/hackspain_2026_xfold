"""macOS needs the interactive viewer to run under mjpython, not python."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def reexec_under_mjpython(module: str) -> None:
    """Re-launch the current module under mjpython when required."""
    if sys.platform != "darwin":
        return
    try:
        from mujoco import viewer as mujoco_viewer
    except ImportError:
        return

    if isinstance(
        getattr(mujoco_viewer, "_MJPYTHON", None),
        getattr(mujoco_viewer, "_MjPythonBase", type),
    ):
        return

    mjpython = Path(sys.executable).resolve().parent / "mjpython"
    if not mjpython.is_file():
        raise SystemExit(
            "On macOS the viewer must run under mjpython.\n"
            "From the repo root:  moon run install-mujoco"
        )
    os.execv(
        os.fsdecode(mjpython),
        [os.fsdecode(mjpython), "-m", module, *sys.argv[1:]],
    )
