"""CLI to plan, create, install and verify isolated model environments."""
from __future__ import annotations
import argparse
import json
import sys

from .environments import (
    EnvironmentError, create_environment, install_requirements,
    plan_environment, verify_environment,
)
from .model_hub import CATALOG


def build_parser():
    p = argparse.ArgumentParser(prog="midivolt-env")
    sub = p.add_subparsers(dest="operation", required=True)
    for command in ("plan", "create"):
        item = sub.add_parser(command)
        item.add_argument("model", choices=sorted(CATALOG))
        item.add_argument("--checkout", required=True)
        item.add_argument("--revision", required=True,
                          help="Already approved 40-character upstream SOURCE commit")
        item.add_argument("--base-python", required=True,
                          help="Trusted local Python 3.10/3.11 interpreter")
        item.add_argument("--env", required=True,
                          help="NEW empty path outside upstream checkout")
        if command == "create":
            item.add_argument("--confirm-create", action="store_true")
    install = sub.add_parser("install")
    install.add_argument("--env", required=True)
    install.add_argument("--confirm-install", action="store_true")
    source = install.add_mutually_exclusive_group()
    source.add_argument("--wheelhouse", help="Offline pre-downloaded wheels")
    source.add_argument("--allow-network", action="store_true",
                        help="Allow pip to fetch upstream dependencies")
    install.add_argument("--timeout", type=int, default=2400)
    verify = sub.add_parser("verify")
    verify.add_argument("--env", required=True)
    verify.add_argument("--run-imports", action="store_true",
                        help="Explicitly load installed model Python modules")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.operation in ("plan", "create"):
            plan = plan_environment(
                args.model, checkout=args.checkout,
                expected_commit=args.revision,
                base_python=args.base_python, destination=args.env)
            result = (plan.as_dict() if args.operation == "plan" else
                      create_environment(plan, confirm=args.confirm_create))
        elif args.operation == "install":
            result = install_requirements(
                args.env, confirm=args.confirm_install,
                allow_network=args.allow_network, wheelhouse=args.wheelhouse,
                timeout=args.timeout)
        else:
            result = verify_environment(args.env, import_model=args.run_imports)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (OSError, ValueError, PermissionError, EnvironmentError) as exc:
        print(f"MIDIVOLT env error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
