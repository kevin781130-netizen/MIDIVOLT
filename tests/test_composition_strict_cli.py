"""Strict-parts CLI smoke using a fake provider, without external model assets."""

import json

import pretty_midi
import pytest

from midivolt import compose_cli
from midivolt.io import read_midi, write_midi
from midivolt.review_engine import check_proposal, apply_proposal


class MockProvider:
    name = "mock-provider"

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, tempo, seed=None):
        self.calls.append((prompt, tempo, seed))
        program = 0 if "Piano" in prompt else 40
        result = pretty_midi.PrettyMIDI(initial_tempo=120)
        track = pretty_midi.Instrument(program=program, name="Fake generated part")
        track.notes.append(pretty_midi.Note(80, 60, 0, 0.5))
        result.instruments.append(track)
        return result


def test_strict_cli_generates_two_parts_with_hash_bound_approval(tmp_path, monkeypatch, capsys):
    src = tmp_path / "melody.mid"
    original = pretty_midi.PrettyMIDI(initial_tempo=60)
    flute = pretty_midi.Instrument(73, name="Locked melody")
    flute.notes.append(pretty_midi.Note(80, 65, 0, 1))
    original.instruments.append(flute)
    write_midi(original, src)
    unchanged = src.read_bytes()

    mock = MockProvider()
    monkeypatch.setattr(compose_cli, "LocalText2MidiProvider", lambda **kwargs: mock)
    candidate, manifest = tmp_path / "candidate.mid", tmp_path / "proposal.json"
    argv = [
        "--strict-parts", "--source", str(src), "--prompt", "鋼琴、小提琴",
        "--python", "unused", "--checkout", "unused", "--checkpoint", "unused",
        "--vocab", "unused", "--t5-dir", "unused",
        "--candidate", str(candidate), "--manifest", str(manifest), "--lock", "0",
    ]
    assert compose_cli.main(argv) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["strict_parts"] is True and output["approved"] is False
    assert [p["role"] for p in output["composition_plan"]["parts"]] == ["piano", "violin"]
    assert len(mock.calls) == 2
    assert [inst.program for inst in read_midi(candidate).instruments] == [73, 0, 40]
    assert src.read_bytes() == unchanged
    _, diff = check_proposal(manifest)
    assert diff["locked_tracks"] == [0] and diff["notes_added"] == 2
    with pytest.raises(PermissionError):
        apply_proposal(manifest, tmp_path / "approved.mid", approved=False)
    assert compose_cli.main(argv) == 2
    assert apply_proposal(manifest, tmp_path / "approved.mid", approved=True)["approved"]


def test_strict_cli_preflight_rejects_unknown_program(tmp_path, monkeypatch):
    src = tmp_path / "source.mid"
    midi = pretty_midi.PrettyMIDI()
    part = pretty_midi.Instrument(73)
    part.notes.append(pretty_midi.Note(80, 65, 0, 1))
    midi.instruments.append(part)
    write_midi(midi, src)
    mock = MockProvider()
    monkeypatch.setattr(compose_cli, "LocalText2MidiProvider", lambda **kwargs: mock)
    candidate, manifest = tmp_path / "candidate.mid", tmp_path / "proposal.json"
    argv = [
        "--strict-parts", "--source", str(src), "--prompt", "鋼琴",
        "--python", "unused", "--checkout", "unused", "--checkpoint", "unused",
        "--vocab", "unused", "--t5-dir", "unused",
        "--candidate", str(candidate), "--manifest", str(manifest), "--lock", "0",
        "--program", "guitar=24",
    ]
    assert compose_cli.main(argv) == 2
    assert not candidate.exists() and not manifest.exists() and not mock.calls


def test_explicit_harmony_cli_includes_generation_context_and_review(tmp_path, monkeypatch, capsys):
    src = tmp_path / "melody.mid"
    original = pretty_midi.PrettyMIDI(initial_tempo=60)
    part = pretty_midi.Instrument(73, name="Original")
    part.notes.append(pretty_midi.Note(80, 60, 0, 1))
    original.instruments.append(part)
    write_midi(original, src)
    provider = MockProvider()
    monkeypatch.setattr(compose_cli, "LocalText2MidiProvider", lambda **kwargs: provider)
    candidate, manifest = tmp_path / "new.mid", tmp_path / "new.json"
    args = [
        "--strict-parts", "--source", str(src), "--prompt", "鋼琴",
        "--python", "unused", "--checkout", "unused", "--checkpoint", "unused",
        "--vocab", "unused", "--t5-dir", "unused",
        "--candidate", str(candidate), "--manifest", str(manifest),
        "--lock", "0", "--harmonic-key", "C major",
        "--min-harmony-score", "0.8", "--retry-per-part", "0",
    ]
    assert compose_cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert "Declared key: C major" in provider.calls[0][0]
    attempts = result["composition_plan"]["quality_attempts"]
    assert attempts[0]["accepted"]
    assert attempts[0]["harmony_metrics"]["score"] == 1.0
    assert result["composition_plan"]["quality_policy"]["harmony_gating_enabled"]
    assert result["approved"] is False
    assert candidate.exists() and manifest.exists()
    _, diff = check_proposal(manifest)
    assert diff["notes_added"] == 1


def test_harmony_cli_is_strict_only(tmp_path, monkeypatch):
    src = tmp_path / "source.mid"
    original = pretty_midi.PrettyMIDI(initial_tempo=60)
    part = pretty_midi.Instrument(73)
    part.notes.append(pretty_midi.Note(80, 60, 0, 1))
    original.instruments.append(part)
    write_midi(original, src)
    provider = MockProvider()
    monkeypatch.setattr(compose_cli, "LocalText2MidiProvider", lambda **kwargs: provider)
    candidate = tmp_path / "candidate.mid"
    manifest = tmp_path / "plan.json"
    args = [
        "--source", str(src), "--prompt", "鋼琴", "--python", "unused",
        "--checkout", "unused", "--checkpoint", "unused", "--vocab", "unused",
        "--t5-dir", "unused", "--candidate", str(candidate),
        "--manifest", str(manifest), "--lock", "0",
        "--harmonic-key", "C major",
    ]
    assert compose_cli.main(args) == 2
    assert not candidate.exists() and not manifest.exists()
    assert not provider.calls
