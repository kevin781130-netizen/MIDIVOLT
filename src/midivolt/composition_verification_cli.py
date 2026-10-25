"""Verify saved K13 outputs independently, without model/GPU/DAW execution."""
from __future__ import annotations

import argparse
import json
import sys

from .composition_verification import verify_benchmark_evidence


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midivolt-compose-verify",
        description="Recompute K13 summary and K9-audit each K8 MIDI result, without running a model.",
    )
    p.add_argument("--benchmark", required=True, help="Existing K13 benchmark.json")
    p.add_argument("--out-dir", required=True, help="NEW directory for K14 audit output")
    p.add_argument("--doctor", help="Optional K12 model environment evidence JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_benchmark_evidence(
            args.benchmark, output_dir=args.out_dir, doctor_report=args.doctor
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["all_cases_accepted"] else 3
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        # Deliberately exclude model stderr, prompts, and local paths from
        # terminal diagnostics; do not confuse a parse error with success.
        print(f"MIDIVOLT K14 benchmark verification failed: {type(exc).__name__}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
