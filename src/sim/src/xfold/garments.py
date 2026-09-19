"""Catalogue of foldable upper-body sheets (same three FlipFold / ninja creases).

Each entry is one 2D panel + one PNG. Hoodies and open coats are not here.
The dress is a longer A-line pinafore with braces; it can overhang the
0.66 m folder.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Garment:
    key: str
    label: str
    mesh: str
    texture: str
    # Outline style in generate_shirt_mesh (work_tee shares the crew T).
    style: str


# Pristine SKUs; a `_damaged` twin is added for each (hole / torn hem).
_PRISTINE: tuple[tuple[str, str, str, str, str], ...] = (
    ("tee", "Crew-neck T", "shirt_t.obj", "shirt_print.png", "tee"),
    ("work_tee", "Work tee + pocket", "shirt_t.obj", "garment_work_tee.png", "tee"),
    ("jersey", "Long V-neck jersey", "garment_jersey.obj", "garment_jersey.png", "jersey"),
    ("tank", "Sleeveless tank", "garment_tank.obj", "garment_tank.png", "tank"),
    ("polo", "Spread-collar polo", "garment_polo.obj", "garment_polo.png", "polo"),
    ("dress", "Pinafore dress + braces", "garment_dress.obj", "garment_dress.png", "dress"),
)

CATALOG: dict[str, Garment] = {}
for _key, _label, _mesh, _tex, _style in _PRISTINE:
    CATALOG[_key] = Garment(_key, _label, _mesh, _tex, _style)
    dkey = f"{_key}_damaged"
    CATALOG[dkey] = Garment(
        dkey,
        f"{_label} (torn)",
        f"garment_{_key}_damaged.obj",
        f"garment_{_key}_damaged.png",
        _style,
    )
    for _n in (1, 2, 3):
        nkey = f"{_key}_notgood{_n}"
        CATALOG[nkey] = Garment(
            nkey,
            f"{_label} (notGood{_n})",
            _mesh,
            f"garment_{_key}_notgood{_n}.png",
            _style,
        )
GARMENT_KEYS = tuple(CATALOG)

# Operator-facing axes (CLI picker + dashboard launch). SKU keys in CATALOG
# are the cartesian product of these plus stain 1–3.
CLOTH_TYPE_KEYS = tuple(k for k, *_ in _PRISTINE)
CLOTH_CONDITION_KEYS = ("good", "damaged", "notgood", "skewed")
CLOTH_CONDITION_LABELS = {
    "good": "clean, square on the belt",
    "damaged": "hole / torn hem",
    "notgood": "stain (random 1–3)",
    "skewed": "any heading on the belt (arms square it)",
}


def base_garment(name: str) -> Garment:
    """Clean SKU behind a torn / stained twin."""
    item = resolve_garment(name)
    key = item.key
    if key.endswith("_damaged"):
        return CATALOG[key[: -8]]
    for n in (1, 2, 3):
        suf = f"_notgood{n}"
        if key.endswith(suf):
            return CATALOG[key[: -len(suf)]]
    return item


def resolve_garment(name: str) -> Garment:
    key = (name or "tee").strip().lower().replace("-", "_")
    aliases = {
        "t": "tee",
        "tshirt": "tee",
        "t_shirt": "tee",
        "uniform": "work_tee",
        "pinafore": "dress",
        "jumper": "dress",
    }
    key = aliases.get(key, key)
    if key.endswith("_torn"):
        key = key[: -5] + "_damaged"
    if key.endswith("_stain1"):
        key = key[: -7] + "_notgood1"
    elif key.endswith("_stain2"):
        key = key[: -7] + "_notgood2"
    elif key.endswith("_stain3"):
        key = key[: -7] + "_notgood3"
    if key not in CATALOG:
        raise ValueError(
            f"unknown garment {name!r}; choose one of: {', '.join(GARMENT_KEYS)}"
        )
    return CATALOG[key]


def format_catalog() -> str:
    lines = ["#  id         what"]
    for i, item in enumerate(CATALOG.values(), start=1):
        lines.append(f"{i:>2}  {item.key:<22} {item.label}")
    return "\n".join(lines)


def public_catalog() -> dict[str, list[dict[str, str]]]:
    """Wire shape for GET /capabilities (dashboard launch form)."""
    return {
        "clothTypes": [{"key": k, "label": lab} for k, lab, *_ in _PRISTINE],
        "clothConditions": [
            {"key": k, "label": CLOTH_CONDITION_LABELS[k]} for k in CLOTH_CONDITION_KEYS
        ],
    }


def compose_pick(cloth: str, condition: str, rng) -> GarmentPick:
    """Map a cloth type + condition onto a catalogue SKU (and pose flag)."""
    import random as _random

    base = base_garment(cloth).key
    if base not in CLOTH_TYPE_KEYS:
        raise ValueError(f"unknown cloth type {cloth!r}")
    cond = (condition or "good").strip().lower()
    if cond not in CLOTH_CONDITION_KEYS:
        raise ValueError(
            f"unknown condition {condition!r}; choose one of: {', '.join(CLOTH_CONDITION_KEYS)}"
        )
    if cond == "damaged":
        return GarmentPick(f"{base}_damaged", skewed=False)
    if cond == "notgood":
        n = rng.randint(1, 3) if hasattr(rng, "randint") else _random.Random().randint(1, 3)
        return GarmentPick(f"{base}_notgood{n}", skewed=False)
    if cond == "skewed":
        return GarmentPick(base, skewed=True)
    return GarmentPick(base, skewed=False)


def _mix_choice(mix: str, values: list[str], universe: tuple[str, ...], rng) -> str:
    allowed = set(universe)
    cleaned = [v for v in values if v in allowed]
    if values and not cleaned:
        raise ValueError(
            f"unknown value {values!r}; choose from: {', '.join(universe)}"
        )
    if mix == "same":
        pool = cleaned or list(universe)
        return pool[0]
    pool = cleaned or list(universe)
    return pool[rng.randrange(len(pool))]


def resolve_launch(
    *,
    cloth_mix: str = "same",
    cloth_types: list[str] | None = None,
    condition_mix: str = "same",
    conditions: list[str] | None = None,
    seed: int = 0,
    index: int = 0,
) -> tuple[GarmentPick, str, str]:
    """Pick one SKU for a run (or batch member). Returns pick, cloth type, condition."""
    import random

    cloth_mix = cloth_mix if cloth_mix in {"same", "random", "list"} else "same"
    condition_mix = (
        condition_mix if condition_mix in {"same", "random", "list"} else "same"
    )
    types = list(cloth_types or [])
    conds = list(conditions or [])
    cloth_seed = int(seed) & 0xFFFFFFFF
    cond_seed = (int(seed) * 17 + 1) & 0xFFFFFFFF
    if cloth_mix != "same":
        cloth_seed = (cloth_seed + index + 1) & 0xFFFFFFFF
    if condition_mix != "same":
        cond_seed = (cond_seed + index + 1) & 0xFFFFFFFF
    cloth_rng = random.Random(cloth_seed)
    cond_rng = random.Random(cond_seed)
    cloth = _mix_choice(cloth_mix, types, CLOTH_TYPE_KEYS, cloth_rng)
    cond = _mix_choice(condition_mix, conds, CLOTH_CONDITION_KEYS, cond_rng)
    return compose_pick(cloth, cond, cond_rng), cloth, cond


@dataclass(frozen=True)
class GarmentPick:
    """Result of -g / the two-step picker."""

    key: str
    skewed: bool = False


def add_garment_arguments(parser: argparse.ArgumentParser) -> None:
    """Shared -g / --pick / --list-garments for line and playground."""
    parser.add_argument(
        "-g",
        "--garment",
        choices=GARMENT_KEYS,
        metavar="NAME",
        help="foldable sheet: " + ", ".join(GARMENT_KEYS),
    )
    parser.add_argument(
        "--pick",
        action="store_true",
        help="two-step list: cloth type, then condition",
    )
    parser.add_argument(
        "--skewed",
        action="store_true",
        help="spawn the cloth rotated / off-centre on the belt",
    )
    parser.add_argument(
        "--list-garments",
        action="store_true",
        help="print the catalogue and exit",
    )


def _tty_in():
    try:
        return open("/dev/tty", "rb", buffering=0)
    except OSError:
        if sys.stdin.isatty():
            return sys.stdin.buffer
        return None


def _read_key(fd: int) -> str:
    import select

    ch = os.read(fd, 1)
    if ch == b"\x1b":
        if select.select([fd], [], [], 0.06)[0]:
            rest = os.read(fd, 2)
            if rest in (b"[A", b"OA"):
                return "up"
            if rest in (b"[B", b"OB"):
                return "down"
        return "quit"
    if ch in (b"\r", b"\n", b" "):
        return "enter"
    if ch in (b"k", b"K"):
        return "up"
    if ch in (b"j", b"J"):
        return "down"
    if ch in (b"q", b"Q", b"\x03"):
        return "quit"
    if ch.isdigit():
        return ch.decode("ascii")
    return ""


def _draw_menu(title: str, rows: list[tuple[str, str]], idx: int, *, first: bool) -> None:
    n = len(rows) + 3
    out = sys.stderr
    if not first:
        out.write(f"\033[{n}A")
    out.write(f"{title}   ↑↓ move   Enter select   q cancel\n\n")
    width = max(len(k) for k, _ in rows)
    for i, (key, label) in enumerate(rows):
        body = f"{key:<{width}}  {label}"
        if i == idx:
            line = f"\033[7m> {body}\033[0m"
        else:
            line = f"  {body}"
        out.write(f"{line}\033[K\n")
    out.write("\n")
    out.flush()


def _clear_menu(nrows: int) -> None:
    sys.stderr.write(f"\033[{nrows + 3}A\033[0J")
    sys.stderr.flush()


def _arrow_pick(
    title: str, rows: list[tuple[str, str]], idx: int, fd: int
) -> int:
    idx %= len(rows)
    _draw_menu(title, rows, idx, first=True)
    while True:
        key = _read_key(fd)
        if key == "up":
            idx = (idx - 1) % len(rows)
            _draw_menu(title, rows, idx, first=False)
        elif key == "down":
            idx = (idx + 1) % len(rows)
            _draw_menu(title, rows, idx, first=False)
        elif key == "enter":
            _clear_menu(len(rows))
            return idx
        elif key == "quit":
            _clear_menu(len(rows))
            raise SystemExit("no garment selected")
        elif key.isdigit():
            n = int(key)
            if 1 <= n <= len(rows):
                idx = n - 1
                _draw_menu(title, rows, idx, first=False)


def prompt_garment(current: str = "tee", *, skewed: bool = False) -> GarmentPick:
    """Two-step arrow list: cloth type, then good / damaged / notGood / skewed."""
    import random
    import termios
    import tty

    types = [(k, lab) for k, lab, *_ in _PRISTINE]
    try:
        current_item = resolve_garment(current)
        current_base = base_garment(current_item.key).key
    except ValueError:
        current_base = "tee"
        current_item = CATALOG["tee"]
    type_idx = next((i for i, (k, _) in enumerate(types) if k == current_base), 0)
    if skewed:
        cond_idx = 3
    elif current_item.key.endswith("_damaged"):
        cond_idx = 1
    elif "_notgood" in current_item.key:
        cond_idx = 2
    else:
        cond_idx = 0

    stream = _tty_in()
    if stream is None:
        raise SystemExit("pass -g NAME (no terminal for the garment list)")

    fd = stream.fileno()
    old = termios.tcgetattr(fd)
    sys.stderr.write("\033[?25l")
    try:
        tty.setcbreak(fd)
        type_idx = _arrow_pick("1/2  Cloth type", types, type_idx, fd)
        conds = (
            ("good", "clean, square on the belt"),
            ("damaged", "hole / torn hem"),
            ("notgood", "stain (random 1–3)"),
            ("skewed", "not square on the belt"),
        )
        cond_idx = _arrow_pick("2/2  Condition", list(conds), cond_idx, fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stderr.write("\033[?25h")
        sys.stderr.flush()
        if stream is not sys.stdin.buffer:
            stream.close()

    base_key = types[type_idx][0]
    cond = conds[cond_idx][0]
    pose = False
    if cond == "damaged":
        chosen = f"{base_key}_damaged"
    elif cond == "notgood":
        chosen = f"{base_key}_notgood{random.randint(1, 3)}"
    elif cond == "skewed":
        chosen = base_key
        pose = True
    else:
        chosen = base_key
    item = CATALOG[chosen]
    extra = "  skewed on belt" if pose else ""
    print(f"garment: {chosen}  ({item.label}){extra}", flush=True)
    return GarmentPick(chosen, skewed=pose)


def garment_from_args(
    args: argparse.Namespace,
    *,
    interactive: bool = False,
    current: str = "tee",
) -> GarmentPick | None:
    """-g wins, else --pick / interactive TTY list. None → shirt.toml default."""
    if getattr(args, "list_garments", False):
        print(format_catalog(), flush=True)
        raise SystemExit(0)
    name = getattr(args, "garment", None) or ""
    skewed = bool(getattr(args, "skewed", False))
    if name:
        return GarmentPick(name, skewed=skewed)
    if os.environ.get("XFOLD_GARMENT", "").strip() and not getattr(args, "pick", False):
        if skewed:
            return GarmentPick(os.environ["XFOLD_GARMENT"].strip(), skewed=True)
        return None
    if getattr(args, "pick", False) or (
        interactive
        and not getattr(args, "headless", False)
        and (sys.stdin.isatty() or sys.stderr.isatty())
    ):
        return prompt_garment(current, skewed=skewed)
    if skewed:
        return GarmentPick(current, skewed=True)
    return None


def rewrite_argv_garment(pick: GarmentPick | str) -> None:
    """Replace --pick with --garment so mjpython re-exec does not prompt again."""
    if isinstance(pick, str):
        pick = GarmentPick(pick)
    skip_next = False
    kept: list[str] = []
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a in ("--pick", "--list-garments", "--skewed"):
            continue
        if a in ("-g", "--garment"):
            skip_next = True
            continue
        if a.startswith("--garment=") or a.startswith("-g="):
            continue
        kept.append(a)
    extra = ["--garment", pick.key]
    if pick.skewed:
        extra.append("--skewed")
    sys.argv = [sys.argv[0], *extra, *kept]
