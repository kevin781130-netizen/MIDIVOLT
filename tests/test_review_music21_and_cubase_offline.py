"""Real MIDI review/Cubase pre-hardware acceptance without music21 or an AI model."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import mido
import pretty_midi

from midivolt.prompt_music import generate_sketch, parse_prompt

# Refuse music21 imports even if a developer machine has it installed.
BLOCK_MUSIC21 = r'''
import builtins, runpy
original_import = builtins.__import__
def deny_music21(name, *args, **kwargs):
    if name == "music21" or name.startswith("music21."):
        raise ModuleNotFoundError("No module named 'music21'", name="music21")
    return original_import(name, *args, **kwargs)
builtins.__import__ = deny_music21
runpy.run_module("midivolt.review_cli", run_name="__main__")
'''


def review(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", BLOCK_MUSIC21, *args],
                          capture_output=True, text=True, timeout=30)


def cubase(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "midivolt.cubase_cli", *args],
                          capture_output=True, text=True, timeout=30)


def seeded_midi(tmp_path: Path) -> tuple[Path, Path]:
    source = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0, name="Original locked piano")
    piano.notes = [pretty_midi.Note(92, pitch, 0.0, 0.5) for pitch in (60, 64, 67)]
    source.instruments.append(piano)
    input_path = tmp_path / "source.mid"
    source.write(str(input_path))
    sketch = generate_sketch(parse_prompt("C major 2 bars 120 BPM full arrangement",
                                         bars=2, seed=42), source=source)
    output_path = tmp_path / "candidate.mid"
    sketch.write(str(output_path))
    return input_path, output_path


def test_review_help_without_music21():
    output = review("--help")
    assert output.returncode == 0, output.stderr
    assert "propose" in output.stdout
    assert "Traceback" not in output.stderr


def test_missing_music21_chord_proposal_refuses_without_traceback_or_artifacts(tmp_path):
    source, _ = seeded_midi(tmp_path)
    original = sha256(source.read_bytes()).hexdigest()
    candidate, manifest = tmp_path / "local-chords.mid", tmp_path / "local-chords.json"
    output = review("propose", "--input", str(source), "--chords", "Cmaj7",
                    "--candidate-out", str(candidate), "--manifest", str(manifest),
                    "--lock", "0")
    assert output.returncode == 2, output.stderr
    assert "music21 is required" in output.stderr
    assert "Traceback" not in output.stderr
    assert not candidate.exists() and not manifest.exists()
    assert sha256(source.read_bytes()).hexdigest() == original


def test_real_midi_review_requires_explicit_approval_and_preserves_source(tmp_path):
    source, candidate = seeded_midi(tmp_path)
    digest = sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "review.json"
    approved = tmp_path / "approved.mid"
    proposed = review("propose", "--input", str(source), "--candidate", str(candidate),
                      "--manifest", str(manifest), "--lock", "0")
    assert proposed.returncode == 0, proposed.stderr
    audit = json.loads(proposed.stdout)
    assert audit["notes_removed"] == 0 and audit["notes_added"] > 0
    assert audit["locked_tracks"] == [0]
    preview = review("preview", "--manifest", str(manifest))
    assert preview.returncode == 0, preview.stderr
    denied = review("apply", "--manifest", str(manifest), "--out", str(approved))
    assert denied.returncode == 2
    assert not approved.exists()
    accepted = review("apply", "--manifest", str(manifest), "--out", str(approved), "--approve")
    assert accepted.returncode == 0, accepted.stderr
    assert approved.is_file()
    assert sha256(source.read_bytes()).hexdigest() == digest
    parsed_src, parsed_final = pretty_midi.PrettyMIDI(str(source)), pretty_midi.PrettyMIDI(str(approved))
    assert len(parsed_src.instruments) == 1 and len(parsed_final.instruments) == 5
    assert [(n.pitch, n.velocity, n.start, n.end) for n in parsed_src.instruments[0].notes] == [
        (n.pitch, n.velocity, n.start, n.end) for n in parsed_final.instruments[0].notes]


def test_cubase_export_same_ppq_is_lossless_with_real_reviewed_midi(tmp_path):
    source, candidate = seeded_midi(tmp_path)
    manifest, approved, exported = (tmp_path / x for x in ("review.json", "approved.mid", "cubase.mid"))
    assert review("propose", "--input", str(source), "--candidate", str(candidate),
                  "--manifest", str(manifest), "--lock", "0").returncode == 0
    assert review("apply", "--manifest", str(manifest), "--out", str(approved),
                  "--approve").returncode == 0
    ppq = mido.MidiFile(str(approved)).ticks_per_beat
    result = cubase("prepare", "--input", str(approved), "--out", str(exported),
                    "--ppq", str(ppq))
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["note_events"] == 45 and output["type"] == 1
    assert output["all_midi_events_preserved_after_tick_rescale"] is True
    audit = cubase("compare", "--reference", str(approved), "--returned", str(exported), "--strict")
    assert audit.returncode == 0, audit.stderr
    counts = json.loads(audit.stdout)
    assert counts["exact_event_match"] is True and counts["missing_events"] == 0
    assert counts["added_events"] == 0 and counts["note_on_returned"] == 45
    assert counts["cubase_import_verified"] is False


def test_ppq_conversion_reports_possible_quantization_not_cubase_acceptance(tmp_path):
    source, candidate = seeded_midi(tmp_path)
    manifest, approved, exported = (tmp_path / x for x in ("review.json", "approved.mid", "cubase480.mid"))
    assert review("propose", "--input", str(source), "--candidate", str(candidate),
                  "--manifest", str(manifest), "--lock", "0").returncode == 0
    assert review("apply", "--manifest", str(manifest), "--out", str(approved), "--approve").returncode == 0
    prep = cubase("prepare", "--input", str(approved), "--out", str(exported), "--ppq", "480")
    assert prep.returncode == 0, prep.stderr
    prepared = json.loads(prep.stdout)
    assert prepared["timing_quantization_possible"] is True
    assert prepared["cubase_application_import_verified"] is False
    assert prepared["note_events"] == 45
    comp = cubase("compare", "--reference", str(approved), "--returned", str(exported), "--strict")
    assert comp.returncode == 3, comp.stderr
    report = json.loads(comp.stdout)
    assert report["exact_event_match"] is False
    assert report["note_on_reference"] == report["note_on_returned"] == 45
