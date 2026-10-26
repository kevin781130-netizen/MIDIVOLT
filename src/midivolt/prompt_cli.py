"""MIDIVOLT text instruction -> editable MIDI baseline.

Unlike an LLM music generator, this is a *deterministic* local
arrangement sketcher. Audio-to-MIDI and provider-based AI are separate
capabilities. No third-party trademarks or weights are used.
"""
from __future__ import annotations

import argparse
import json
import sys

from .io import read_midi, write_midi
from .prompt_music import parse_prompt, generate_sketch, report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="midivolt-prompt", description=__doc__)
    p.add_argument("--prompt", required=True,
                   help="e.g. '8 bars of sparse melody in D minor at 110 bpm'")
    p.add_argument("--out", required=True, help="New Standard MIDI file path")
    p.add_argument("--input", help="Existing Standard MIDI to extend non-destructively")
    p.add_argument("--bars", type=int, help="Override number of generated bars (1..32)")
    p.add_argument("--bpm", type=float, help="Override tempo, or match source MIDI BPM")
    p.add_argument("--key", help="Pitch class, e.g. D, F#, Bb")
    p.add_argument("--mode", choices=["major", "minor"])
    p.add_argument("--parts", nargs="+", choices=["chords", "melody", "bass", "drums"],
                   help="Which separate MIDI parts to generate")
    p.add_argument("--seed", type=int, help="Stable 32-bit seed for variations")
    p.add_argument("--overwrite", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        original = read_midi(args.input) if args.input else None
        explicit = args.bpm
        if original is not None:
            _, tempo = original.get_tempo_changes()
            if len(tempo) != 1:
                raise ValueError("Cannot extend varying source tempo")
            if explicit is None:
                # Source tempo must be the timing source, never prompt text.
                explicit = float(tempo[0])
        spec = parse_prompt(
            args.prompt, key=args.key, mode=args.mode,
            bars=args.bars, bpm=explicit,
            parts=tuple(args.parts) if args.parts else None,
            seed=args.seed,
        )
        result = generate_sketch(spec, source=original)
        write_midi(result, args.out, overwrite=args.overwrite)
        print(json.dumps(
            {**report(spec, result, extended=original is not None),
             "output": args.out}, ensure_ascii=False, indent=2,
        ))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"MIDIVOLT prompt error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
