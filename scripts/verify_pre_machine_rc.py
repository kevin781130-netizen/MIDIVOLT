"""Fail-closed MIDIVOLT offline pre-machine release gate.

PASS_PRE_MACHINE means all included software checks passed on this exact checkout.
It does NOT certify Cubase, Windows installer, model quality, or commercial release.
No network, GitHub Actions, installer execution, or source modifications.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("source_contract", "full_pytest", "ai_regression", "music21", "wheel_build", "wheel_integrity", "wheel_install")


def run_command(cmd: list[str], *, env: dict[str, str], timeout: int = 300) -> dict:
    try:
        result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                                text=True, check=False, timeout=timeout)
        return {"status": "PASS" if result.returncode == 0 else "FAIL",
                "exit_code": result.returncode, "stdout_tail": result.stdout[-1800:],
                "stderr_tail": result.stderr[-1800:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "BLOCKED", "error": type(exc).__name__}


def release_gate(wheelhouse: Path | None, expected_head: str | None = None) -> dict:
    report: dict = {"status": "BLOCKED", "python": sys.version.split()[0],
                    "stages": {}, "scope": "CLI_CORE_PRE_MACHINE_ONLY",
                    "real_machine_required": ["Windows PowerShell installer",
                     "Cubase graphical SMF import/export", "true provider/model artistic evaluation",
                     "Python 3.11 Basic Pitch real WAV if audio transcription sold"]}
    try:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
        if project.get("name") != "midivolt" or project.get("requires-python") != ">=3.11,<3.14":
            report["reason"] = "INVALID_CORE_PYTHON_POLICY"
            return report
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError):
        report["reason"] = "MISSING_OR_INVALID_PROJECT"
        return report
    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        report["reason"] = "UNSUPPORTED_PYTHON"
        return report
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(ROOT / "src"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PIP_NO_INDEX": "1", "PIP_CONFIG_FILE": os.devnull,
                "PIP_NO_INPUT": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
    if expected_head is not None:
        head = run_command(["git", "rev-parse", "HEAD"], env=env, timeout=15)
        if head["status"] != "PASS" or head["stdout_tail"].strip() != expected_head:
            report["reason"] = "CHECKOUT_HEAD_MISMATCH"
            return report
    for stage, cmd in (
        ("source_contract", [sys.executable, "scripts/verify_rc_source_contract.py", "--root", str(ROOT)]),
        ("full_pytest", [sys.executable, "-m", "pytest", "-q", "tests"]),
        ("ai_regression", [sys.executable, "scripts/verify_ai_offline.py"]),
        ("music21", [sys.executable, "scripts/accept_music21_core.py"]),
    ):
        output = run_command(cmd, env=env)
        report["stages"][stage] = output
        if output["status"] != "PASS":
            report["reason"] = "STOP_AT_" + stage.upper()
            return report
        if stage == "music21" and "PASS_REAL_MUSIC21_ACCEPTANCE" not in output["stdout_tail"]:
            report["stages"][stage]["status"] = "FAIL"
            report["reason"] = "MUSIC21_SUCCESS_MARKER_MISSING"
            return report
        if stage == "ai_regression" and "PASS_SUPPORTED_RUNTIME" not in output["stdout_tail"]:
            report["stages"][stage]["status"] = "FAIL"
            report["reason"] = "AI_SUCCESS_MARKER_MISSING"
            return report
    with tempfile.TemporaryDirectory(prefix="midivolt-pre-machine-") as temp:
        dist = Path(temp) / "dist"
        dist.mkdir()
        build = run_command([sys.executable, "-m", "pip", "wheel", "--no-index",
                             "--no-deps", "--no-build-isolation", "--wheel-dir", str(dist), str(ROOT)],
                            env=env, timeout=180)
        report["stages"]["wheel_build"] = build
        if build["status"] != "PASS":
            report["reason"] = "STOP_AT_WHEEL_BUILD"
            return report
        wheels = list(dist.glob("midivolt-*.whl"))
        if len(wheels) != 1:
            report["reason"] = "WHEEL_COUNT_NOT_ONE"
            return report
        wheel = wheels[0]
        digest = sha256(wheel.read_bytes()).hexdigest()
        report["wheel_sha256"] = digest
        integrity = run_command([sys.executable, "scripts/verify_rc_wheel.py",
                                  "--wheel", str(wheel), "--project", str(ROOT / "pyproject.toml")], env=env)
        report["stages"]["wheel_integrity"] = integrity
        if integrity["status"] != "PASS" or "PASS_WHEEL_INTEGRITY_NOT_INSTALLATION" not in integrity["stdout_tail"]:
            report["reason"] = "STOP_AT_WHEEL_INTEGRITY"
            return report
        if wheelhouse is None or not wheelhouse.is_dir() or wheelhouse.is_symlink():
            report["stages"]["wheel_install"] = {"status": "BLOCKED", "reason": "AUDITED_WHEELHOUSE_REQUIRED"}
            report["reason"] = "DEPENDENCY_COMPLETE_INSTALL_NOT_RUN"
            return report
        install = run_command([sys.executable, "scripts/verify_rc_wheel_install.py",
                               "--wheel", str(wheel), "--project", str(ROOT / "pyproject.toml"),
                               "--wheelhouse", str(wheelhouse), "--sha256", digest], env=env, timeout=240)
        report["stages"]["wheel_install"] = install
        if install["status"] != "PASS" or "PASS_SUPPORTED_PYTHON_INSTALL" not in install["stdout_tail"]:
            report["reason"] = "STOP_AT_WHEEL_INSTALL"
            return report
    report["status"] = "PASS_PRE_MACHINE"
    report["reason"] = "ONLY_REAL_APPLICATION_AND_PROVIDER_ACCEPTANCE_REMAINS_FOR_DECLARED_SCOPE"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, help="audited offline dependency wheels; required for PASS")
    parser.add_argument("--expected-head", help="exact 40-character git revision to certify")
    args = parser.parse_args()
    result = release_gate(args.wheelhouse, args.expected_head)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS_PRE_MACHINE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
