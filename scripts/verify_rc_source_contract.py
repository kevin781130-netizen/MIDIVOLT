"""Offline, dependency-free MIDIVOLT Windows RC source/package contract check.

This is a PRE-BUILD check. It does not claim the wheel can be installed,
that Python 3.11 works, or that Cubase has been exercised.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys
import tomllib

REQUIRED_ASSETS = (
    "packaging/windows/Install-MIDIVOLT.ps1",
    "packaging/windows/Smoke-MIDIVOLT.ps1",
    "packaging/windows/README-Windows.txt",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
)


def inspect(root: Path) -> dict:
    """Fail closed on missing release inputs and non-existent advertised CLIs."""
    root = root.resolve()
    errors: list[str] = []

    def read(name: str) -> str:
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            errors.append("MISSING_OR_UNSAFE:" + name)
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            errors.append("UNREADABLE:" + name)
            return ""

    pyproject = read("pyproject.toml")
    try:
        manifest = tomllib.loads(pyproject)
    except tomllib.TOMLDecodeError:
        errors.append("INVALID_PYPROJECT")
        manifest = {}
    project = manifest.get("project", {})
    version = project.get("version")
    if project.get("name") != "midivolt" or not re.fullmatch(r"\d+\.\d+\.\d+rc\d+", str(version)):
        errors.append("INVALID_PROJECT_VERSION")
    if project.get("requires-python") != ">=3.11,<3.12":
        errors.append("RUNTIME_CONTRACT_MISMATCH")
    if manifest.get("build-system", {}).get("build-backend") != "setuptools.build_meta":
        errors.append("BUILD_BACKEND_MISMATCH")
    if "wheel" not in manifest.get("build-system", {}).get("requires", []):
        errors.append("WHEEL_BUILD_DEPENDENCY_MISSING")

    init_source = read("src/midivolt/__init__.py")
    if version and f'__version__ = "{version}"' not in init_source:
        errors.append("PACKAGE_VERSION_MISMATCH")

    scripts = project.get("scripts", {})
    if not isinstance(scripts, dict) or len(scripts) < 13:
        errors.append("CLI_DECLARATIONS_INCOMPLETE")
        scripts = scripts if isinstance(scripts, dict) else {}
    for command, target in scripts.items():
        if not isinstance(target, str) or not re.fullmatch(r"midivolt(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*", target):
            errors.append("INVALID_ENTRYPOINT:" + command)
            continue
        dotted, callable_name = target.split(":")
        rel = "src/" + dotted.replace(".", "/") + ".py"
        code = read(rel)
        if not code:
            continue
        try:
            tree = ast.parse(code, filename=rel)
        except SyntaxError:
            errors.append("INVALID_MODULE_SYNTAX:" + rel)
            continue
        if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == callable_name for node in tree.body):
            errors.append("MISSING_ENTRYPOINT_FUNCTION:" + command)

    for asset in REQUIRED_ASSETS:
        read(asset)

    workflow = read(".github/workflows/windows-rc.yml")
    expected_recipe_fragments = (
        'python -m build --wheel',
        'Compress-Archive',
        'Get-FileHash -Algorithm SHA256',
        'Copy-Item LICENSE',
        'Copy-Item THIRD_PARTY_NOTICES.md',
    )
    for token in expected_recipe_fragments:
        if token not in workflow:
            errors.append("RELEASE_RECIPE_MISSING:" + token)
    for asset in REQUIRED_ASSETS[:3]:
        if asset not in workflow:
            errors.append("RELEASE_ZIP_MISSING:" + asset)

    installer = read("packaging/windows/Install-MIDIVOLT.ps1")
    for token in ("AllowNetwork", "Wheelhouse", "--no-index", "already exists", "Smoke-MIDIVOLT.ps1"):
        if token not in installer:
            errors.append("INSTALLER_CONTRACT_MISSING:" + token)

    smoke = read("packaging/windows/Smoke-MIDIVOLT.ps1")
    for command in ("midivolt", "midivolt-hub", "midivolt-review", "midivolt-cubase", "midivolt-model", "midivolt-env", "midivolt-accept", "midivolt-tsov", "midivolt-bridge"):
        if command not in scripts or f'"{command}"' not in smoke:
            errors.append("SMOKE_CLI_MISSING:" + command)
    if "WINDOWS_RC_SMOKE=PASS" not in smoke:
        errors.append("SMOKE_SUCCESS_MARKER_MISSING")

    return {"status": "PASS_SOURCE_CONTRACT_NOT_RUNTIME" if not errors else "FAIL_SOURCE_CONTRACT",
            "python_runtime_certified": False, "wheel_built": False,
            "cli_count": len(scripts), "asset_count": len(REQUIRED_ASSETS),
            "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    result = inspect(args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    sys.exit(main())
