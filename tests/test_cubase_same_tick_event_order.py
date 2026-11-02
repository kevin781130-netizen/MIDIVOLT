"""A strict Cubase roundtrip must preserve ordered events at the same MIDI tick."""
from __future__ import annotations

from pathlib import Path
import mido
import pytest

from midivolt.cubase_cli import main as cubase_cli
from midivolt.cubase_smf import compare_smf, prepare_smf


def write_notes(path: Path, *, swapped: bool = False) -> None:
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    conductor = mido.MidiTrack([mido.MetaMessage("end_of_track", time=1440)])
    lead = mido.MidiTrack([
        mido.MetaMessage("track_name", name="Lead", time=0),
        mido.Message("note_on", channel=0, note=60, velocity=80, time=0),
        mido.Message("note_on" if swapped else "note_off", channel=0,
                     note=60, velocity=80 if swapped else 0, time=480),
        mido.Message("note_off" if swapped else "note_on", channel=0,
                     note=60, velocity=0 if swapped else 80, time=0),
        mido.Message("note_off", channel=0, note=60, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=480),
    ])
    midi.tracks = [conductor, lead]
    midi.save(str(path))


def test_strict_rejects_note_on_off_swap_at_same_tick(tmp_path: Path):
    reference, changed = tmp_path / "reference.mid", tmp_path / "swapped.mid"
    write_notes(reference)
    write_notes(changed, swapped=True)
    proof = compare_smf(reference, changed)
    assert proof["missing_events"] == proof["added_events"] == 0
    assert proof["song_duration_preserved"] is True
    assert proof["musical_track_membership_preserved"] is False
    assert proof["exact_event_match"] is False
    assert cubase_cli(["compare", "--reference", str(reference), "--returned", str(changed), "--strict"]) == 3


def test_strict_rejects_same_tick_controller_order_swap(tmp_path: Path):
    source = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack([
        mido.Message("control_change", channel=0, control=7, value=10, time=0),
        mido.Message("control_change", channel=0, control=7, value=100, time=0),
        mido.MetaMessage("end_of_track", time=480),
    ])
    source.tracks = [mido.MidiTrack([mido.MetaMessage("end_of_track", time=480)]), track]
    ref, changed = tmp_path / "ref.mid", tmp_path / "changed.mid"
    source.save(ref)
    source.tracks[1] = mido.MidiTrack([track[1].copy(), track[0].copy(), track[2].copy()])
    source.save(changed)
    proof = compare_smf(ref, changed)
    assert proof["missing_events"] == proof["added_events"] == 0
    assert proof["exact_event_match"] is False


@pytest.mark.parametrize("ppq", [220, 480, 960])
def test_normal_type1_export_keeps_same_tick_event_order(tmp_path: Path, ppq: int):
    src = tmp_path / "source.mid"
    out = tmp_path / "cubase.mid"
    write_notes(src)
    result = prepare_smf(src, out, ppq=ppq)
    assert result["musical_track_membership_preserved"] is True
    proof = compare_smf(src, out)
    assert proof["musical_track_membership_preserved"] is True
    assert proof["exact_event_match"] is True


def test_whole_track_reorder_remains_accepted(tmp_path: Path):
    src, other = tmp_path / "source.mid", tmp_path / "reordered.mid"
    write_notes(src)
    midi = mido.MidiFile(src)
    other_lane = mido.MidiTrack([
        mido.Message("note_on", channel=1, note=48, velocity=90, time=0),
        mido.Message("note_off", channel=1, note=48, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=960),
    ])
    midi.tracks.append(other_lane)
    midi.save(src)
    midi.tracks[1], midi.tracks[2] = midi.tracks[2], midi.tracks[1]
    midi.save(other)
    assert compare_smf(src, other)["exact_event_match"] is True
