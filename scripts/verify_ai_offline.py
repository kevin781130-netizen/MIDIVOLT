"""Fail-closed offline MIDIVOLT AI-to-approval regression gate (no Actions).

Default certifies only on the declared Python 3.11 runtime. An explicit
--diagnostic-unsupported-python runs tests but NEVER marks runtime accepted.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

TEST_FILES = (
    "tests/test_ai_provider_to_review_e2e.py",
    "tests/test_review_engine.py",
    "tests/test_approval_snapshot_standalone.py",
    "tests/test_candidate_cleanup_standalone.py",
    "tests/test_provider_contract_standalone.py",
)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, help="write real pytest JUnit XML to this path")
    parser.add_argument("--diagnostic-unsupported-python", action="store_true",
                        help="run on unsupported Python WITHOUT claiming release acceptance")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    supported = sys.version_info[:2] == (3, 11)
    if not supported and not args.diagnostic_unsupported_python:
        print(json.dumps({"status": "BLOCKED_PYTHON", "expected": "3.11.x",
                          "actual": sys.version.split()[0], "test_count": 0}))
        return 3
    missing = [p for p in TEST_FILES if not (root / p).is_file()]
    if missing:
        print(json.dumps({"status": "BLOCKED_MISSING_TEST_FILES", "missing": missing}))
        return 4
    if args.junit:
        if not args.junit.parent.is_dir():
            print(json.dumps({"status": "BLOCKED_MISSING_REPORT_DIR"}))
            return 4
    cmd = [sys.executable, "-m", "pytest", "-q", *TEST_FILES]
    if args.junit:
        cmd += ["--junitxml=" + str(args.junit.resolve())]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    result = subprocess.run(cmd, cwd=root, env=env, check=False)
    total = None
    if args.junit and args.junit.is_file():
        suite = ET.parse(args.junit).getroot().find("testsuite")
        if suite is not None:
            total = {k: suite.attrib[k] for k in ("tests", "failures", "errors", "skipped")}
    passed = result.returncode == 0
    print(json.dumps({"status": "PASS_SUPPORTED_RUNTIME" if supported and passed
                      else "PASS_DIAGNOSTIC_UNSUPPORTED_RUNTIME" if passed
                      else "FAILED_TESTS", "python": sys.version.split()[0],
                      "pytest_exit": result.returncode, "suite": total}, sort_keys=True))
    return 0 if passed else result.returncode or 1


if __name__ == "__main__":
    raise SystemExit(run())
