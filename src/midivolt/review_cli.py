"""Proposal -> review -> explicit apply for MIDIVOLT arrangement candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .review_engine import apply_proposal, check_proposal, create_proposal


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="midivolt-review")
    sub = p.add_subparsers(dest="operation", required=True)
    propose = sub.add_parser("propose", help="Create reviewed MIDI candidate (without modifying source)")
    propose.add_argument("--input", required=True)
    mode = propose.add_mutually_exclusive_group(required=True)
    mode.add_argument("--candidate", help="Existing MIDI from any generator or agent")
    mode.add_argument("--chords", help="Generate chord/bass arrangement proposal locally")
    propose.add_argument("--candidate-out", help="New candidate MIDI path when using --chords")
    propose.add_argument("--manifest", required=True)
    propose.add_argument("--lock", type=int, action="append", required=True,
                         help="Track index to preserve (repeat for multiple tracks)")
    propose.add_argument("--beats-per-chord", type=float, default=4)
    propose.add_argument("--no-bass", action="store_true")
    preview = sub.add_parser("preview", help="Verify content hashes and print differences")
    preview.add_argument("--manifest", required=True)
    apply = sub.add_parser("apply", help="Apply reviewed candidate to a NEW MIDI file")
    apply.add_argument("--manifest", required=True)
    apply.add_argument("--out", required=True)
    apply.add_argument("--approve", action="store_true",
                       help="Explicit approval required before writing a project")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "propose":
            candidate = args.candidate
            if args.chords is not None:
                if not args.candidate_out:
                    raise ValueError("--candidate-out is required with --chords.")
                original, candidate, manifest = (
                    Path(args.input).resolve(), Path(args.candidate_out).resolve(),
                    Path(args.manifest).resolve(),
                )
                if len({original, candidate, manifest}) != 3:
                    raise ValueError("Input, candidate and manifest must be separate.")
                if manifest.exists() or candidate.exists():
                    raise FileExistsError("Candidate or manifest already exists.")
                # Lazy import: externally generated MIDI proposals don't need music21.
                from .arrange import add_accompaniment
                from .io import read_midi, write_midi
                generated = add_accompaniment(
                    read_midi(original), args.chords,
                    beats_per_chord=args.beats_per_chord,
                    add_bass=not args.no_bass,
                )
                write_midi(generated, candidate)
            else:
                if args.candidate_out:
                    raise ValueError("--candidate-out only works with --chords.")
            result = create_proposal(
                args.input, candidate, args.manifest, locked_tracks=args.lock
            )
            output = result["review"]
        elif args.operation == "preview":
            _, output = check_proposal(args.manifest)
        else:
            output = apply_proposal(
                args.manifest, args.out, approved=args.approve
            )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, PermissionError, KeyError,
            TypeError, IndexError) as exc:
        print(f"MIDIVOLT review error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
