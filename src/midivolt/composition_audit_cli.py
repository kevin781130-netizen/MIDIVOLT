"""Inspect an existing K8 report and candidate; never execute an AI model or Cubase."""
from __future__ import annotations

import argparse
import json
import sys

from .composition_audit import audit_composition_acceptance


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midivolt-compose-audit",
        description="Replay-check K8 MIDI acceptance evidence; compare optional DAW re-export.",
    )
    p.add_argument("--acceptance", required=True, help="Existing K8 acceptance.json")
    p.add_argument("--out", required=True, help="NEW K9 audit report .json")
    p.add_argument("--cubase-return", help="Optional separate MIDI file manually exported by DAW")
    return p


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_args(argv)
    try:
        result = audit_composition_acceptance(
            opts.acceptance, output_path=opts.out, cubase_return=opts.cubase_return
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        print(f"MIDIVOLT composition audit error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
