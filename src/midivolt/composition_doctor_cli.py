"""K12 pre-inference Text2midi model diagnostics; no model loaded."""
from __future__ import annotations

import argparse
import json
import sys

from .composition_doctor import diagnose_composition_runtime


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midivolt-compose-doctor",
        description="Audit pinned model assets and opt-in CUDA health before real inference.",
    )
    for name in ("env", "checkout", "checkpoint", "checkpoint-sha256",
                 "vocab", "vocab-sha256", "t5-dir", "out"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--confirm-imports", action="store_true",
                   help="Opt in to import installed torch and transformers; does not import upstream code")
    p.add_argument("--cuda-smoke", action="store_true",
                   help="Opt in to a tiny CUDA kernel; requires --confirm-imports")
    p.add_argument("--require-cuda", action="store_true",
                   help="Require an actually passing CUDA kernel before declaring probe ready")
    p.add_argument("--timeout", type=float, default=90)
    p.add_argument("--confirm-model-load", action="store_true",
                   help="DANGEROUS: opt in to trusted upstream code, REMI pickle and real checkpoint deserialization; NO MIDI generation")
    p.add_argument("--model-load-timeout", type=float, default=1200)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = diagnose_composition_runtime(
            environment=args.env, checkout=args.checkout,
            checkpoint=args.checkpoint, checkpoint_sha256=args.checkpoint_sha256,
            vocab=args.vocab, vocab_sha256=args.vocab_sha256,
            t5_dir=args.t5_dir, output_path=args.out,
            confirm_imports=args.confirm_imports, cuda_smoke=args.cuda_smoke,
            require_cuda=args.require_cuda, timeout=args.timeout,
            confirm_model_load=args.confirm_model_load,
            model_load_timeout=args.model_load_timeout,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ready_for_inference_attempt"] else 3
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        print(f"MIDIVOLT model doctor error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
