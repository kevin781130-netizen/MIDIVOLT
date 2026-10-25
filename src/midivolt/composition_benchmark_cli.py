"""K13 bounded, explicitly consented Text2midi benchmark runner."""
from __future__ import annotations

import argparse
import json
import sys

from .composition_benchmark import run_composition_benchmark


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midivolt-compose-benchmark",
        description="Run <=8 real-model strict-part cases; report failures, retries and subprocess timings.",
    )
    for flag in ("suite", "out-dir", "source", "env", "checkout",
                 "checkpoint", "checkpoint-sha256", "vocab", "vocab-sha256", "t5-dir"):
        p.add_argument("--" + flag, required=True)
    p.add_argument("--lock", type=int, action="append", required=True)
    p.add_argument("--confirm-inference", action="store_true")
    p.add_argument("--retry-per-part", type=int, default=0)
    p.add_argument("--timeout", type=float, default=1800.0,
                   help="Per model invocation timeout in seconds, includes model loading.")
    p.add_argument("--max-tokens", type=int, default=2000)
    p.add_argument("--max-new-notes", type=int, default=20000)
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--fail-fast", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_composition_benchmark(
            confirm_inference=args.confirm_inference, suite=args.suite,
            output_dir=args.out_dir, source=args.source,
            locked_tracks=tuple(args.lock), environment=args.env,
            checkout=args.checkout, checkpoint=args.checkpoint,
            checkpoint_sha256=args.checkpoint_sha256, vocab=args.vocab,
            vocab_sha256=args.vocab_sha256, t5_dir=args.t5_dir,
            quality_retries=args.retry_per_part, timeout=args.timeout,
            temperature=args.temperature, max_tokens=args.max_tokens,
            max_total_notes=args.max_new_notes, fail_fast=args.fail_fast,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["cases_failed"] == 0 else 3
    except (ValueError, TypeError, RuntimeError, OSError, KeyError, IndexError) as exc:
        # Do not include upstream model stderr or user prompts in error output.
        print(f"MIDIVOLT composition benchmark error: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
