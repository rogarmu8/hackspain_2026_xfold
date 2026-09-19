"""Record a line's events, and compare two recordings.

    python -m xfold_isaac.compare record -g tee --seed 7 --out data/isaac/tee_mujoco.jsonl
    python -m xfold_isaac.compare diff data/isaac/tee_mujoco.jsonl data/isaac/tee.jsonl

``record`` runs the native MuJoCo line (``--engine mujoco``) or the same Line
through EngineShim on the MuJoCo reference backend (``--engine reference``);
neither needs Isaac. ``diff`` lines the two event lists up and reports where
the phase sequence, the timing or a measurement differs. It exits 1 if the
sequence of (phase, operation) differs or the outcome does.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def record(garment: str | None, seed: int, skewed: bool, engine: str) -> tuple[list[dict], str | None]:
    import mujoco
    from xfold.line import Line, build
    from xfold.shirt import select_garment, shirt_config

    if garment:
        select_garment(garment)
    model = build()
    data = mujoco.MjData(model)
    events: list[dict] = []
    name = shirt_config().garment

    def on_event(event: dict) -> None:
        events.append({**event, "engine": engine, "garment": name, "seed": seed})

    line = Line(model, data, repeat=False, skewed=skewed, seed=seed, log=lambda *_: None, on_event=on_event)
    if engine == "reference":
        from .engine import EngineShim
        from .reference import MujocoBackend

        EngineShim(line, MujocoBackend(line))
    while not line.finished:
        line.step()
    if events:
        events[-1]["outcome"] = line.outcome
    return events, line.outcome


def load(path: Path) -> list[dict]:
    return [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines() if row.strip()]


def diff(a: list[dict], b: list[dict], *, time_tol: float = 0.25, rel_tol: float = 0.15) -> bool:
    """Print the comparison; True if the two runs went through the same process."""
    key_a = [(e["state"], e["operation"]) for e in a]
    key_b = [(e["state"], e["operation"]) for e in b]
    same = key_a == key_b
    label_a = a[0].get("engine", "a") if a else "a"
    label_b = b[0].get("engine", "b") if b else "b"
    print(f"{'phase':<10} {'operation':<14} {label_a:>9} {label_b:>9} {'dt':>7}  measurements")
    for index in range(max(len(a), len(b))):
        ea = a[index] if index < len(a) else None
        eb = b[index] if index < len(b) else None
        if ea is None or eb is None or (ea["state"], ea["operation"]) != (eb["state"], eb["operation"]):
            print(f"  !! {index}: {key_a[index] if ea else '-'}  vs  {key_b[index] if eb else '-'}")
            continue
        dt = eb["t"] - ea["t"]
        notes = []
        for name, va in ea.get("measurements", {}).items():
            vb = eb.get("measurements", {}).get(name)
            if vb is None:
                notes.append(f"{name} missing")
                continue
            off = abs(vb - va) > rel_tol * max(abs(va), 1e-3)
            notes.append(f"{name} {va:.4g}->{vb:.4g}{' !' if off else ''}")
        flag = " !" if abs(dt) > time_tol else ""
        print(f"{ea['state']:<10} {ea['operation']:<14} {ea['t']:9.3f} {eb['t']:9.3f} {dt:+7.3f}{flag}  {'; '.join(notes)}")
    out_a = next((e.get("outcome") for e in reversed(a) if "outcome" in e), None)
    out_b = next((e.get("outcome") for e in reversed(b) if "outcome" in e), None)
    print(f"sequence {'same' if same else 'DIFFERENT'} ({len(a)} vs {len(b)} events); outcome {out_a} vs {out_b}")
    return same and out_a == out_b


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("-g", "--garment")
    rec.add_argument("--seed", type=int, default=0)
    rec.add_argument("--skewed", action="store_true")
    rec.add_argument("--engine", choices=("mujoco", "reference"), default="mujoco")
    rec.add_argument("--out", type=Path, required=True)
    cmp_ = sub.add_parser("diff")
    cmp_.add_argument("a", type=Path)
    cmp_.add_argument("b", type=Path)
    cmp_.add_argument("--time-tol", type=float, default=0.25, help="seconds")
    args = parser.parse_args()

    if args.command == "record":
        started = time.perf_counter()
        events, outcome = record(args.garment, args.seed, args.skewed, args.engine)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        print(f"{len(events)} events, outcome {outcome}, {time.perf_counter() - started:.1f} s -> {args.out}")
        return
    sys.exit(0 if diff(load(args.a), load(args.b), time_tol=args.time_tol) else 1)


if __name__ == "__main__":
    main()
