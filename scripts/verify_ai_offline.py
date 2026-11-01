"""Offline AI→MIDI→approval acceptance gate. No GitHub Actions.

The supported-runtime PASS status requires actual Python 3.11 and verified
JUnit counts; --diagnostic-unsupported-python can never certify a release.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

TEST_FILES = (
    "tests/test_ai_provider_to_review_e2e.py",
    "tests/test_review_engine.py",
    "tests/test_approval_snapshot_standalone.py",
    "tests/test_candidate_cleanup_standalone.py",
    "tests/test_provider_contract_standalone.py",
)
MINIMUM_TESTS = 40  # Baseline measured on 2026-11-01; additions are allowed.


def inspect_junit(path: Path) -> dict[str, int]:
    """Validate pytest XML; never count skipped or incomplete collections as PASS."""
    root = ET.parse(path).getroot()
    if root.tag != "testsuites":
        raise ValueError("Expected pytest testsuites XML root")
    suites = root.findall("testsuite")
    if not suites:
        raise ValueError("JUnit report does not contain a testsuite")
    keys = ("tests", "failures", "errors", "skipped")
    totals = {key: 0 for key in keys}
    for suite in suites:
        for key in keys:
            val = int(suite.attrib[key])
            if val < 0:
                raise ValueError("Invalid negative JUnit count")
            totals[key] += val
    actual_cases = sum(len(suite.findall("testcase")) for suite in suites)
    if actual_cases != totals["tests"]:
        raise ValueError("Testcase count differs from JUnit header")
    return totals


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--junit", type=Path, help="new pytest JUnit report path; no overwrite")
    p.add_argument("--diagnostic-unsupported-python", action="store_true",
                   help="run on unsupported Python without certifying the runtime")
    args = p.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    supported = sys.version_info[:2] == (3, 11)
    if not supported and not args.diagnostic_unsupported_python:
        print(json.dumps({"status": "BLOCKED_PYTHON", "expected": "3.11.x",
                          "actual": sys.version.split()[0], "test_count": 0}))
        return 3
    missing = [name for name in TEST_FILES if not (root / name).is_file()]
    if missing:
        print(json.dumps({"status": "BLOCKED_MISSING_TEST_FILES", "missing": missing}))
        return 4
    if args.junit and (not args.junit.parent.is_dir() or args.junit.exists()):
        print(json.dumps({"status": "BLOCKED_REPORT_DESTINATION"}))
        return 4

    # Even when no persistent report was requested, collect and verify JUnit.
    with tempfile.TemporaryDirectory(prefix="midivolt-ai-gate-") as tmp:
        junit = args.junit.resolve() if args.junit else Path(tmp) / "results.junit.xml"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "src")
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env.pop("PYTEST_ADDOPTS", None)
        cmd = [sys.executable, "-m", "pytest", "-q", *TEST_FILES,
               "--junitxml=" + str(junit)]
        process = subprocess.run(cmd, cwd=root, env=env, check=False)
        try:
            counts = inspect_junit(junit)
            evidence_ok = (counts["tests"] >= MINIMUM_TESTS
                           and counts["errors"] == counts["failures"] == counts["skipped"] == 0)
            reason = "" if evidence_ok else "TEST_COUNT_OR_RESULT_INCOMPLETE"
        except (OSError, ET.ParseError, ValueError, KeyError) as exc:
            counts = None
            evidence_ok = False
            reason = "INVALID_JUNIT:" + str(exc)

    passed = process.returncode == 0 and evidence_ok
    result = {
        "status": ("PASS_SUPPORTED_RUNTIME" if passed and supported else
                   "PASS_DIAGNOSTIC_UNSUPPORTED_RUNTIME" if passed else "FAILED_VALIDATION"),
        "python": sys.version.split()[0], "pytest_exit": process.returncode,
        "suite": counts, "minimum_tests": MINIMUM_TESTS,
    }
    if reason:
        result["reason"] = reason
    print(json.dumps(result, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
