"""Bake the bag SKU sticker: garment title on top, a QR code below.

    pixi run -e mujoco python -P -m xfold.generate_label

The sticker geom is 10 × 7 cm (see bag_sticker in line.xml). The PNG matches
that 10:7 frame. Payload is a short product URL so the code scans as a SKU.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from xfold.qr_label import qr_image

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"

# Short titles that fit the 10 cm sticker. Keys match line.xml label_* assets.
TITLES = {
    "tee": "T-SHIRT",
    "work_tee": "WORK TEE",
    "jersey": "JERSEY",
    "tank": "TANK",
    "polo": "POLO",
    "dress": "DRESS",
    "custom": "CUSTOM",
}

WIDTH, HEIGHT = 640, 448
MARGIN = 28
INK = (22, 22, 22)
PAPER = (250, 248, 242)
RULE = (200, 196, 186)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def payload_for(key: str) -> str:
    return f"xfold:{key}"


def make_label(key: str) -> Image.Image:
    title = TITLES[key]
    img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(img)
    draw.rectangle((1, 1, WIDTH - 2, HEIGHT - 2), outline=RULE, width=2)

    font = _font(54)
    left, top, right, bottom = draw.textbbox((0, 0), title, font=font)
    tw, th = right - left, bottom - top
    title_y = 26
    draw.text(((WIDTH - tw) / 2 - left, title_y - top), title, font=font, fill=INK)
    rule_y = title_y + th + 12
    draw.line((MARGIN, rule_y, WIDTH - MARGIN, rule_y), fill=RULE, width=2)

    top_qr = rule_y + 16
    avail = HEIGHT - MARGIN - top_qr
    qr_size = min(WIDTH - 2 * MARGIN, avail)
    qr = qr_image(payload_for(key), qr_size, ink=INK, paper=PAPER)
    img.paste(qr, ((WIDTH - qr_size) // 2, top_qr + (avail - qr_size) // 2))
    return img


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    for key in TITLES:
        path = MODELS / f"label_{key}.png"
        make_label(key).save(path)
        print(path)


if __name__ == "__main__":
    main()
