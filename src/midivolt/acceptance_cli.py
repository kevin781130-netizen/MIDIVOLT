"""Explicit Windows/CPU/GPU model smoke accepting only real checkpoints."""
from __future__ import annotations
import argparse
import json
import sys

from .model_hub import CATALOG
from .environments import EnvironmentError
from .acceptance import acceptance_run


def build_parser():
    p = argparse.ArgumentParser(prog="midivolt-accept")
    p.add_argument("model", choices=sorted(CATALOG))
    for field in ("env", "checkout", "checkpoint", "source", "out", "manifest", "report"):
        p.add_argument("--" + field, required=True)
    p.add_argument("--lock", type=int, action="append", required=True)
    p.add_argument("--confirm-inference", action="store_true")
    p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--seed", type=int, default=123)
    p.add_argument("--prompt")
    p.add_argument("--vocab")
    p.add_argument("--t5-dir")
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--max-tokens", type=int, default=2000)
    p.add_argument("--melody-program", type=int)
    p.add_argument("--seconds", type=float)
    p.add_argument("--top-p", type=float, default=0.98)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        result = acceptance_run(
            model=a.model, environment=a.env, checkout=a.checkout,
            checkpoint=a.checkpoint, source=a.source,
            out=a.out, manifest=a.manifest, report=a.report,
            locked_tracks=a.lock, confirm_inference=a.confirm_inference,
            timeout=a.timeout, seed=a.seed, prompt=a.prompt,
            vocab_path=a.vocab, t5_dir=a.t5_dir,
            temperature=a.temperature, max_tokens=a.max_tokens,
            melody_program=a.melody_program, seconds=a.seconds, top_p=a.top_p,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, PermissionError, RuntimeError,
            EnvironmentError) as exc:
        print(f"MIDIVOLT acceptance error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
