"""Bake the bag's top label: the product type as a title, a fixed barcode below.

One PNG per garment (models/label_<key>.png), 10 x 7 cm on the bag. The
barcode is the same on every label.

    pixi run -e mujoco python -P -m xfold.generate_label
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from xfold.generate_shirt_mesh import MODELS

WIDTH, HEIGHT = 640, 448  # 10 x 7 cm
PAPER = (250, 250, 247)
INK = (16, 16, 18)

TITLES = {
    "tee": "T-SHIRT",
    "work_tee": "WORK TEE",
    "jersey": "JERSEY",
    "tank": "TANK TOP",
    "polo": "POLO SHIRT",
    "dress": "DRESS",
    "trousers": "TROUSERS",
    "custom": "CUSTOM",
}

# Same code on every label. Module widths in order, bar first, then space.
BARCODE_DIGITS = "8435012340017"
BARCODE_MODULES = (
    "1 1 1 3 2 1 1 2 1 3 2 2 1 1 3 1 2 1 1 2 3 1 1 3 2 1 2 2 1 1 "
    "1 3 1 2 2 1 3 1 1 1 2 3 1 2 1 1 3 2 2 1 1 3 1 1 2 2 1 3 1 1 "
    "2 1 1 2 3 1 1 3 2 1 1 1 2 2 1 3 1 2 1 1 2 3 1 1 1 1 1"
)
FONTS = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size, index=1 if path.endswith(".ttc") else 0)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _centered(draw: ImageDraw.ImageDraw, text: str, y: int, size: int, max_w: int) -> None:
    font = _font(size)
    while draw.textlength(text, font=font) > max_w and size > 12:
        size -= 2
        font = _font(size)
    draw.text((WIDTH // 2, y), text, font=font, fill=INK, anchor="mm")


def make_label(title: str, out: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((6, 6, WIDTH - 7, HEIGHT - 7), outline=INK, width=5)

    _centered(draw, title, 92, 92, WIDTH - 80)
    draw.rectangle((40, 158, WIDTH - 41, 164), fill=INK)

    widths = [int(w) for w in BARCODE_MODULES.split()]
    module = (WIDTH - 120) // sum(widths)
    x = (WIDTH - module * sum(widths)) // 2
    for index, width in enumerate(widths):
        if index % 2 == 0:
            draw.rectangle((x, 186, x + module * width - 1, 350), fill=INK)
        x += module * width
    _centered(draw, " ".join((BARCODE_DIGITS[0], BARCODE_DIGITS[1:7], BARCODE_DIGITS[7:])), 388, 40, WIDTH - 80)

    image.save(out, format="PNG", optimize=True)


def main() -> None:
    for key, title in TITLES.items():
        out = MODELS / f"label_{key}.png"
        make_label(title, out)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
