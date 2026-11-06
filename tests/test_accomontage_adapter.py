"""Contract tests for the external-file-only AccoMontage bridge (no weights)."""
import json

import pretty_midi
import pytest

from midivolt.accomontage_adapter import prepare, ingest, _sections
from midivolt.review_engine import check_proposal, apply_proposal


def _midi(path, *, meter=4, bars=4):
    m = pretty_midi.PrettyMIDI(initial_tempo=70)
    m.time_signature_changes.append(pretty_midi.TimeSignature(meter, 4, 0))
    lead = pretty_midi.Instrument(program=73, name="Lead")
    lead.notes.append(pretty_midi.Note(100, 67, 0.0, 0.5))
    chords = pretty_midi.Instrument(program=0, name="Chords")
    duration = (60 / 70) * meter * bars
    chords.notes.append(pretty_midi.Note(80, 60, 0.0, duration))
    m.instruments = [lead, chords]
    m.write(str(path))
    return path


def _generated(path):
    m = pretty_midi.PrettyMIDI(initial_tempo=120)
    copied = pretty_midi.Instrument(73, name="Upstream original melody")
    copied.notes.append(pretty_midi.Note(100, 67, 0.0, 0.5))
    harmony = pretty_midi.Instrument(0, name="AccoMontage piano")
    harmony.notes.append(pretty_midi.Note(80, 64, 0.5, 1.0))
    m.instruments = [copied, harmony]
    m.write(str(path))
    return path


def test_16_bar_segments_are_supported():
    assert _sections("A16B8") == 24
    with pytest.raises(ValueError):
        _sections("A17")


def test_prepare_stages_two_tracks_without_touching_original(tmp_path):
    original = _midi(tmp_path / "song.mid")
    before = original.read_bytes()
    request = prepare(source=original, workdir=tmp_path / "stage",
                      melody_track=0, chord_track=1, segments="A4")
    assert original.read_bytes() == before
    staged = pretty_midi.PrettyMIDI(request["lead_sheet"])
    assert [i.name for i in staged.instruments] == ["Lead", "Chords"]
    assert request["inference"] == "NOT_RUN"
    assert request["license_gate"] == "UNVERIFIED"
    assert json.loads((tmp_path / "stage" / "request.json").read_text())["schema"] == request["schema"]


def test_import_adds_only_selected_accompaniment_and_requires_review(tmp_path):
    src = _midi(tmp_path / "song.mid")
    original_bytes = src.read_bytes()
    prepare(source=src, workdir=tmp_path / "stage", melody_track=0,
            chord_track=1, segments="A4")
    model = _generated(tmp_path / "external.mid")
    report = ingest(request=tmp_path / "stage" / "request.json", generated=model,
                    accompaniment_track=1, output=tmp_path / "candidate.mid",
                    manifest=tmp_path / "proposal.json")
    assert report["release_approved"] is False
    assert report["inference_verified"] is False
    assert src.read_bytes() == original_bytes
    candidate = pretty_midi.PrettyMIDI(str(tmp_path / "candidate.mid"))
    assert [i.name for i in candidate.instruments] == [
        "Lead", "Chords", "MIDIVOLT AI | AccoMontage piano"]
    _, review = check_proposal(tmp_path / "proposal.json")
    assert review["locked_tracks"] == [0]
    assert review["notes_added"] == 1
    with pytest.raises(PermissionError):
        apply_proposal(tmp_path / "proposal.json", tmp_path / "approved.mid",
                       approved=False)
    assert not (tmp_path / "approved.mid").exists()


def test_rejects_wrong_meter_and_unequal_segments(tmp_path):
    wrong = _midi(tmp_path / "three-four.mid", meter=3)
    with pytest.raises(ValueError, match="4/4"):
        prepare(source=wrong, workdir=tmp_path / "stage",
                melody_track=0, chord_track=1, segments="A4")
    song = _midi(tmp_path / "four-four.mid")
    with pytest.raises(ValueError, match="exactly"):
        prepare(source=song, workdir=tmp_path / "another",
                melody_track=0, chord_track=1, segments="A8")
    assert not (tmp_path / "another").exists()


def test_rejects_changed_source_before_import(tmp_path):
    src = _midi(tmp_path / "song.mid")
    prepare(source=src, workdir=tmp_path / "stage",
            melody_track=0, chord_track=1, segments="A4")
    src.write_bytes(src.read_bytes() + b"EXTRA")
    with pytest.raises(ValueError, match="changed"):
        ingest(request=tmp_path / "stage" / "request.json",
               generated=_generated(tmp_path / "external.mid"),
               accompaniment_track=1, output=tmp_path / "candidate.mid",
               manifest=tmp_path / "proposal.json")
    assert not (tmp_path / "candidate.mid").exists()


def test_rejects_ambiguous_track_and_no_overwrite(tmp_path):
    src = _midi(tmp_path / "song.mid")
    prepare(source=src, workdir=tmp_path / "stage",
            melody_track=0, chord_track=1, segments="A4")
    raw = _generated(tmp_path / "external.mid")
    common = dict(request=tmp_path / "stage" / "request.json", generated=raw,
                  output=tmp_path / "candidate.mid",
                  manifest=tmp_path / "proposal.json")
    with pytest.raises(ValueError, match="track index"):
        ingest(accompaniment_track=99, **common)
    assert not (tmp_path / "candidate.mid").exists()
    target = tmp_path / "candidate.mid"
    target.write_bytes(b"DO NOT OVERWRITE")
    with pytest.raises(FileExistsError):
        ingest(accompaniment_track=1, **common)
    assert target.read_bytes() == b"DO NOT OVERWRITE"

def test_rejects_request_track_swap_without_publishing(tmp_path):
    src = _midi(tmp_path / "song.mid")
    prepare(source=src, workdir=tmp_path / "stage",
            melody_track=0, chord_track=1, segments="A4")
    request_file = tmp_path / "stage" / "request.json"
    data = json.loads(request_file.read_text())
    data["source_melody_track"] = 1
    data["source_chord_track"] = 0
    request_file.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="does not match"):
        ingest(request=request_file,
               generated=_generated(tmp_path / "external.mid"),
               accompaniment_track=1, output=tmp_path / "candidate.mid",
               manifest=tmp_path / "proposal.json")
    assert not (tmp_path / "candidate.mid").exists()
    assert not (tmp_path / "proposal.json").exists()


def test_rejects_staged_midi_mutation(tmp_path):
    src = _midi(tmp_path / "song.mid")
    request = prepare(source=src, workdir=tmp_path / "stage",
                      melody_track=0, chord_track=1, segments="A4")
    staged = pretty_midi.PrettyMIDI(request["lead_sheet"])
    staged.instruments[0].notes[0].pitch += 2
    staged.write(request["lead_sheet"])
    with pytest.raises(ValueError, match="changed"):
        ingest(request=tmp_path / "stage" / "request.json",
               generated=_generated(tmp_path / "external.mid"),
               accompaniment_track=1, output=tmp_path / "candidate.mid",
               manifest=tmp_path / "proposal.json")
    assert not (tmp_path / "candidate.mid").exists()
