"""Offline install-and-import acceptance for an exact MIDIVOLT wheel.

Requires a trusted local wheelhouse. No network, no trained models, no Actions.
The installed core runtime must satisfy the current project Requires-Python.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import venv

from verify_rc_wheel import inspect_wheel

def supported_python(spec: str, version: tuple[int, int] | None = None) -> bool:
    """Fail closed on unknown Requires-Python syntax (core RC is an exact range)."""
    match = re.fullmatch(r">=(\d+)\.(\d+),<(\d+)\.(\d+)", spec)
    if not match:
        return False
    current = version if version is not None else sys.version_info[:2]
    return (int(match[1]), int(match[2])) <= current < (int(match[3]), int(match[4]))


EXPECTED_SCRIPTS = (
    "midivolt", "midivolt-prompt", "midivolt-ai", "midivolt-bridge",
    "midivolt-tsov", "midivolt-review", "midivolt-model", "midivolt-hub",
    "midivolt-env", "midivolt-accept", "midivolt-cubase",
    "midivolt-transcribe", "midivolt-evaluate",
)

# Runs in an isolated Python venv, imports all registered CLI targets, but does
# NOT execute any model, network operation, or music composition command.
CHECK_SCRIPT = r'''
from importlib import metadata
import json, os, sys
from pathlib import Path
wanted = json.loads(sys.argv[1]); expected = sys.argv[2]
dist = metadata.distribution("midivolt")
registered = {e.name:e for e in dist.entry_points if e.group == "console_scripts"}
if dist.version != expected: raise RuntimeError("Installed MIDIVOLT version mismatch")
if set(registered) != set(wanted): raise RuntimeError("Installed console script list mismatch")
bin_dir = Path(sys.executable).parent
missing = [name for name in wanted if not (bin_dir / (name + (".exe" if os.name == "nt" else ""))).is_file()]
if missing: raise RuntimeError("Missing installed CLI launchers: " + repr(missing))
loaded = []
for name in wanted:
    obj = registered[name].load()
    if not callable(obj): raise RuntimeError("CLI target not callable: " + name)
    loaded.append(name)
print(json.dumps({"installed_version":dist.version,"loaded_cli":loaded,"launchers_checked":len(loaded)}))
'''


def inspect_install(wheel: Path, project: Path, wheelhouse: Path, expected_sha256: str,
                    *, diagnostic_unsupported_python: bool = False) -> dict:
    """Fail closed: SHA/source contract -> offline venv install -> all CLIs load."""
    result = {
        "status": "BLOCKED", "python": sys.version.split()[0],
        "supported_python": False,
        "supported_runtime_certified": False, "installation_attempted": False,
        "installed_cli_count": 0, "errors": [],
    }
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        result["errors"].append("INVALID_EXPECTED_SHA256")
        return result
    if not wheel.is_file() or not wheelhouse.is_dir() or not project.is_file():
        result["errors"].append("MISSING_LOCAL_WHEEL_PROJECT_OR_WHEELHOUSE")
        return result
    if any(p.is_symlink() for p in (wheel, wheelhouse, project)):
        result["errors"].append("SYMLINK_INPUT_REJECTED")
        return result
    try:
        project_metadata = tomllib.loads(project.read_text(encoding="utf-8"))["project"]
        result["supported_python"] = supported_python(project_metadata["requires-python"])
    except (OSError, UnicodeError, KeyError, ValueError, tomllib.TOMLDecodeError):
        result["errors"].append("INVALID_PROJECT_PYTHON_POLICY")
        return result
    if not result["supported_python"] and not diagnostic_unsupported_python:
        result["errors"].append("PYTHON_VERSION_OUTSIDE_PROJECT_RANGE")
        return result
    digest = sha256(wheel.read_bytes()).hexdigest()
    result["sha256"] = digest
    if digest.lower() != expected_sha256.lower():
        result["errors"].append("WHEEL_SHA256_MISMATCH")
        return result
    artifact = inspect_wheel(wheel, project)
    if artifact["status"] != "PASS_WHEEL_INTEGRITY_NOT_INSTALLATION":
        result["errors"].append("WHEEL_SOURCE_OR_METADATA_INVALID")
        result["artifact_errors"] = artifact["errors"]
        return result
    # No implicit index, no sdist builds, no pip config, no model inference.
    environment = os.environ.copy()
    environment.update({"PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1",
                        "PIP_NO_INPUT": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                        "PYTHONNOUSERSITE": "1"})
    try:
        with tempfile.TemporaryDirectory(prefix="midivolt-verified-install-") as temp:
            venv_dir = Path(temp) / "venv"
            venv.EnvBuilder(with_pip=True).create(venv_dir)
            python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if not python.is_file():
                result["errors"].append("VENV_PYTHON_MISSING")
                return result
            command = [str(python), "-m", "pip", "install", "--no-index",
                       "--no-input", "--only-binary=:all:", "--find-links", str(wheelhouse.resolve())]
            if not result["supported_python"]:
                command.append("--ignore-requires-python")
            command.append(str(wheel.resolve()))
            result["installation_attempted"] = True
            proc = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=120)
            if proc.returncode:
                result["errors"].append("OFFLINE_PIP_INSTALL_FAILED")
                result["pip_error_tail"] = proc.stderr[-900:]
                return result
            expected_version = artifact["wheel"].name if isinstance(artifact["wheel"], Path) else wheel.name
            match = re.match(r"midivolt-([^-]+)-", expected_version)
            if not match:
                result["errors"].append("INVALID_WHEEL_FILENAME")
                return result
            check = subprocess.run([str(python), "-I", "-c", CHECK_SCRIPT,
                                    json.dumps(EXPECTED_SCRIPTS), match.group(1)],
                                   capture_output=True, text=True, env=environment, timeout=90)
            if check.returncode:
                result["errors"].append("INSTALLED_CLI_LOAD_FAILED")
                result["load_error_tail"] = check.stderr[-1200:]
                return result
            loaded = json.loads(check.stdout.strip().splitlines()[-1])
            result["installed_cli_count"] = loaded["launchers_checked"]
            if result["installed_cli_count"] != 13:
                result["errors"].append("MISSING_CLI_LAUNCHERS")
                return result
            result["status"] = ("PASS_SUPPORTED_PYTHON_INSTALL" if result["supported_python"]
                                else "PASS_DIAGNOSTIC_UNSUPPORTED_PYTHON")
            result["supported_runtime_certified"] = result["supported_python"]
            return result
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        result["errors"].append("ENVIRONMENT_OR_INSTALL_EXCEPTION:" + type(exc).__name__)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1] / "pyproject.toml")
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="independently trusted SHA256")
    parser.add_argument("--diagnostic-unsupported-python", action="store_true")
    a = parser.parse_args(argv)
    result = inspect_install(a.wheel, a.project, a.wheelhouse, a.sha256,
                             diagnostic_unsupported_python=a.diagnostic_unsupported_python)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
