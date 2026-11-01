"""Runtime matrix tests: modern core MIDI vs legacy Basic Pitch audio extra."""
from __future__ import annotations

import builtins
from pathlib import Path
import tomllib

import pytest
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

from midivolt.audio import transcribe_audio
from midivolt.transcribe import basic_pitch_backend


ROOT = Path(__file__).resolve().parents[1]


def _requirements(extra: str) -> list[Requirement]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    return [Requirement(value) for value in project["optional-dependencies"][extra]]


def _matches(requirement: Requirement, python_version: str) -> bool:
    environment = default_environment()
    environment["python_version"] = python_version
    environment["python_full_version"] = python_version + ".0"
    return requirement.marker is None or requirement.marker.evaluate(environment)


def test_core_runtime_accepts_python_311_through_313_only():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    supported = SpecifierSet(project["requires-python"])
    assert "3.11.9" in supported
    assert "3.12.8" in supported
    assert "3.13.5" in supported
    assert "3.14.0" not in supported
    assert "music21>=9.7.1,<10" in project["dependencies"]


@pytest.mark.parametrize("extra", ["audio", "dev"])
def test_numpy_constraint_selects_python_compatible_major(extra: str):
    requirements = _requirements(extra)
    numpy = [r for r in requirements if r.name.lower() == "numpy"]
    assert len(numpy) == 2
    for version in ("3.11",):
        selected = [r for r in numpy if _matches(r, version)]
        assert len(selected) == 1
        assert selected[0].specifier == ">=1.23.5,<2"
    for version in ("3.12", "3.13"):
        selected = [r for r in numpy if _matches(r, version)]
        assert len(selected) == 1
        assert selected[0].specifier == ">=2.0,<3"


def test_basic_pitch_is_only_selected_for_python_311():
    basic_pitch = next(r for r in _requirements("audio") if r.name == "basic-pitch")
    assert _matches(basic_pitch, "3.11")
    assert not _matches(basic_pitch, "3.12")
    assert not _matches(basic_pitch, "3.13")


@pytest.mark.parametrize("backend", ["single", "batch"])
def test_missing_basic_pitch_fails_with_python311_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
):
    original_import = builtins.__import__

    def reject_basic_pitch(name, *args, **kwargs):
        if name == "basic_pitch" or name.startswith("basic_pitch."):
            raise ModuleNotFoundError("No module named 'basic_pitch'", name="basic_pitch")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_basic_pitch)
    if backend == "single":
        source = tmp_path / "input.wav"
        source.write_bytes(b"test fixture")
        output = tmp_path / "output.mid"
        with pytest.raises(RuntimeError, match="Python 3.11"):
            transcribe_audio(source, output)
        assert not output.exists()
    else:
        with pytest.raises(RuntimeError, match="Python 3.11"):
            basic_pitch_backend()
