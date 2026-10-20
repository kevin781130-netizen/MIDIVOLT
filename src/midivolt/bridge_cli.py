"""Sawdust and tsov interoperability entry point."""

from __future__ import annotations

import argparse
import json
import sys

from .bridges import prepare_bridge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="midivolt-bridge", description="Export MIDIVOLT MIDI for Sawdust/tsov"
    )
    parser.add_argument("--target", choices=("sawdust", "tsov"), required=True)
    parser.add_argument("--input", required=True, help="Existing MIDI file")
    parser.add_argument("--out", required=True, help="New MIDI file for host import")
    parser.add_argument(
        "--quantize", action="store_true",
        help="Explicitly snap note boundaries to Sawdust's 24-step grid (lossy)",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = prepare_bridge(
            args.input, args.out, args.target,
            quantize=args.quantize, overwrite=args.overwrite,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"MIDIVOLT bridge error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
