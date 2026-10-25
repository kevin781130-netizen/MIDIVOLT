"""K8 acceptance-contract tests using fixtures only; NO actual model weights.

A mock provider is used ONLY to exercise the report file path and error
handling. These tests must never be described as pretrained inference.
"""

from __future__ import annotations

from hashlib import sha256
import json

import pretty_midi
import pytest

from midivolt import composition_acceptance as acceptance
from midivolt.composition_acceptance_cli import main as cli_main
from midivolt.io import read_midi, write_midi
from midivolt.review_engine import check_proposal


class FixtureProvider:
    name = "fixture_only_not_pretrained"
    def __init__(self, **kwargs):
        self.calls = []
    def generate(self, prompt, *, tempo, seed=None):
        self.calls.append((prompt, tempo, seed))
        result = pretty_midi.PrettyMIDI(initial_tempo=120)
        program = 40 if "Violin" in prompt else 0
        track = pretty_midi.Instrument(program=program, name="Synthetic")
        track.notes.append(pretty_midi.Note(90, 60, 0, 0.5))
        result.instruments.append(track)
        return result


def fixtures(tmp_path, monkeypatch):
    root = tmp_path / "Text2midi"
    (root / "model").mkdir(parents=True)
    (root / "model" / "transformer_model.py").write_text(
        "class Transformer:\n"
        "    def __init__(self, device=None):\n"
        "        T5EncoderModel.from_pretrained('google/flan-t5-base')\n"
        "    def generate(self): pass\n"
    )
    env = tmp_path / "model-env"
    env.mkdir()
    ckpt = tmp_path / "weights.bin"
    ckpt.write_bytes(b"DO NOT RUN: synthetic weights")
    vocab = tmp_path / "vocab_remi.pkl"
    vocab.write_bytes(b"DO NOT UNPICKLE: synthetic vocab")
    tokenizer = tmp_path / "tokenizer"
    tokenizer.mkdir()
    (tokenizer / "tokenizer_config.json").write_text("{}")
    (tokenizer / "config.json").write_text('{"model_type":"t5"}')
    (tokenizer / "model.safetensors").write_bytes(b"synthetic placeholder, not weights")
    src = tmp_path / "original.mid"
    original = pretty_midi.PrettyMIDI(initial_tempo=60)
    track = pretty_midi.Instrument(program=73, name="Locked melody")
    track.notes.append(pretty_midi.Note(90, 72, 0, 1))
    original.instruments.append(track)
    write_midi(original, src)
    monkeypatch.setattr(
        acceptance, "_read_managed_environment",
        lambda e: {"model": "text2midi", "installed": True, "checkout": str(root)},
    )
    monkeypatch.setattr(
        acceptance, "verify_environment",
        lambda e, import_model=False: {
            "model": "text2midi", "installed": True, "commit": "a"*40,
            "python": "fixture-path", "requirements_sha256": "b"*64,
        },
    )
    args = dict(
        environment=env, checkout=root, checkpoint=ckpt,
        checkpoint_sha256=sha256(ckpt.read_bytes()).hexdigest(),
        vocab=vocab, vocab_sha256=sha256(vocab.read_bytes()).hexdigest(),
        t5_dir=tokenizer, source=src, candidate=tmp_path / "candidate.mid",
        manifest=tmp_path / "proposal.json", report=tmp_path / "report.json",
        prompt="鋼琴、小提琴", locked_tracks=[0], confirm_inference=True,
        quality_retries=0, seed=42,
    )
    return args


def test_no_confirm_blocks_before_any_environment_check(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        acceptance, "_read_managed_environment",
        lambda _: called.append("unexpected"),
    )
    with pytest.raises(PermissionError, match="confirm-inference"):
        acceptance.run_composition_acceptance(
            confirm_inference=False, environment=tmp_path,
            checkout=tmp_path, checkpoint=tmp_path, checkpoint_sha256="0"*64,
            vocab=tmp_path, vocab_sha256="0"*64, t5_dir=tmp_path,
            source=tmp_path, candidate=tmp_path / "out.mid",
            manifest=tmp_path / "plan.json", report=tmp_path / "report.json",
            prompt="piano", locked_tracks=[0],
        )
    assert not called


def test_asset_hash_mismatch_fails_before_model_execution(tmp_path, monkeypatch):
    p = fixtures(tmp_path, monkeypatch)
    fake = FixtureProvider()
    monkeypatch.setattr(acceptance, "LocalText2MidiProvider", lambda **kw: fake)
    p["checkpoint_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        acceptance.run_composition_acceptance(**p)
    assert not fake.calls
    for k in ("candidate", "manifest", "report"):
        assert not p[k].exists()


def test_missing_tokenizer_config_fails_closed(tmp_path, monkeypatch):
    p = fixtures(tmp_path, monkeypatch)
    (p["t5_dir"] / "tokenizer_config.json").unlink()
    with pytest.raises(ValueError, match="tokenizer_config.json"):
        acceptance.run_composition_acceptance(**p)
    for k in ("candidate", "manifest", "report"):
        assert not p[k].exists()


def test_synthetic_provider_exercises_report_contract_but_not_real_weights(tmp_path, monkeypatch):
    p = fixtures(tmp_path, monkeypatch)
    provider = FixtureProvider()
    monkeypatch.setattr(acceptance, "LocalText2MidiProvider", lambda **kw: provider)
    output = acceptance.run_composition_acceptance(**p)
    assert len(provider.calls) == 2
    assert len(read_midi(p["candidate"]).instruments) == 3
    assert output["candidate_sha256"] == sha256(p["candidate"].read_bytes()).hexdigest()
    assert output["source_sha256"] == sha256(p["source"].read_bytes()).hexdigest()
    assert output["new_notes"] == 2
    assert output["approved_for_use"] is False
    assert output["commercial_training_data_rights_verified"] is False
    assert output["human_music_review_passed"] is False
    assert output["cubase_import_verified"] is False
    assert output["commercial_release_ready"] is False
    assert json.loads(p["report"].read_text())["candidate_sha256"] == output["candidate_sha256"]
    _, diff = check_proposal(p["manifest"])
    assert diff["notes_added"] == 2
    with pytest.raises(FileExistsError):
        acceptance.run_composition_acceptance(**p)
    assert len(provider.calls) == 2


def test_later_part_failure_never_publishes_success(tmp_path, monkeypatch):
    p = fixtures(tmp_path, monkeypatch)
    class ModelCrashes(FixtureProvider):
        def generate(self, prompt, *, tempo, seed=None):
            if "Violin" in prompt:
                raise RuntimeError("runner crash on second instrument")
            return super().generate(prompt, tempo=tempo, seed=seed)
    mock = ModelCrashes()
    monkeypatch.setattr(acceptance, "LocalText2MidiProvider", lambda **kw: mock)
    with pytest.raises(RuntimeError, match="runner crash"):
        acceptance.run_composition_acceptance(**p)
    for k in ("candidate", "manifest", "report"):
        assert not p[k].exists()


def test_cli_refuses_without_real_model_consent(capsys):
    # Parser-required flags are provided, but consent fails before any paths
    # are touched. No fake or downloaded model is used.
    args = []
    for key in ("env", "checkout", "checkpoint", "checkpoint-sha256", "vocab",
                "vocab-sha256", "t5-dir", "source", "candidate",
                "manifest", "report", "prompt"):
        args += ["--" + key, "fixture-placeholder"]
    args += ["--lock", "0"]
    assert cli_main(args) == 2
    assert "--confirm-inference" in capsys.readouterr().err
