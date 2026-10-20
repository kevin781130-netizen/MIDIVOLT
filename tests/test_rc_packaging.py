"""Release-candidate packaging manifest and advertised command validation."""
from importlib import metadata
from pathlib import Path

import midivolt


def test_rc_version_and_direct_mido_dependency():
    distribution = metadata.distribution("midivolt")
    assert distribution.version == "0.1.0rc1"
    assert midivolt.__version__ == "0.1.0rc1"
    requirements = distribution.requires or []
    assert any(item.lower().startswith("mido") for item in requirements)


def test_all_console_entrypoints_resolve():
    dist = metadata.distribution("midivolt")
    names = {entry.name: entry for entry in dist.entry_points if entry.group == "console_scripts"}
    required = {
        "midivolt", "midivolt-cubase", "midivolt-review",
        "midivolt-hub", "midivolt-model", "midivolt-env",
        "midivolt-accept", "midivolt-bridge", "midivolt-tsov",
    }
    assert required <= set(names)
    # Loading the CLI callable must not start a model, download weights,
    # contact Hugging Face, or spawn a third-party agent.
    for key in required:
        assert callable(names[key].load())


def test_windows_rc_scripts_are_checked_in():
    repo = Path(__file__).resolve().parents[1]
    installer = (repo / "packaging/windows/Install-MIDIVOLT.ps1").read_text(encoding="utf-8")
    smoke = (repo / "packaging/windows/Smoke-MIDIVOLT.ps1").read_text(encoding="utf-8")
    workflow = (repo / ".github/workflows/windows-rc.yml").read_text(encoding="utf-8")
    assert "AllowNetwork" in installer and "Wheelhouse" in installer
    assert "already exists" in installer
    assert "WINDOWS_RC_SMOKE=PASS" in smoke
    assert "actions/upload-artifact@v4" in workflow
