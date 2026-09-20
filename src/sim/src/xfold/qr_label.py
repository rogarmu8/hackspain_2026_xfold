"""QR matrix used on the bag sticker (byte mode, ECC-M, versions 1–2).

Self-contained so label generation only needs Pillow. Mask 0 is used; the
payloads are short SKU URLs, so version 2 is typical.
"""

from __future__ import annotations

from PIL import Image

# GF(256) for QR Reed–Solomon, primitive 0x11D.
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_encode(data: list[int], nsym: int) -> list[int]:
    # Generator is high-degree first, monic: (x - α^0)…(x - α^{nsym-1}).
    gen = [1]
    for i in range(nsym):
        factor = _EXP[i]
        nxt = [0] * (len(gen) + 1)
        for j, coef in enumerate(gen):
            nxt[j] ^= coef
            nxt[j + 1] ^= _mul(coef, factor)
        gen = nxt
    res = data + [0] * nsym
    for i in range(len(data)):
        coef = res[i]
        if coef:
            for j, g in enumerate(gen):
                res[i + j] ^= _mul(g, coef)
    return data + res[len(data) :]


# version -> (size, data codewords, ec codewords) for ECC-M, one block.
# Version 3-M is two blocks; sticker payloads stay in v1/v2.
_VERSIONS = {
    1: (21, 16, 10),
    2: (25, 28, 16),
}


def _bits_to_bytes(bits: str) -> list[int]:
    bits = bits + "0" * ((8 - len(bits) % 8) % 8)
    return [int(bits[i : i + 8], 2) for i in range(0, len(bits), 8)]


def _encode_bytes(payload: bytes, data_cw: int) -> list[int]:
    bits = "0100" + f"{len(payload):08b}"
    bits += "".join(f"{b:08b}" for b in payload)
    remain = data_cw * 8 - len(bits)
    bits += "0" * min(4, remain)
    data = _bits_to_bytes(bits)
    pad = (0xEC, 0x11)
    i = 0
    while len(data) < data_cw:
        data.append(pad[i % 2])
        i += 1
    return data[:data_cw]


def _reserved(size: int) -> list[list[bool]]:
    reserved = [[False] * size for _ in range(size)]

    def mark(r: int, c: int) -> None:
        if 0 <= r < size and 0 <= c < size:
            reserved[r][c] = True

    def finder(r0: int, c0: int) -> None:
        for r in range(r0 - 1, r0 + 8):
            for c in range(c0 - 1, c0 + 8):
                mark(r, c)

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(size):
        mark(6, i)
        mark(i, 6)
    for i in range(9):
        mark(8, i)
        mark(i, 8)
    for i in range(8):
        mark(8, size - 1 - i)
        mark(size - 1 - i, 8)
    if size >= 25:
        a = size - 7
        for r in range(a - 2, a + 3):
            for c in range(a - 2, a + 3):
                mark(r, c)
    return reserved


def _paint_finders(mod: list[list[int]], size: int) -> None:
    def finder(r0: int, c0: int) -> None:
        for r in range(7):
            for c in range(7):
                edge = r in (0, 6) or c in (0, 6)
                core = 2 <= r <= 4 and 2 <= c <= 4
                mod[r0 + r][c0 + c] = 1 if edge or core else 0

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(8, size - 8):
        bit = 1 if i % 2 == 0 else 0
        mod[6][i] = bit
        mod[i][6] = bit
    if size >= 25:
        a = size - 7
        for r in range(-2, 3):
            for c in range(-2, 3):
                edge = abs(r) == 2 or abs(c) == 2
                mod[a + r][a + c] = 1 if edge or (r == 0 and c == 0) else 0


def _format_bits(mask: int) -> int:
    """15-bit format string for ECC-M (00) and the given mask (BCH + mask 0x5412)."""
    data = (0b00 << 3) | mask
    bits = data << 10
    gen = 0b10100110111
    for i in range(14, 9, -1):
        if bits & (1 << i):
            bits ^= gen << (i - 10)
    raw = (data << 10) | bits
    return raw ^ 0x5412


def _place_format(mod: list[list[int]], size: int, bits: int) -> None:
    seq = [(1 if bits & (1 << (14 - i)) else 0) for i in range(15)]
    # Horizontal copy around the top-left finder, skipping the timing column.
    coords_a = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    coords_b = [(size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8),
                (size - 5, 8), (size - 6, 8), (size - 7, 8),
                (8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5),
                (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1)]
    for bit, (r, c) in zip(seq, coords_a):
        mod[r][c] = bit
    for bit, (r, c) in zip(seq, coords_b):
        mod[r][c] = bit
    mod[size - 8][8] = 1  # dark module


def _place_data(mod: list[list[int]], reserved: list[list[bool]], bits: list[int], mask: int) -> None:
    size = len(mod)
    i = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if reserved[row][c]:
                    continue
                bit = bits[i] if i < len(bits) else 0
                i += 1
                if mask == 0 and (row + c) % 2 == 0:
                    bit ^= 1
                mod[row][c] = bit
        upward = not upward
        col -= 2


def qr_matrix(payload: str) -> list[list[int]]:
    data = payload.encode("utf-8")
    version = None
    for ver, (_size, data_cw, _ec) in _VERSIONS.items():
        # byte mode: 4 + 8 + 8*n + up to 4 terminator
        if 4 + 8 + 8 * len(data) + 4 <= data_cw * 8:
            version = ver
            break
    if version is None:
        raise ValueError(f"payload too long for sticker QR: {payload!r}")
    size, data_cw, ec_cw = _VERSIONS[version]
    codewords = _rs_encode(_encode_bytes(data, data_cw), ec_cw)
    bits: list[int] = []
    for cw in codewords:
        bits.extend((cw >> k) & 1 for k in range(7, -1, -1))
    reserved = _reserved(size)
    mod = [[0] * size for _ in range(size)]
    _paint_finders(mod, size)
    _place_data(mod, reserved, bits, mask=0)
    _place_format(mod, size, _format_bits(0))
    return mod


def qr_image(payload: str, size: int, *, ink: tuple[int, int, int], paper: tuple[int, int, int]) -> Image.Image:
    matrix = qr_matrix(payload)
    border = 2
    n = len(matrix) + 2 * border
    src = Image.new("RGB", (n, n), paper)
    px = src.load()
    for r, row in enumerate(matrix):
        for c, bit in enumerate(row):
            if bit:
                px[c + border, r + border] = ink
    return src.resize((size, size), Image.Resampling.NEAREST)
