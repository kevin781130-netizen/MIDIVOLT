"""Check an actual MIDIVOLT wheel before Windows RC distribution.

Offline, standard-library only. Inspects the *built wheel*, not just source.
Does not certify installation, Python 3.11, Windows, or Cubase behavior.
"""
from __future__ import annotations

import argparse
import ast
import base64
import configparser
import csv
from email.parser import Parser
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tomllib
from zipfile import BadZipFile, ZipFile

MAX_FILE_COUNT = 2000
MAX_UNCOMPRESSED = 128 * 1024 * 1024


def inspect_wheel(wheel_path: Path, project_path: Path) -> dict:
    errors: list[str] = []

    def reject(message: str) -> None:
        if message not in errors:
            errors.append(message)

    try:
        project = tomllib.loads(project_path.read_text(encoding="utf-8"))["project"]
        expected_version = str(project["version"])
        scripts = project["scripts"]
        expected_python = project["requires-python"]
        if project["name"] != "midivolt" or len(scripts) < 13:
            raise ValueError("Unexpected MIDIVOLT project metadata")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        return {"status": "BLOCKED_PROJECT_METADATA", "errors": [str(exc)]}

    try:
        with ZipFile(wheel_path) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(names) > MAX_FILE_COUNT or sum(x.file_size for x in infos) > MAX_UNCOMPRESSED:
                reject("ARCHIVE_LIMIT_EXCEEDED")
                # Do not decompress an oversized untrusted wheel merely to check it.
                return {"status": "FAIL_WHEEL_INTEGRITY", "wheel": str(wheel_path),
                        "scripts_expected": len(scripts), "python_runtime_certified": False,
                        "windows_certified": False, "errors": errors}
            if len(names) != len(set(names)):
                reject("DUPLICATE_ARCHIVE_ENTRY")
            for info in infos:
                p = PurePosixPath(info.filename)
                if (p.is_absolute() or ".." in p.parts or "\\" in info.filename
                        or not p.parts or info.filename.startswith("./")):
                    reject("UNSAFE_ARCHIVE_PATH")
                # Reject Unix symlink members (Windows ZIP extraction is inconsistent).
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    reject("SYMLINK_ARCHIVE_ENTRY")
            if any(i.is_dir() for i in infos):
                # Ordinary packaging wheels may contain directories, but must
                # not hide unexpected contents inside directory entries.
                pass
            corrupted = archive.testzip()
            if corrupted is not None:
                reject("CORRUPT_ARCHIVE_CRC:" + corrupted)

            root = "midivolt-" + expected_version + ".dist-info/"
            if not all(root + x in names for x in ("METADATA", "WHEEL", "RECORD", "entry_points.txt")):
                reject("MISSING_DIST_INFO")
            if not wheel_path.name.startswith("midivolt-" + expected_version + "-") or not wheel_path.name.endswith(".whl"):
                reject("WHEEL_FILENAME_VERSION_MISMATCH")
            if "MISSING_DIST_INFO" not in errors:
                metadata = Parser().parsestr(archive.read(root + "METADATA").decode("utf-8"))
                if metadata.get("Name", "").lower().replace("_", "-") != "midivolt":
                    reject("PACKAGE_NAME_MISMATCH")
                if metadata.get("Version") != expected_version:
                    reject("PACKAGE_VERSION_MISMATCH")
                actual_python = metadata.get("Requires-Python", "")
                if {x.strip() for x in actual_python.split(",")} != {x.strip() for x in expected_python.split(",")}:
                    reject("PYTHON_RUNTIME_MISMATCH")
                # Keep the independent installer gate aligned with the
                # builder: Apache-2.0 and complete third-party attribution
                # must actually be present in the wheel, not just pyproject.
                required_licenses = ("LICENSE", "THIRD_PARTY_NOTICES.md")
                if (project.get("license") != "Apache-2.0"
                        or set(project.get("license-files", [])) != set(required_licenses)):
                    reject("PROJECT_LICENSE_CONTRACT_MISMATCH")
                if (metadata.get("License-Expression") != "Apache-2.0"
                        or set(metadata.get_all("License-File", [])) != set(required_licenses)):
                    reject("WHEEL_LICENSE_METADATA_MISMATCH")
                for license_name in required_licenses:
                    member = root + "licenses/" + license_name
                    if member not in names:
                        reject("MISSING_PACKAGED_LICENSE:" + license_name)
                        continue
                    original = project_path.resolve().parent / license_name
                    if not original.is_file() or original.is_symlink():
                        reject("MISSING_SOURCE_LICENSE:" + license_name)
                    elif sha256(original.read_bytes()).digest() != sha256(archive.read(member)).digest():
                        reject("PACKAGED_LICENSE_SOURCE_MISMATCH:" + license_name)
                wheel_meta = Parser().parsestr(archive.read(root + "WHEEL").decode("utf-8"))
                if wheel_meta.get("Root-Is-Purelib", "").lower() != "true":
                    reject("NOT_PURE_PYTHON_WHEEL")
                if "py3-none-any" not in wheel_meta.get_all("Tag", []):
                    reject("WHEEL_TAG_MISMATCH")

                config = configparser.ConfigParser(interpolation=None)
                config.optionxform = str
                config.read_string(archive.read(root + "entry_points.txt").decode("utf-8"))
                actual_scripts = dict(config.items("console_scripts")) if config.has_section("console_scripts") else {}
                if actual_scripts != scripts:
                    reject("ENTRYPOINTS_MISMATCH")
                for command, target in scripts.items():
                    if not re.fullmatch(r"midivolt(?:\.[a-zA-Z_]\w*)+:[a-zA-Z_]\w*", target):
                        reject("INVALID_ENTRYPOINT:" + command)
                        continue
                    mod, symbol = target.split(":")
                    file = mod.replace(".", "/") + ".py"
                    if file not in names:
                        reject("MISSING_ENTRYPOINT_MODULE:" + command)
                        continue
                    try:
                        tree = ast.parse(archive.read(file), filename=file)
                    except (ValueError, SyntaxError, UnicodeError):
                        reject("ENTRYPOINT_SYNTAX_INVALID:" + command)
                        continue
                    if not any(isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == symbol for x in tree.body):
                        reject("MISSING_ENTRYPOINT_FUNCTION:" + command)

                records = list(csv.reader(StringIO(archive.read(root + "RECORD").decode("utf-8"))))
                record_names: set[str] = set()
                for row in records:
                    if len(row) != 3 or row[0] in record_names:
                        reject("INVALID_RECORD_ROW")
                        continue
                    name, digest, size = row
                    record_names.add(name)
                    if name not in names:
                        reject("RECORD_REFERENCES_MISSING_FILE")
                        continue
                    if name == root + "RECORD":
                        if digest or size:
                            reject("RECORD_SELF_DIGEST_NOT_EMPTY")
                        continue
                    try:
                        contents = archive.read(name)
                        algorithm, encoded = digest.split("=", 1)
                        if algorithm != "sha256":
                            raise ValueError("unsupported digest")
                        actual = base64.urlsafe_b64encode(sha256(contents).digest()).decode("ascii").rstrip("=")
                        if encoded != actual or int(size) != len(contents):
                            reject("RECORD_DIGEST_OR_SIZE_MISMATCH:" + name)
                    except (ValueError, TypeError):
                        reject("RECORD_DIGEST_INVALID:" + name)
                if set(names) != record_names:
                    reject("RECORD_ARCHIVE_FILESET_MISMATCH")
                if len(records) < len(scripts) + 4:
                    reject("WHEEL_INCOMPLETE")

                # A build from the working tree must carry every Python module
                # byte-for-byte, not merely the 13 advertised CLI entrypoints.
                source_root = project_path.resolve().parent / "src/midivolt"
                if not source_root.is_dir():
                    reject("MISSING_PACKAGE_SOURCE_TREE")
                else:
                    for module in sorted(source_root.rglob("*.py")):
                        if module.is_symlink() or not module.resolve().is_relative_to(source_root.resolve()):
                            reject("UNSAFE_SOURCE_MODULE")
                            continue
                        archive_name = "midivolt/" + module.relative_to(source_root).as_posix()
                        if archive_name not in names:
                            reject("MISSING_PACKAGED_SOURCE:" + archive_name)
                        elif sha256(module.read_bytes()).digest() != sha256(archive.read(archive_name)).digest():
                            reject("PACKAGED_SOURCE_MISMATCH:" + archive_name)
    except (BadZipFile, OSError, ValueError, UnicodeError, configparser.Error) as exc:
        reject("INVALID_WHEEL:" + type(exc).__name__)
    return {"status": "PASS_WHEEL_INTEGRITY_NOT_INSTALLATION" if not errors else "FAIL_WHEEL_INTEGRITY",
            "wheel": str(wheel_path), "scripts_expected": len(scripts),
            "python_runtime_certified": False, "windows_certified": False,
            "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1] / "pyproject.toml")
    args = parser.parse_args(argv)
    result = inspect_wheel(args.wheel, args.project)
    print(json.dumps(result, sort_keys=True))
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    sys.exit(main())
