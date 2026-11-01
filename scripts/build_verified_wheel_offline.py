"""Verified text snapshot -> real setuptools wheel, without GitHub or Actions.

This checks building and package integrity, not dependency installation or DAW.
Official acceptance requires Python 3.11; other Pythons are diagnostic only.
"""
from __future__ import annotations

import argparse
import base64
import csv
from email.parser import Parser
from hashlib import sha256
from io import StringIO
import json
import os
import re
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import tomllib
from zipfile import ZipFile

from restore_source_snapshot import SnapshotError, load_snapshot


class BuildGateError(ValueError):
    pass


# Immutable source provenance pinned independently of the mutable snapshot.
EXPECTED_SOURCE_COMMIT = "c65806b6b67ecab6e5fd1a5f2c3f8aefb5e2ddf1"


def check_wheel(wheel: Path, source: Path) -> dict:
    """Enforce exact source parity, metadata, 13 CLIs, RECORD and no ZIP dupes."""
    meta = tomllib.loads((source / "pyproject.toml").read_text("utf-8"))["project"]
    scripts = meta["scripts"]
    if meta["name"] != "midivolt" or len(scripts) != 13:
        raise BuildGateError("Package identity or 13 CLI entries mismatch")
    with ZipFile(wheel) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise BuildGateError("Duplicate ZIP entries")
        for name in names:
            parts = PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts or "\\" in name:
                raise BuildGateError("Unsafe wheel path")
        bad = z.testzip()
        if bad:
            raise BuildGateError("Bad ZIP CRC: " + bad)
        prefix = f"midivolt-{meta['version']}.dist-info/"
        for name in ("METADATA", "WHEEL", "RECORD", "entry_points.txt"):
            if prefix + name not in names:
                raise BuildGateError("Missing dist-info: " + name)
        installed = Parser().parsestr(z.read(prefix + "METADATA").decode("utf-8"))
        if installed.get("Name") != "midivolt" or installed.get("Version") != meta["version"]:
            raise BuildGateError("Incorrect installed name/version")
        if set(x.strip() for x in installed.get("Requires-Python", "").split(",")) != set(x.strip() for x in meta["requires-python"].split(",")):
            raise BuildGateError("Incorrect Python requirement")
        # An actual distributable RC must carry original license and all
        # third-party attributions. PEP 639 metadata is part of the contract.
        required_licenses = ("LICENSE", "THIRD_PARTY_NOTICES.md")
        if meta.get("license") != "Apache-2.0" or set(meta.get("license-files", [])) != set(required_licenses):
            raise BuildGateError("Incorrect license configuration")
        if installed.get("License-Expression") != "Apache-2.0" or set(installed.get_all("License-File", [])) != set(required_licenses):
            raise BuildGateError("Missing/incorrect PEP 639 license metadata")
        for license_name in required_licenses:
            member = prefix + "licenses/" + license_name
            if member not in names:
                raise BuildGateError("Missing packaged license: " + license_name)
            if z.read(member) != (source / license_name).read_bytes():
                raise BuildGateError("Incorrect packaged license bytes: " + license_name)
        from configparser import ConfigParser
        cp = ConfigParser(interpolation=None)
        cp.optionxform = str
        cp.read_string(z.read(prefix + "entry_points.txt").decode("utf-8"))
        if not cp.has_section("console_scripts") or dict(cp.items("console_scripts")) != scripts:
            raise BuildGateError("Console-script list mismatch")
        tree = source / "src/midivolt"
        sources = sorted(tree.rglob("*.py"))
        if len(sources) != 36:
            raise BuildGateError("Expected 36 production Python source files")
        for p in sources:
            rel = "midivolt/" + p.relative_to(tree).as_posix()
            if rel not in names or p.read_bytes() != z.read(rel):
                raise BuildGateError("Missing or modified source: " + rel)
        record = list(csv.reader(StringIO(z.read(prefix + "RECORD").decode("utf-8"))))
        if len(record) != len(names) or len({row[0] for row in record if len(row) == 3}) != len(names):
            raise BuildGateError("RECORD count mismatch")
        for row in record:
            if len(row) != 3:
                raise BuildGateError("Malformed RECORD")
            name, digest, length = row
            if name not in names:
                raise BuildGateError("RECORD path not in wheel")
            if name == prefix + "RECORD":
                if digest or length:
                    raise BuildGateError("Invalid RECORD self-entry")
                continue
            binary = z.read(name)
            calculated = base64.urlsafe_b64encode(sha256(binary).digest()).decode("ascii").rstrip("=")
            if digest != "sha256=" + calculated or length != str(len(binary)):
                raise BuildGateError("RECORD checksum/size mismatch: " + name)
    return {"source_modules": len(sources), "cli_entries": len(scripts), "zip_files": len(names)}


def build_verified(root: Path, output_dir: Path, *, diagnostic: bool = False,
                   expected_source_commit: str = EXPECTED_SOURCE_COMMIT) -> dict:
    """Validate before writing, then build+check in an isolated temporary dir."""
    result = {"status": "BLOCKED", "supported_python": sys.version_info[:2] == (3, 11),
              "python": sys.version.split()[0], "built": False, "errors": []}
    if not result["supported_python"] and not diagnostic:
        result["errors"].append("PYTHON_3_11_REQUIRED")
        return result
    if not re.fullmatch(r"[0-9a-f]{40}", expected_source_commit):
        result["errors"].append("INVALID_EXPECTED_SOURCE_COMMIT")
        return result
    if not output_dir.is_dir() or output_dir.is_symlink():
        result["errors"].append("OUTPUT_DIRECTORY_REQUIRED")
        return result
    try:
        manifest, sourcefiles = load_snapshot(root)
        if manifest.get("source_commit") != expected_source_commit:
            raise BuildGateError("SOURCE_COMMIT_MISMATCH")
        with tempfile.TemporaryDirectory(prefix="midivolt-rebuilt-") as tmp:
            src = Path(tmp) / "srcdir"
            src.mkdir()
            for name, data in sourcefiles:
                dest = src.joinpath(*PurePosixPath(name).parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            built_dir = Path(tmp) / "dist"
            built_dir.mkdir()
            command = [sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps",
                       "--no-build-isolation", "--wheel-dir", str(built_dir)]
            if not result["supported_python"]:
                command.append("--ignore-requires-python")
            command.append(str(src))
            env = os.environ.copy()
            env.update({"PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1", "PIP_NO_INPUT": "1",
                        "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
            proc = subprocess.run(command, capture_output=True, text=True, env=env, timeout=120)
            if proc.returncode:
                raise BuildGateError("SETUPTOOLS_BUILD_FAILED:" + proc.stderr[-600:])
            products = list(built_dir.glob("*.whl"))
            if len(products) != 1:
                raise BuildGateError("Expected exactly one Wheel")
            wheel = products[0]
            checks = check_wheel(wheel, src)
            dest = output_dir / wheel.name
            if dest.exists() or dest.is_symlink():
                raise BuildGateError("OUTPUT_EXISTS_REFUSE_OVERWRITE")
            # O_EXCL prevents accidental replacement of an existing file.
            with dest.open("xb") as f:
                f.write(wheel.read_bytes())
            result.update(status="PASS_SUPPORTED_PYTHON311_WHEEL_BUILD" if result["supported_python"] else "PASS_DIAGNOSTIC_WHEEL_BUILD",
                          built=True, wheel=str(dest), sha256=sha256(dest.read_bytes()).hexdigest(),
                          snapshot_commit=manifest["source_commit"], **checks)
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired, KeyError, tomllib.TOMLDecodeError) as exc:
        result["errors"].append(str(exc))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-source-commit", default=EXPECTED_SOURCE_COMMIT,
                        help="immutable 40-hex source commit used to create the snapshot")
    parser.add_argument("--diagnostic-unsupported-python", action="store_true")
    args = parser.parse_args(argv)
    outcome = build_verified(args.snapshot_root, args.output_dir,
                             diagnostic=args.diagnostic_unsupported_python,
                             expected_source_commit=args.expected_source_commit)
    print(json.dumps(outcome, sort_keys=True))
    return 0 if not outcome["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
