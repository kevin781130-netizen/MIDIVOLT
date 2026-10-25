"""Fail-closed, stdlib-only distribution audit for MIDIVOLT developer RC.

This verifies the contents of a *built* wheel/optional Windows ZIP. It does
not install third-party dependencies, execute model weights, or claim that
Cubase/real pretrained inference/commercial rights have been approved.
"""
from __future__ import annotations

import configparser
from email.parser import Parser
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

REQUIRED_CLI = frozenset({
    "midivolt", "midivolt-review", "midivolt-compose",
    "midivolt-compose-accept", "midivolt-compose-audit",
    "midivolt-cubase", "midivolt-beta-gate",
})
REQUIRED_WINDOWS = frozenset({
    "Install-MIDIVOLT.ps1", "Smoke-MIDIVOLT.ps1",
    "README-Windows.txt", "LICENSE", "THIRD_PARTY_NOTICES.md",
})
DANGEROUS_ASSETS = (".pkl", ".pickle", ".safetensors", ".ckpt", ".pth",
                    ".pt", ".onnx", ".sf2", ".mp3", ".wav", ".flac",
                    ".bin")
SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_ARCHIVE_ENTRIES = 5000
MAX_UNCOMPRESSED = 100_000_000
MAX_MEMBER = 50_000_000


def _sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _open_safe_zip(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Archive must be a regular, existing non-symlink file.")
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Invalid archive: {path.name}") from exc
    try:
        items = archive.infolist()
        if not items or len(items) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("Archive is empty or contains excessive entries.")
        if sum(i.file_size for i in items) > MAX_UNCOMPRESSED:
            raise ValueError("Archive uncompressed size exceeds distribution limit.")
        names = []
        for info in items:
            name = info.filename
            parts = PurePosixPath(name).parts
            if (not name or "\\" in name or name.startswith("/") or
                    any(part in ("", ".", "..") for part in parts) or
                    ":" in parts[0] or info.file_size > MAX_MEMBER):
                raise ValueError("Unsafe path or oversized archive member.")
            if info.create_system == 3 and stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Archive may not contain symbolic links.")
            if not info.is_dir():
                names.append(name)
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive member names.")
        if any(name.casefold().endswith(DANGEROUS_ASSETS) for name in names):
            raise ValueError("Distribution unexpectedly embeds a model, media, or pickle asset.")
        return archive, set(names)
    except BaseException:
        archive.close()
        raise


def inspect_wheel(wheel: str | Path) -> dict:
    """Check metadata, legal notices and ALL actual CLI modules inside a wheel."""
    path = Path(wheel).expanduser()
    if not path.name.endswith(".whl") or not path.name.lower().startswith("midivolt-"):
        raise ValueError("Supply a MIDIVOLT .whl wheel.")
    with _open_safe_zip(path)[0] as archive:
        names = {item.filename for item in archive.infolist() if not item.is_dir()}
        roots = {
            name.split("/", 1)[0] for name in names
            if name.endswith(".dist-info/METADATA") and "/" in name
        }
        if len(roots) != 1:
            raise ValueError("Expected exactly one wheel .dist-info/METADATA.")
        root = next(iter(roots))
        if not root.startswith("midivolt-"):
            raise ValueError("Wrong package metadata directory.")
        def asset(suffix):
            full = root + "/" + suffix
            if full not in names:
                raise ValueError(f"Wheel missing required {suffix}.")
            return archive.read(full)
        metadata = Parser().parsestr(asset("METADATA").decode("utf-8"))
        if metadata.get("Name", "").lower().replace("_", "-") != "midivolt":
            raise ValueError("Wheel contains incorrect package name.")
        version = metadata.get("Version")
        if not version or not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]*", version):
            raise ValueError("Wheel lacks a valid version.")
        if f"midivolt-{version}-" not in path.name:
            raise ValueError("Filename version disagrees with wheel metadata.")
        requires_python = metadata.get("Requires-Python", "")
        if "3.11" not in requires_python:
            raise ValueError("Wheel is missing supported Python 3.11 metadata.")
        wheel_meta = asset("WHEEL").decode("utf-8")
        if "Tag: py3-none-any" not in wheel_meta:
            raise ValueError("Beta developer wheel must be pure Python py3-none-any.")
        license_paths = {name[len(root)+1:] for name in names if name.startswith(root + "/licenses/")}
        if "licenses/LICENSE" not in license_paths or "licenses/THIRD_PARTY_NOTICES.md" not in license_paths:
            raise ValueError("Wheel must include Apache LICENSE and THIRD_PARTY_NOTICES.md.")
        license_bytes = asset("licenses/LICENSE")
        notices = asset("licenses/THIRD_PARTY_NOTICES.md")
        if b"Apache License" not in license_bytes or b"Third-party" not in notices:
            raise ValueError("License notice contents missing or inconsistent.")
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read_string(asset("entry_points.txt").decode("utf-8"))
        if "console_scripts" not in parser:
            raise ValueError("Wheel missing console_scripts.")
        scripts = dict(parser["console_scripts"])
        if not REQUIRED_CLI.issubset(scripts):
            raise ValueError("Wheel missing required CLI: " + ", ".join(sorted(REQUIRED_CLI-set(scripts))))
        for command, target in scripts.items():
            match = re.fullmatch(r"(midivolt(?:\.[A-Za-z_][\w]*)*):([A-Za-z_]\w*)", target.strip())
            if not match:
                raise ValueError(f"Unsafe or unsupported CLI entry point {command!r}.")
            module_path = match.group(1).replace(".", "/")
            if module_path + ".py" not in names and module_path + "/__init__.py" not in names:
                raise ValueError(f"CLI {command} points to missing packaged module.")
        files = sum(name.startswith("midivolt/") for name in names)
        return {
            "package": "midivolt", "version": version, "wheel": str(path.resolve()),
            "wheel_sha256": _sha(path), "python_requirement": requires_python,
            "cli_entrypoints": sorted(scripts),
            "packaged_python_files": files, "legal_notices_packaged": True,
            "external_model_assets_embedded": False, "package_contents_verified": True,
            "wheel_installed_in_clean_environment": False,
        }


def inspect_windows_zip(archive_file: str | Path, *, wheel: Path,
                        expected_sha256: str) -> dict:
    if not isinstance(expected_sha256, str) or not SHA.fullmatch(expected_sha256):
        raise ValueError("Provide independently sourced 64-char lowercase Windows ZIP SHA-256.")
    path = Path(archive_file).expanduser()
    if path.suffix.lower() != ".zip":
        raise ValueError("Windows distribution must be .zip.")
    digest = _sha(path)
    if digest != expected_sha256:
        raise ValueError("Windows ZIP checksum mismatch.")
    archive, names = _open_safe_zip(path)
    with archive:
        missing = REQUIRED_WINDOWS - names
        if missing:
            raise ValueError("Windows ZIP missing: " + ", ".join(sorted(missing)))
        included_wheels = [name for name in names if name.endswith(".whl")]
        if included_wheels != [wheel.name]:
            raise ValueError("Windows ZIP must include exactly the inspected MIDIVOLT wheel.")
        included = archive.read(wheel.name)
        if sha256(included).hexdigest() != _sha(wheel):
            raise ValueError("Windows ZIP wheel differs from audited wheel.")
        if b"Apache License" not in archive.read("LICENSE") or b"Third-party" not in archive.read("THIRD_PARTY_NOTICES.md"):
            raise ValueError("Windows ZIP missing valid license notice text.")
        return {
            "windows_zip": str(path.resolve()), "windows_zip_sha256": digest,
            "zip_sha256_matches_supplied_trusted_value": True,
            "wheel_payload_matches_separate_wheel": True,
            "windows_install_scripts_packaged": True,
            "actual_powershell_install_verified": False,
        }


def inspect_beta_package(
    wheel: str | Path, *, windows_zip: str | Path | None = None,
    zip_sha256: str | None = None,
    output_path: str | Path | None = None,
) -> dict:
    """No code execution or online access. Never claim commercial beta ready."""
    artifact = Path(wheel).expanduser()
    w = inspect_wheel(artifact)
    if (windows_zip is None) != (zip_sha256 is None):
        raise ValueError("Specify both Windows ZIP and independently checked SHA-256.")
    windows = (inspect_windows_zip(windows_zip, wheel=artifact,
               expected_sha256=zip_sha256) if windows_zip is not None else None)
    blockers = [
        "Real Text2midi pretrained checkpoint inference not independently verified.",
        "Cubase GUI import/export and musical playback not independently verified.",
        "Independent human listening and arrangement accuracy not verified.",
        "Model training-data/composition copyright and commercial rights not cleared.",
        "Clean workstation install, supply-chain review and security sign-off not verified by artifact inspection.",
    ]
    if windows is None:
        blockers.append("Windows installer ZIP and its independently checked digest not provided.")
    report = {
        "schema_version": 1, "type": "midivolt_k10_release_package_audit",
        "package": w, "windows": windows,
        "developer_package_content_verified": True,
        "developer_rc_install_verified": False,
        "commercial_beta_release_ready": False,
        "commercial_beta_blockers": blockers,
        "scope": "read_only_archives_not_executed",
    }
    if output_path is not None:
        out = Path(output_path).expanduser().resolve()
        if out.suffix.lower() != ".json" or not out.parent.is_dir():
            raise ValueError("Report output must be a .json in an existing directory.")
        reserved = [artifact.resolve()]
        if windows_zip is not None:
            reserved.append(Path(windows_zip).expanduser().resolve())
        if out in reserved or out.is_symlink() or out.exists():
            raise FileExistsError("Release gate report must use a fresh distinct path.")
        fd, tmp = tempfile.mkstemp(prefix="." + out.name + ".", suffix=".tmp", dir=out.parent)
        os.close(fd)
        try:
            Path(tmp).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            os.link(tmp, out)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return report
