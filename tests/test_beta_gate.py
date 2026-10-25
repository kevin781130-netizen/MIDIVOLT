"""K10 synthetic distribution-integrity tests (no model, pip install or Cubase)."""
from __future__ import annotations

from hashlib import sha256
import base64
import csv
import io
from pathlib import Path
import json
import tomllib
import zipfile

import pytest

from midivolt.beta_gate import (
    REQUIRED_CLI, REQUIRED_TARGETS, inspect_beta_package, inspect_wheel, inspect_windows_zip,
)
from midivolt.beta_gate_cli import main


def synthetic_wheel(tmp_path, *, omit=None, extra=None, entry_override=None):
    path = tmp_path / "midivolt-0.1.0rc1-py3-none-any.whl"
    root = "midivolt-0.1.0rc1.dist-info"
    scripts = dict(REQUIRED_TARGETS)
    if entry_override is not None:
        scripts.update(entry_override)
    modules = {
        value.split(":")[0].replace(".", "/") + ".py": b"def main(): return 0\n"
        for value in scripts.values()
    }
    entries = "".join(f"{name} = {target}\n" for name, target in sorted(scripts.items()))
    files = {
        root + "/METADATA": b"Metadata-Version: 2.4\nName: midivolt\nVersion: 0.1.0rc1\nRequires-Python: >=3.11,<3.12\n",
        root + "/WHEEL": b"Wheel-Version: 1.0\nGenerator: setuptools\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        root + "/licenses/LICENSE": b"Apache License\nVersion 2.0\n",
        root + "/licenses/THIRD_PARTY_NOTICES.md": b"# Third-party software and rights register\n",
        root + "/entry_points.txt": ("[console_scripts]\n" + entries).encode(),
        **modules,
    }
    files.pop(omit, None)
    if extra is not None:
        files.update(extra)
    record_name = root + "/RECORD"
    if omit != record_name:
        lines = []
        for name, payload in files.items():
            digest = base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b"=").decode("ascii")
            lines.append((name, "sha256=" + digest, str(len(payload))))
        lines.append((record_name, "", ""))
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerows(lines)
        files[record_name] = output.getvalue().encode("utf-8")
    with zipfile.ZipFile(path, "w") as z:
        for name, payload in files.items():
            z.writestr(name, payload)
    return path


def synthetic_windows_zip(tmp_path, wheel, *, missing=None, tamper=False):
    target = tmp_path / "MIDIVOLT-Windows-0.1.0rc1-py311.zip"
    assets = {
        "Install-MIDIVOLT.ps1": b"# Installer",
        "Smoke-MIDIVOLT.ps1": b"# Smoke",
        "README-Windows.txt": b"Developer RC only.",
        "LICENSE": b"Apache License\nVersion 2.0",
        "THIRD_PARTY_NOTICES.md": b"# Third-party notices",
        wheel.name: (b"wrong wheel" if tamper else wheel.read_bytes()),
    }
    assets.pop(missing, None)
    with zipfile.ZipFile(target, "w") as z:
        for name, data in assets.items():
            z.writestr(name, data)
    return target, sha256(target.read_bytes()).hexdigest()


def test_valid_wheel_checks_cli_legal_and_pure_python(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    data = inspect_wheel(wheel)
    assert data["version"] == "0.1.0rc1"
    assert data["legal_notices_packaged"]
    assert REQUIRED_CLI.issubset(data["cli_entrypoints"])
    assert data["package_contents_verified"]
    assert not data["wheel_installed_in_clean_environment"]


def test_valid_windows_zip_includes_identical_wheel_and_license(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    zipped, digest = synthetic_windows_zip(tmp_path, wheel)
    data = inspect_windows_zip(zipped, wheel=wheel, expected_sha256=digest)
    assert data["zip_sha256_matches_supplied_trusted_value"]
    assert data["wheel_payload_matches_separate_wheel"]
    assert data["actual_powershell_install_verified"] is False
    report = inspect_beta_package(wheel, windows_zip=zipped, zip_sha256=digest)
    assert report["developer_package_content_verified"] is True
    assert report["commercial_beta_release_ready"] is False
    assert report["developer_rc_install_verified"] is False
    assert "clean workstation install" in " ".join(report["commercial_beta_blockers"]).lower()


@pytest.mark.parametrize("omission", [
    "midivolt-0.1.0rc1.dist-info/licenses/LICENSE",
    "midivolt-0.1.0rc1.dist-info/licenses/THIRD_PARTY_NOTICES.md",
    "midivolt-0.1.0rc1.dist-info/entry_points.txt",
])
def test_missing_wheel_notices_or_entrypoints_fail(tmp_path, omission):
    with pytest.raises(ValueError, match="missing required|Wheel must include"):
        inspect_wheel(synthetic_wheel(tmp_path, omit=omission))


def test_rejects_missing_mapped_cli_module(tmp_path):
    wheel = synthetic_wheel(tmp_path, omit="midivolt/beta_gate_cli.py")
    with pytest.raises(ValueError, match="missing packaged module"):
        inspect_wheel(wheel)


def test_rejects_dangerous_external_model_pickle_and_weights(tmp_path):
    wheel = synthetic_wheel(tmp_path, extra={"midivolt/data/vocab_remi.pkl": b"pickle"})
    with pytest.raises(ValueError, match="embeds"):
        inspect_wheel(wheel)


def test_rejects_zip_slip_or_duplicate_zip_members(tmp_path):
    p = synthetic_wheel(tmp_path, extra={"../checkpoint.txt": b"invalid"})
    with pytest.raises(ValueError, match="Unsafe path"):
        inspect_wheel(p)
    p = synthetic_wheel(tmp_path)
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(p, "a") as z:
            z.writestr("midivolt/cli.py", b"duplicate", compress_type=zipfile.ZIP_DEFLATED)
    with pytest.raises(ValueError, match="Duplicate archive"):
        inspect_wheel(p)


def test_rejects_external_or_malformed_entrypoint(tmp_path):
    p = synthetic_wheel(tmp_path, entry_override={"midivolt-compose": "external_service:main"})
    with pytest.raises(ValueError, match="unexpected entry point target"):
        inspect_wheel(p)


def test_missing_windows_notice_or_fake_wheel_payload_fails(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    p, digest = synthetic_windows_zip(tmp_path, wheel, missing="LICENSE")
    with pytest.raises(ValueError, match="ZIP missing"):
        inspect_windows_zip(p, wheel=wheel, expected_sha256=digest)
    p, digest = synthetic_windows_zip(tmp_path, wheel, tamper=True)
    with pytest.raises(ValueError, match="differs"):
        inspect_windows_zip(p, wheel=wheel, expected_sha256=digest)


def test_wrong_windows_zip_checksum_is_rejected(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    p, digest = synthetic_windows_zip(tmp_path, wheel)
    with pytest.raises(ValueError, match="checksum mismatch"):
        inspect_windows_zip(p, wheel=wheel, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="both Windows ZIP"):
        inspect_beta_package(wheel, windows_zip=p)


def test_report_output_new_file_only_and_commercial_gate_stays_blocked(tmp_path, capsys):
    wheel = synthetic_wheel(tmp_path)
    report_path = tmp_path / "beta-gate.json"
    assert main(["--wheel", str(wheel), "--out", str(report_path)]) == 3
    report = json.loads(report_path.read_text())
    assert report["developer_package_content_verified"] is True
    assert report["commercial_beta_release_ready"] is False
    original = report_path.read_bytes()
    assert main(["--wheel", str(wheel), "--out", str(report_path),
                 "--developer-rc"]) == 2
    assert report_path.read_bytes() == original
    assert main(["--wheel", str(wheel), "--developer-rc"]) == 0
    assert "developer_package_content_verified" in capsys.readouterr().out


def test_invalid_wheel_cli_fails_closed(tmp_path, capsys):
    missing = tmp_path / "midivolt-0.1.0rc1-py3-none-any.whl"
    assert main(["--wheel", str(missing), "--developer-rc"]) == 2
    assert "beta gate error" in capsys.readouterr().err


def test_actual_project_manifest_declares_notices_and_gate_entrypoint():
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert set(pyproject["tool"]["setuptools"]["license-files"]) >= {
        "LICENSE", "THIRD_PARTY_NOTICES.md"
    }
    assert pyproject["project"]["scripts"]["midivolt-beta-gate"] == "midivolt.beta_gate_cli:main"
    assert (root / "THIRD_PARTY_NOTICES.md").is_file()


def test_missing_record_or_wheel_unlisted_file_fails_closed(tmp_path):
    record = "midivolt-0.1.0rc1.dist-info/RECORD"
    wheel = synthetic_wheel(tmp_path, omit=record)
    with pytest.raises(ValueError, match="missing required PEP 427 RECORD"):
        inspect_wheel(wheel)
    wheel = synthetic_wheel(tmp_path)
    # Adding a file without rewriting RECORD is not a valid wheel.
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("midivolt/unrecorded.py", b"print('injected')")
    with pytest.raises(ValueError, match="missing or unlisted"):
        inspect_wheel(wheel)


def test_wheel_record_detects_changed_source_even_if_filename_and_size_same(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    with zipfile.ZipFile(wheel, "r") as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    name = "midivolt/cli.py"
    original = members[name]
    members[name] = b"x" + original[1:]
    assert len(members[name]) == len(original)
    with zipfile.ZipFile(wheel, "w") as archive:
        for item, payload in members.items():
            archive.writestr(item, payload)
    with pytest.raises(ValueError, match="RECORD size or digest mismatch"):
        inspect_wheel(wheel)


def test_wheel_record_detects_wrong_sizes_and_duplicate_manifest_rows(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    with zipfile.ZipFile(wheel, "r") as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    name = "midivolt-0.1.0rc1.dist-info/RECORD"
    # Use a reliable first Python module size mutation rather than depending
    # on an exact line's length.
    rows = list(csv.reader(io.StringIO(files[name].decode())))
    for row in rows:
        if row[0] == "midivolt/cli.py":
            row[2] = str(int(row[2]) + 1)
            break
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    files[name] = buf.getvalue().encode()
    with zipfile.ZipFile(wheel, "w") as archive:
        for item, payload in files.items():
            archive.writestr(item, payload)
    with pytest.raises(ValueError, match="RECORD size or digest mismatch"):
        inspect_wheel(wheel)


def test_valid_wheel_reports_record_validation_and_no_signature_claim(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    report = inspect_wheel(wheel)
    assert report["wheel_record_integrity_verified"] is True
    assert report["wheel_record_entries_verified"] >= 8
    assert report["wheel_signature_or_publisher_trusted"] is False
