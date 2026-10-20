"""MIDIVOLT Model Hub CLI: local-first, network/download only with opt-in."""
from __future__ import annotations

import argparse
import json
import math
import sys

from .model_hub import (
    CATALOG, ModelHubError, catalog, doctor, download_asset,
    inspect_model, search_models,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midivolt-hub",
        description="Curated AI MIDI model catalog, compatibility and opt-in downloads.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("catalog", help="Offline curated models; no network")
    c.add_argument("--query")
    s = sub.add_parser("search", help="Offline curated search; --online queries Hugging Face")
    s.add_argument("query")
    s.add_argument("--online", action="store_true")
    s.add_argument("--limit", type=int, default=10)
    i = sub.add_parser("inspect", help="Inspect catalog or remote model metadata")
    i.add_argument("model", choices=sorted(CATALOG))
    i.add_argument("--online", action="store_true")
    d = sub.add_parser("doctor", help="Read-only local runtime readiness checks")
    d.add_argument("model", choices=sorted(CATALOG))
    for flag in ("python", "checkout", "checkpoint", "vocab", "t5-dir"):
        d.add_argument("--" + flag)
    f = sub.add_parser("download", help="Fetch ONE verified file from pinned HF commit")
    f.add_argument("model", choices=sorted(CATALOG))
    f.add_argument("--file", required=True)
    f.add_argument("--revision", required=True, help="Full 40-character git commit SHA")
    f.add_argument("--dest", required=True, help="Existing local directory")
    f.add_argument("--accept-license", required=True)
    f.add_argument("--confirm-download", action="store_true")
    f.add_argument("--allow-unsafe-format", action="store_true")
    f.add_argument("--max-mb", type=int, default=2000,
                   help="Size cap in decimal MB (default 2000)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "catalog":
            result = {"models": catalog(args.query), "network_used": False}
        elif args.command == "search":
            result = search_models(args.query, online=args.online, limit=args.limit)
        elif args.command == "inspect":
            result = inspect_model(args.model, online=args.online)
        elif args.command == "doctor":
            result = doctor(
                args.model, python=args.python, checkout=args.checkout,
                checkpoint=args.checkpoint, vocab=args.vocab, t5_dir=args.t5_dir,
            )
        else:
            if not 1 <= args.max_mb <= 8000:
                raise ValueError("--max-mb must be 1..8000")
            result = download_asset(
                args.model, args.file, args.revision, args.dest,
                confirm=args.confirm_download, accept_license=args.accept_license,
                allow_unsafe_format=args.allow_unsafe_format,
                max_bytes=args.max_mb * 1_000_000,
            )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, PermissionError, OSError, ModelHubError) as exc:
        print(f"MIDIVOLT Model Hub error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
