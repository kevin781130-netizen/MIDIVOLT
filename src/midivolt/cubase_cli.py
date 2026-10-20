"""Cubase MIDI interchange profile and independent roundtrip inspection."""
from __future__ import annotations
import argparse
import json
import sys

from .cubase_smf import inspect_smf, prepare_smf, compare_smf


def build_parser():
    p = argparse.ArgumentParser(prog="midivolt-cubase")
    sub = p.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Inspect source SMF without editing it")
    check.add_argument("--input", required=True)
    prepare = sub.add_parser("prepare", help="Create Cubase-friendly Type 1 SMF")
    prepare.add_argument("--input", required=True)
    prepare.add_argument("--out", required=True)
    prepare.add_argument("--ppq", type=int, default=480,
                         help="Target MIDI ticks per quarter note, 24..960")
    compare = sub.add_parser("compare", help="Audit DAW re-export against original")
    compare.add_argument("--reference", required=True)
    compare.add_argument("--returned", required=True)
    compare.add_argument("--strict", action="store_true",
                         help="Exit nonzero if any MIDI/meta events changed")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            result = inspect_smf(args.input)
        elif args.command == "prepare":
            result = prepare_smf(args.input, args.out, ppq=args.ppq)
        else:
            result = compare_smf(args.reference, args.returned)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.command == "compare" and args.strict and not result["exact_event_match"]:
            return 3
        return 0
    except (OSError, ValueError, EOFError, TypeError) as exc:
        print(f"MIDIVOLT Cubase MIDI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
