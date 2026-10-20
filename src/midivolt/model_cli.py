"""MIDIVOLT optional model-inference command."""
from __future__ import annotations
import argparse
import json
import sys
from .model_adapters import generate_candidate

def main(argv=None):
    p = argparse.ArgumentParser(prog="midivolt-model")
    modes = p.add_subparsers(dest="model", required=True)
    for name in ("text2midi", "anticipation"):
        m = modes.add_parser(name)
        for opt in ("python", "checkout", "checkpoint", "out"):
            m.add_argument("--" + opt, required=True)
        m.add_argument("--source")
        m.add_argument("--manifest")
        m.add_argument("--lock", type=int, action="append")
        m.add_argument("--timeout", type=float, default=1200)
        m.add_argument("--seed", type=int)
        if name == "text2midi":
            for opt in ("prompt", "vocab", "t5-dir"):
                m.add_argument("--" + opt, required=True)
            m.add_argument("--temperature", type=float, default=0.9)
            m.add_argument("--max-tokens", type=int, default=2000)
        else:
            m.add_argument("--melody-program", type=int, required=True)
            m.add_argument("--seconds", type=float, required=True)
            m.add_argument("--top-p", type=float, default=0.98)
    a = p.parse_args(argv)
    try:
        result = generate_candidate(
            model=a.model, python_executable=a.python, checkout=a.checkout,
            checkpoint=a.checkpoint, output_path=a.out, source_path=a.source,
            manifest_path=a.manifest, locked_tracks=a.lock,
            timeout=a.timeout, seed=a.seed, prompt=getattr(a, "prompt", None),
            vocab_path=getattr(a, "vocab", None), t5_dir=getattr(a, "t5_dir", None),
            temperature=getattr(a, "temperature", 0.9),
            max_tokens=getattr(a, "max_tokens", 2000),
            melody_program=getattr(a, "melody_program", None),
            seconds=getattr(a, "seconds", None), top_p=getattr(a, "top_p", 0.98),
        )
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"MIDIVOLT model error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
