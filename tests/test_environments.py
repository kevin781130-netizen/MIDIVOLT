"""Cross-platform acceptance of real venv lifecycle, without pretrained weights."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pretty_midi
import pytest

from midivolt.environments import (
    EnvironmentError, MARKER, create_environment,
    install_requirements, plan_environment, verify_environment,
    venv_python,
)
from midivolt.environment_cli import main as env_main
from midivolt.acceptance import acceptance_run
from midivolt.io import write_midi, read_midi
from midivolt.review_engine import create_proposal, check_proposal

def _git(root, *argv):
    return subprocess.run(["git", "-C", str(root), *argv], check=True,
                          capture_output=True, text=True).stdout.strip()

def checkout(tmp_path, name="text2midi"):
    root = tmp_path / "upstream"
    root.mkdir()
    if name == "text2midi":
        path = root / "model" / "transformer_model.py"
    else:
        path = root / "anticipation" / "sample.py"
    path.parent.mkdir()
    path.write_text("# local pinned upstream source\n")
    (root / "requirements.txt").write_text("# intentionally empty for offline test\n")
    _git(root, "init")
    _git(root, "add", ".")
    _git(root, "-c", "user.name=MIDIVOLT Test", "-c",
         "user.email=tests@example.invalid", "commit", "-m", "pin source")
    return root, _git(root, "rev-parse", "HEAD")

def spec(tmp_path):
    root, sha = checkout(tmp_path)
    env = tmp_path / "model_env"
    return plan_environment(
        "text2midi", checkout=root, expected_commit=sha,
        base_python=sys.executable, destination=env)

def test_plan_is_read_only_and_checkout_pinned(tmp_path):
    model = spec(tmp_path)
    assert len(model.expected_commit) == 40
    assert model.python_version.startswith("3.11.")
    assert model.requirements_sha256
    assert not model.destination.exists()
    with pytest.raises(PermissionError, match="confirm"):
        create_environment(model)
    assert not model.destination.exists()

def test_commit_drift_and_tracked_modifications_rejected(tmp_path):
    model = spec(tmp_path)
    with pytest.raises(EnvironmentError, match="drift"):
        plan_environment(
            "text2midi", checkout=model.checkout, expected_commit="f"*40,
            base_python=sys.executable, destination=model.destination)
    (model.checkout / "requirements.txt").write_text("# tampered\n")
    with pytest.raises(EnvironmentError, match="modified"):
        create_environment(model, confirm=True)
    assert not model.destination.exists()

def test_nonempty_and_internal_target_rejected(tmp_path):
    model = spec(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        plan_environment(
            "text2midi", checkout=model.checkout,
            expected_commit=model.expected_commit, base_python=sys.executable,
            destination=model.checkout / "env")
    model.destination.mkdir()
    with pytest.raises(FileExistsError):
        plan_environment(
            "text2midi", checkout=model.checkout,
            expected_commit=model.expected_commit, base_python=sys.executable,
            destination=model.destination)

def test_cli_requires_confirmation_before_creating(tmp_path, capsys):
    model = spec(tmp_path)
    args = ["create", "text2midi", "--checkout", str(model.checkout),
            "--revision", model.expected_commit,
            "--base-python", sys.executable, "--env", str(model.destination)]
    assert env_main(args) == 2
    assert "--confirm-create" in capsys.readouterr().err
    assert not model.destination.exists()

def test_real_offline_venv_and_pip_install(tmp_path):
    """Actually runs system python -m venv and empty requirements pip install."""
    plan = spec(tmp_path)
    created = create_environment(plan, confirm=True)
    assert created["installed"] is False
    assert (plan.destination / MARKER).is_file()
    assert venv_python(plan.destination).is_file()
    status = verify_environment(plan.destination)
    assert status["source_and_requirements_verified"]
    assert status["real_inference_verified"] is False
    assert status["model_import_verified"] is False
    with pytest.raises(PermissionError):
        install_requirements(plan.destination, allow_network=True)
    with pytest.raises(ValueError, match="exactly one"):
        install_requirements(plan.destination, confirm=True)
    offline_wheels = tmp_path / "wheels"
    offline_wheels.mkdir()
    installed = install_requirements(
        plan.destination, confirm=True, wheelhouse=offline_wheels, timeout=180)
    assert installed["installed"] is True
    assert installed["installed_network_used"] is False
    assert installed["freeze"] is not None
    with pytest.raises(EnvironmentError, match="already installed"):
        install_requirements(
            plan.destination, confirm=True, wheelhouse=offline_wheels, timeout=180)
    assert not (tmp_path / "venv_other").exists()

def test_verify_does_not_import_model_code(tmp_path):
    model = spec(tmp_path)
    create_environment(model, confirm=True)
    # even if supplied model source would raise, default verification is safe
    (model.checkout / "model" / "transformer_model.py").write_text(
        "raise RuntimeError('must not import')\n")
    with pytest.raises(EnvironmentError, match="modified"):
        verify_environment(model.destination)

def _melody(tmp_path):
    source = tmp_path / "original.mid"
    midi = pretty_midi.PrettyMIDI(initial_tempo=70)
    lead = pretty_midi.Instrument(program=73, name="Locked flute")
    lead.notes.append(pretty_midi.Note(80, 65, 0, 0.6))
    midi.instruments.append(lead)
    write_midi(midi, source)
    return source

def test_acceptance_requires_consent_before_any_io(tmp_path):
    with pytest.raises(PermissionError, match="confirm-inference"):
        acceptance_run(
            model="text2midi", environment="missing", checkout="missing",
            checkpoint="missing", source="missing",
            out=tmp_path/"candidate.mid", manifest=tmp_path/"plan.json",
            report=tmp_path/"report.json", locked_tracks=[0])

def test_acceptance_records_locked_diff_after_success(tmp_path, monkeypatch):
    source = _melody(tmp_path)
    man, can, rep = (tmp_path/"plan.json", tmp_path/"candidate.mid",
                     tmp_path/"accept.json")
    fake_env = tmp_path / "fakeenv"
    fake_env.mkdir()
    root = tmp_path/"upstream"
    root.mkdir()
    monkeypatch.setattr(
        "midivolt.acceptance._read_managed_environment",
        lambda _: {"model":"text2midi", "installed":True,
                   "checkout":str(root)})
    monkeypatch.setattr(
        "midivolt.acceptance.verify_environment",
        lambda env, import_model=False: {
            "python":sys.executable, "commit":"a"*40,
            "requirements_sha256":"b"*64})
    def fake_generate(**kwargs):
        original = read_midi(kwargs["source_path"])
        candidate = pretty_midi.PrettyMIDI(initial_tempo=70)
        candidate.instruments = original.instruments[:]
        new = pretty_midi.Instrument(program=0, name="AI")
        new.notes.append(pretty_midi.Note(80, 72, 0, 0.8))
        candidate.instruments.append(new)
        write_midi(candidate, kwargs["output_path"])
        create_proposal(kwargs["source_path"], kwargs["output_path"],
                        kwargs["manifest_path"], locked_tracks=[0])
        class Result:
            tracks = 2
            notes = 2
        return Result()
    monkeypatch.setattr("midivolt.acceptance.generate_candidate", fake_generate)
    outcome = acceptance_run(
        model="text2midi", environment=fake_env, checkout=root,
        checkpoint="fake", source=source, out=can, manifest=man,
        report=rep, locked_tracks=[0], confirm_inference=True)
    assert outcome["new_notes"] == 1
    assert outcome["musical_quality_verified"] is False
    assert outcome["real_inference_completed"] is True
    assert json.loads(rep.read_text())["candidate_sha256"]
    assert check_proposal(man)[1]["locked_tracks"] == [0]
    with pytest.raises(FileExistsError):
        acceptance_run(
            model="text2midi", environment=fake_env, checkout=root,
            checkpoint="fake", source=source, out=can, manifest=man,
            report=rep, locked_tracks=[0], confirm_inference=True)

def test_acceptance_rejects_wrong_source_and_model(tmp_path, monkeypatch):
    source = _melody(tmp_path)
    root = tmp_path / "source_checkout"
    root.mkdir()
    env = tmp_path / "env"
    env.mkdir()
    monkeypatch.setattr(
        "midivolt.acceptance._read_managed_environment",
        lambda _: {"model":"anticipation","installed":True,
                   "checkout":str(root)})
    kwargs = dict(model="text2midi", environment=env, checkout=root,
                  checkpoint="x", source=source,
                  out=tmp_path/"can.mid", manifest=tmp_path/"plan.json",
                  report=tmp_path/"accept.json", locked_tracks=[0],
                  confirm_inference=True)
    with pytest.raises(ValueError, match="does not match"):
        acceptance_run(**kwargs)


def test_offline_requirements_reject_direct_url_before_pip(tmp_path, monkeypatch):
    """PIP_NO_INDEX must not be relied upon to block direct artifact URLs."""
    import hashlib
    from midivolt.environments import install_requirements
    root, commit = checkout(tmp_path)
    (root/"requirements.txt").write_text(
        "example @ https://malicious.invalid/wheel.whl\n")
    digest = hashlib.sha256((root/"requirements.txt").read_bytes()).hexdigest()
    env = tmp_path/"venv"
    env.mkdir()
    wheelhouse = tmp_path/"wheelhouse"
    wheelhouse.mkdir()
    monkeypatch.setattr(
        "midivolt.environments._read_managed_environment",
        lambda _: {"model":"text2midi", "checkout":str(root),
                   "expected_commit":commit, "requirements_sha256":digest,
                   "installed":False, "venv_python":sys.executable})
    monkeypatch.setattr("midivolt.environments._inspect_checkout", lambda *a: None)
    with pytest.raises(EnvironmentError, match="Offline install refuses"):
        install_requirements(env, confirm=True, wheelhouse=wheelhouse)
