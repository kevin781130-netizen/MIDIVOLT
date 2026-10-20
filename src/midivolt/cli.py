"""MIDIVOLT CLI for creating, arranging, analyzing and transcribing MIDI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pretty_midi

from .arrange import add_accompaniment
from .io import read_midi, write_midi
from .theory import estimate_key


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="midivolt", description="MIDIVOLT MIDI tools")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create chord and bass MIDI tracks")
    create.add_argument("--chords", required=True)
    create.add_argument("--bpm", type=float, default=120.0)
    create.add_argument("--out", required=True)
    create.add_argument("--beats-per-chord", type=float, default=4.0)
    create.add_argument("--no-bass", action="store_true")
    create.add_argument("--overwrite", action="store_true")

    arrange = sub.add_parser("arrange", help="Add accompaniment without editing input tracks")
    arrange.add_argument("--input", required=True)
    arrange.add_argument("--chords", required=True)
    arrange.add_argument("--out", required=True)
    arrange.add_argument("--beats-per-chord", type=float, default=4.0)
    arrange.add_argument("--no-bass", action="store_true")
    arrange.add_argument("--overwrite", action="store_true")

    analyze = sub.add_parser("analyze", help="Print a MIDI summary and estimated key")
    analyze.add_argument("--input", required=True)

    transcribe = sub.add_parser("transcribe", help="Audio-to-MIDI using optional Basic Pitch")
    transcribe.add_argument("--input", required=True)
    transcribe.add_argument("--out", required=True)
    transcribe.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create":
            if not 1 <= args.bpm <= 500:
                raise ValueError("bpm must be within 1..500.")
            midi = pretty_midi.PrettyMIDI(initial_tempo=args.bpm)
            arranged = add_accompaniment(
                midi, args.chords, beats_per_chord=args.beats_per_chord,
                add_bass=not args.no_bass,
            )
            write_midi(arranged, args.out, overwrite=args.overwrite)
            print(f"Saved {args.out}")
        elif args.command == "arrange":
            if Path(args.input).resolve() == Path(args.out).resolve() and not args.overwrite:
                raise ValueError("Input and output refer to the same file; specify --overwrite.")
            original = read_midi(args.input)
            arranged = add_accompaniment(
                original, args.chords, beats_per_chord=args.beats_per_chord,
                add_bass=not args.no_bass,
            )
            write_midi(arranged, args.out, overwrite=args.overwrite)
            print(f"Saved {args.out}")
        elif args.command == "analyze":
            midi = read_midi(args.input)
            times, tempos = midi.get_tempo_changes()
            report = {
                "estimated_key": estimate_key(midi),
                "duration_seconds": round(midi.get_end_time(), 3),
                "tempo_changes": [
                    {"time": round(float(t), 3), "bpm": round(float(bpm), 3)}
                    for t, bpm in zip(times, tempos)
                ],
                "tracks": [
                    {
                        "name": str(inst.name), "program": int(inst.program),
                        "is_drum": bool(inst.is_drum), "notes": len(inst.notes),
                    }
                    for inst in midi.instruments
                ],
            }
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            from .audio import transcribe_audio

            transcribe_audio(args.input, args.out, overwrite=args.overwrite)
            print(f"Saved {args.out}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"MIDIVOLT error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
