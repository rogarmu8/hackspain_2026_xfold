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

GARMENT_KEYS = ("tee", "work_tee", "jersey", "tank", "polo", "dress")


@dataclass(frozen=True)
class Garment:
    key: str
    label: str
    mesh: str
    texture: str
    # Outline style in generate_shirt_mesh (work_tee shares the crew T).
    style: str


CATALOG: dict[str, Garment] = {
    "tee": Garment("tee", "Crew-neck T", "shirt_t.obj", "shirt_print.png", "tee"),
    "work_tee": Garment(
        "work_tee", "Work tee + pocket", "shirt_t.obj", "garment_work_tee.png", "tee"
    ),
    "jersey": Garment(
        "jersey", "Long V-neck jersey", "garment_jersey.obj", "garment_jersey.png", "jersey"
    ),
    "tank": Garment("tank", "Sleeveless tank", "garment_tank.obj", "garment_tank.png", "tank"),
    "polo": Garment(
        "polo", "Spread-collar polo", "garment_polo.obj", "garment_polo.png", "polo"
    ),
    "dress": Garment(
        "dress", "Pinafore dress + braces", "garment_dress.obj", "garment_dress.png", "dress"
    ),
}


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
    if key not in CATALOG:
        raise ValueError(
            f"unknown garment {name!r}; choose one of: {', '.join(GARMENT_KEYS)}"
        )
    return CATALOG[key]


def format_catalog() -> str:
    lines = ["#  id         what"]
    for i, item in enumerate(CATALOG.values(), start=1):
        lines.append(f"{i}  {item.key:<10} {item.label}")
    return "\n".join(lines)


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
        help="arrow-key list to choose the garment (↑↓, Enter)",
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


def _draw_menu(items: list[Garment], idx: int, *, first: bool) -> None:
    n = len(items) + 3
    out = sys.stderr
    if not first:
        out.write(f"\033[{n}A")
    out.write("Select garment   ↑↓ move   Enter select   q cancel\n\n")
    for i, item in enumerate(items):
        body = f"{item.key:<10} {item.label}"
        if i == idx:
            line = f"\033[7m> {body}\033[0m"
        else:
            line = f"  {body}"
        out.write(f"{line}\033[K\n")
    out.write("\n")
    out.flush()


def prompt_garment(current: str = "tee") -> str:
    """Arrow-key list on the terminal. Used by --pick and interactive sim:run."""
    import termios
    import tty

    items = list(CATALOG.values())
    idx = 0
    for i, item in enumerate(items):
        if item.key == current:
            idx = i
            break

    stream = _tty_in()
    if stream is None:
        raise SystemExit("pass -g NAME (no terminal for the garment list)")

    fd = stream.fileno()
    old = termios.tcgetattr(fd)
    sys.stderr.write("\033[?25l")
    _draw_menu(items, idx, first=True)
    try:
        tty.setcbreak(fd)
        while True:
            key = _read_key(fd)
            if key == "up":
                idx = (idx - 1) % len(items)
                _draw_menu(items, idx, first=False)
            elif key == "down":
                idx = (idx + 1) % len(items)
                _draw_menu(items, idx, first=False)
            elif key == "enter":
                break
            elif key == "quit":
                raise SystemExit("no garment selected")
            elif key.isdigit():
                n = int(key)
                if 1 <= n <= len(items):
                    idx = n - 1
                    _draw_menu(items, idx, first=False)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stderr.write(f"\033[{len(items) + 3}A\033[0J\033[?25h")
        sys.stderr.flush()
        if stream is not sys.stdin.buffer:
            stream.close()

    chosen = items[idx].key
    print(f"garment: {chosen}  ({items[idx].label})", flush=True)
    return chosen


def garment_from_args(
    args: argparse.Namespace,
    *,
    interactive: bool = False,
    current: str = "tee",
) -> str | None:
    """-g wins, else --pick / interactive TTY list. None → shirt.toml default."""
    if getattr(args, "list_garments", False):
        print(format_catalog(), flush=True)
        raise SystemExit(0)
    name = getattr(args, "garment", None) or ""
    if name:
        return name
    if os.environ.get("XFOLD_GARMENT", "").strip() and not getattr(args, "pick", False):
        return None
    if getattr(args, "pick", False) or (
        interactive
        and not getattr(args, "headless", False)
        and (sys.stdin.isatty() or sys.stderr.isatty())
    ):
        return prompt_garment(current)
    return None


def rewrite_argv_garment(name: str) -> None:
    """Replace --pick with --garment so mjpython re-exec does not prompt again."""
    skip_next = False
    kept: list[str] = []
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a in ("--pick", "--list-garments"):
            continue
        if a in ("-g", "--garment"):
            skip_next = True
            continue
        if a.startswith("--garment=") or a.startswith("-g="):
            continue
        kept.append(a)
    sys.argv = [sys.argv[0], "--garment", name, *kept]
