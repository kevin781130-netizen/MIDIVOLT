"""Plan (not execute) instrument-specific AI arrangement requests."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from .composition_planner import make_composition_plan
from .io import read_midi


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midivolt-plan",
        description="Convert explicit Chinese/English instrument requests into a reviewable JSON plan; no inference.",
    )
    p.add_argument("--source", required=True, help="Existing source MIDI, never modified")
    p.add_argument("--prompt", required=True, help="Natural-language arrangement request")
    p.add_argument("--lock", type=int, action="append", required=True,
                   help="Existing source track index to protect (repeatable)")
    p.add_argument("--out", help="New .json plan path (omit to print JSON only)")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        source = Path(a.source).expanduser().resolve()
        midi = read_midi(source)
        plan = make_composition_plan(
            a.prompt,
            source_track_count=len(midi.instruments),
            locked_tracks=tuple(a.lock),
        )
        rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        if a.out:
            dest = Path(a.out).expanduser().resolve()
            if dest.suffix.lower() != ".json" or not dest.parent.is_dir():
                raise ValueError("Plan output must be a .json file in an existing directory.")
            if dest.exists():
                raise FileExistsError(f"Refusing to overwrite plan: {dest}")
            fd, name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out:
                    out.write(rendered)
                    out.flush()
                    os.fsync(out.fileno())
                os.link(name, dest)  # atomic no-replace publish
            finally:
                Path(name).unlink(missing_ok=True)
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"MIDIVOLT plan error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
