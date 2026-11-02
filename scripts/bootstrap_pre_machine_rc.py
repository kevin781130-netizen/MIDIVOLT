"""One-command MIDIVOLT offline pre-machine gate bootstrap, with explicit network consent.

Downloads package dependencies only when --allow-network is specified. Neither mode
runs GitHub Actions, contacts any AI provider, nor mutates the Git commit.
The gate (not this bootstrap) decides PASS_PRE_MACHINE after real tests and installs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], env: dict[str, str], timeout: int = 600) -> dict:
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=timeout, check=False)
        record = {"status": "PASS" if result.returncode == 0 else "FAIL",
                  "exit_code": result.returncode, "stderr_tail": result.stderr[-1200:],
                  "stdout_tail": result.stdout[-1200:]}
        # The release gate produces a multi-kilobyte one-line JSON report.
        # Parse its *complete* last line before truncating diagnostic output.
        try:
            record["json_result"] = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            pass
        return record
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "BLOCKED", "reason": type(exc).__name__}


def bootstrap(*, allow_network: bool = False, wheelhouse: Path | None = None) -> dict:
    result: dict = {"status": "BLOCKED", "stage": "PRECHECK", "certified": False}
    if not allow_network and wheelhouse is None:
        result["reason"] = "PROVIDE_TRUSTED_WHEELHOUSE_OR_ALLOW_NETWORK"
        return result
    if wheelhouse is not None and allow_network:
        result["reason"] = "CHOOSE_NETWORK_OR_OFFLINE_NOT_BOTH"
        return result
    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        result["reason"] = "UNSUPPORTED_BOOTSTRAP_PYTHON"
        return result
    if wheelhouse is not None and (not wheelhouse.is_dir() or wheelhouse.is_symlink()):
        result["reason"] = "INVALID_TRUSTED_WHEELHOUSE"
        return result
    env = os.environ.copy()
    env.update({"PIP_CONFIG_FILE": os.devnull, "PIP_NO_INPUT": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONNOUSERSITE": "1"})
    head = run(["git", "rev-parse", "HEAD"], env, 20)
    if head["status"] != "PASS" or not re.fullmatch(r"[0-9a-f]{40}", head["stdout_tail"].strip()):
        result["reason"] = "UNVERIFIED_GIT_HEAD"
        return result
    sha = head["stdout_tail"].strip()
    result["commit"] = sha
    clean = run(["git", "status", "--porcelain", "--untracked-files=all"], env, 20)
    if clean["status"] != "PASS" or clean["stdout_tail"].strip():
        result["reason"] = "DIRTY_GIT_CHECKOUT"
        return result
    # The complete repository test suite includes upstream model environments
    # that accept Python 3.10/3.11 only, while the product core accepts 3.11-3.13.
    # Core and the model suite overlap only at 3.11. Do not waste package
    # downloads or imply an unsupported model runtime can be fully certified.
    if sys.version_info[:2] != (3, 11):
        result["reason"] = "PYTHON311_REQUIRED_FOR_FULL_PRODUCT_SUITE"
        return result
    with tempfile.TemporaryDirectory(prefix="midivolt-rc-bootstrap-") as temp:
        tmp = Path(temp)
        wheels = tmp / "wheels" if allow_network else wheelhouse
        if allow_network:
            wheels.mkdir()
            result["stage"] = "WHEELHOUSE_DOWNLOAD"
            # Populate dependency wheels without installing into the host environment.
            for args in (
                [sys.executable, "-m", "pip", "download", "--only-binary=:all:",
                 "--dest", str(wheels), "setuptools>=77", "wheel"],
                [sys.executable, "-m", "pip", "wheel", "--only-binary=:all:",
                 "--wheel-dir", str(wheels), ".[dev]"],
            ):
                outcome = run(args, env, 600)
                if outcome["status"] != "PASS":
                    result["reason"] = "DEPENDENCY_DOWNLOAD_OR_BUILD_FAILED"
                    result["details"] = outcome
                    return result
        result["stage"] = "ISOLATED_ENV_INSTALL"
        envdir = tmp / "venv"
        try:
            venv.EnvBuilder(with_pip=True).create(envdir)
        except (OSError, subprocess.CalledProcessError) as exc:
            result["reason"] = "VENV_CREATION_FAILED"
            result["error"] = type(exc).__name__
            return result
        python = envdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        base = [str(python), "-m", "pip", "install", "--no-index", "--find-links", str(wheels), "--no-input"]
        for cmd in (base + ["setuptools>=77", "wheel", "pytest>=8,<10"],
                    base + ["--no-build-isolation", "-e", ".[dev]"]):
            install = run(cmd, env, 600)
            if install["status"] != "PASS":
                result["reason"] = "ISOLATED_INSTALL_FAILED"
                result["details"] = install
                return result
        result["stage"] = "SEVEN_RELEASE_GATES"
        validation = run([str(python), "scripts/verify_pre_machine_rc.py",
                          "--wheelhouse", str(wheels), "--expected-head", sha], env, 1200)
        result["gate_exit"] = validation.get("exit_code")
        if isinstance(validation.get("json_result"), dict):
            result["gate_report"] = validation["json_result"]
        else:
            result["gate_output_tail"] = validation.get("stdout_tail", "")
        if validation["status"] != "PASS" or result.get("gate_report", {}).get("status") != "PASS_PRE_MACHINE":
            result["reason"] = "PRE_MACHINE_GATE_NOT_PASSED"
            result["gate_stderr_tail"] = validation.get("stderr_tail", "")
            return result
    result.update(status="PASS_PRE_MACHINE", stage="COMPLETE", certified=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--allow-network", action="store_true", help="explicitly allow PyPI dependencies download")
    group.add_argument("--wheelhouse", type=Path, help="trusted complete local dependency wheelhouse")
    args = parser.parse_args()
    report = bootstrap(allow_network=args.allow_network, wheelhouse=args.wheelhouse)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS_PRE_MACHINE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
