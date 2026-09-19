"""Render offscreen stills of a shirt scene — for checking looks and for the pitch.

Usage:
    python -m xfold.shirt_shot [--hi] [--steps 3000] [--out /tmp]
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

from xfold.shirt import PLAYGROUND_HI_XML, PLAYGROUND_XML, load_mjcf, load_mujoco_plugins

# (name, distance, elevation, azimuth) — grazing angles expose floor clipping.
VIEWS = (
    ("wide", 1.15, -30.0, 125.0),
    ("grazing", 0.70, -5.0, 140.0),
    ("top", 0.95, -70.0, 125.0),
)


def write_png(path: Path, rgb) -> None:
    """Minimal PNG writer so this works without imageio/PIL."""
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hi", action="store_true", help="Use the high-detail mesh")
    parser.add_argument("--steps", type=int, default=3000, help="Settle steps first")
    parser.add_argument("--out", type=Path, default=Path("/tmp"))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args(argv)

    try:
        import mujoco
    except ImportError:
        raise SystemExit("MuJoCo is not installed. Run:  moon run install-mujoco")

    load_mujoco_plugins()
    scene = PLAYGROUND_HI_XML if args.hi else PLAYGROUND_XML
    model, data = load_mjcf(scene)
    for _ in range(args.steps):
        mujoco.mj_step(model, data)

    renderer = mujoco.Renderer(model, height=args.height, width=args.width)
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(model, camera)
    options = mujoco.MjvOption()

    args.out.mkdir(parents=True, exist_ok=True)
    tag = "hi" if args.hi else "std"
    for name, distance, elevation, azimuth in VIEWS:
        camera.lookat[:] = [0.0, 0.0, 0.02]
        camera.distance = distance
        camera.elevation = elevation
        camera.azimuth = azimuth
        renderer.update_scene(data, camera, options)
        path = args.out / f"shirt_{tag}_{name}.png"
        write_png(path, renderer.render())
        print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
