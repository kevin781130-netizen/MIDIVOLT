"""K10 distribution checker; commercial beta defaults to fail closed."""
from __future__ import annotations

import argparse
import json
import sys

from .beta_gate import inspect_beta_package


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="midivolt-beta-gate",
        description="Inspect a built wheel/ZIP; no downloads or code execution.")
    p.add_argument("--wheel", required=True)
    p.add_argument("--windows-zip")
    p.add_argument("--zip-sha256", help="Digest independently checked against published release checksum")
    p.add_argument("--out", help="Optional NEW JSON report file")
    p.add_argument("--developer-rc", action="store_true",
        help="Return zero for verified artifact contents only; not commercial beta approval")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        report = inspect_beta_package(a.wheel, windows_zip=a.windows_zip,
                                     zip_sha256=a.zip_sha256, output_path=a.out)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        # Commercial beta remains blocked pending *independent* real model,
        # DAW, listening, security and copyright evidence.
        return 0 if a.developer_rc else 3
    except (ValueError, OSError, EOFError, RuntimeError, KeyError, IndexError) as e:
        print(f"MIDIVOLT beta gate error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
