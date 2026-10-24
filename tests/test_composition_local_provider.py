"""End-to-end local subprocess to AI Composition Engine review tests.

A fake runner exercises the real subprocess path; no pretrained checkpoint,
downloads, or network are used. This does NOT prove model quality/weights.
"""
from __future__ import annotations

import sys

import pretty_midi
import pytest

from midivolt.compose_cli import main
from midivolt.io import read_midi, write_midi
from midivolt.review_engine import apply_proposal, check_proposal


def fixtures(tmp_path, *, runner_mode="ok"):
    src = tmp_path / "melody.mid"
    original = pretty_midi.PrettyMIDI(initial_tempo=60)
    flute = pretty_midi.Instrument(program=73, name="Preserve flute")
    flute.notes.append(pretty_midi.Note(95, 65, 0, 1))
    flute.control_changes.append(pretty_midi.ControlChange(1, 50, 0))
    original.instruments.append(flute)
    write_midi(original, src)
    root = tmp_path / "upstream"
    (root / "model").mkdir(parents=True)
    (root / "model" / "transformer_model.py").write_text("# fixture")
    ckpt = tmp_path / "weights.bin"
    ckpt.write_bytes(b"fixture-only")
    vocab = tmp_path / "vocab.pkl"
    vocab.write_bytes(b"fixture-only")
    tokenizer = tmp_path / "tokenizer"
    tokenizer.mkdir()
    runner = tmp_path / "runner.py"
    if runner_mode == "crash":
        runner.write_text("raise RuntimeError('dummy crash')\n")
    else:
        notes = (
            'piano.notes.append(pretty_midi.Note(80,60,0,0.5))\n'
            'bass.notes.append(pretty_midi.Note(78,36,0,0.5))\n'
        ) if runner_mode == "ok" else ""
        runner.write_text(
            'import argparse, pretty_midi\n'
            'p=argparse.ArgumentParser()\n'
            'p.add_argument("--out",required=True)\n'
            'args,_=p.parse_known_args()\n'
            'm=pretty_midi.PrettyMIDI(initial_tempo=120)\n'
            'piano=pretty_midi.Instrument(0,name="AI Piano")\n'
            'bass=pretty_midi.Instrument(32,name="AI Bass")\n'
            + notes +
            'm.instruments.extend([piano,bass])\n'
            'm.write(args.out)\n'
        )
    candidate = tmp_path / "candidate.mid"
    manifest = tmp_path / "plan.json"
    argv = [
        "--source", str(src), "--prompt", "Add piano and bass",
        "--python", sys.executable, "--checkout", str(root),
        "--checkpoint", str(ckpt), "--vocab", str(vocab),
        "--t5-dir", str(tokenizer), "--candidate", str(candidate),
        "--manifest", str(manifest), "--lock", "0", "--seed", "42",
    ]
    return src, candidate, manifest, runner, argv


def test_child_process_to_three_track_review_and_explicit_approval(tmp_path, monkeypatch, capsys):
    src, candidate, manifest, runner, argv = fixtures(tmp_path)
    monkeypatch.setattr("midivolt.model_adapters._runner_script", lambda _: runner)
    original_bytes = src.read_bytes()
    assert main(argv) == 0
    capsys.readouterr()
    assert candidate.exists() and manifest.exists()
    assert src.read_bytes() == original_bytes
    result = read_midi(candidate)
    assert [inst.name for inst in result.instruments] == [
        "Preserve flute", "AI Piano", "AI Bass"
    ]
    assert result.get_tempo_changes()[1].tolist() == [60.0]
    assert result.instruments[1].notes[0].end == pytest.approx(1.0, abs=0.002)
    _, review = check_proposal(manifest)
    assert review["notes_added"] == 2 and review["notes_removed"] == 0
    assert review["locked_tracks"] == [0]
    with pytest.raises(PermissionError):
        apply_proposal(manifest, tmp_path / "approved.mid", approved=False)
    applied = apply_proposal(manifest, tmp_path / "approved.mid", approved=True)
    assert applied["approved"] and len(read_midi(applied["output"]).instruments) == 3
    assert main(argv) == 2  # Never overwrite candidate or manifest.


def test_invalid_lock_never_runs_model(tmp_path, monkeypatch):
    src, candidate, manifest, runner, argv = fixtures(tmp_path)
    monkeypatch.setattr("midivolt.model_adapters._runner_script", lambda _: runner)
    argv[argv.index("--lock") + 1] = "5"
    assert main(argv) == 2
    assert not candidate.exists() and not manifest.exists()
    assert len(read_midi(src).instruments) == 1


def test_missing_model_files_fail_without_publishing(tmp_path):
    _, candidate, manifest, _, argv = fixtures(tmp_path)
    # Required paths exist except this checkpoint. Preflight fails closed.
    argv[argv.index("--checkpoint") + 1] = str(tmp_path / "missing.bin")
    assert main(argv) == 2
    assert not candidate.exists() and not manifest.exists()


@pytest.mark.parametrize("mode", ["crash", "empty"])
def test_broken_or_empty_runner_never_publishes(tmp_path, monkeypatch, mode):
    _, candidate, manifest, runner, argv = fixtures(tmp_path, runner_mode=mode)
    monkeypatch.setattr("midivolt.model_adapters._runner_script", lambda _: runner)
    assert main(argv) == 2
    assert not candidate.exists() and not manifest.exists()
