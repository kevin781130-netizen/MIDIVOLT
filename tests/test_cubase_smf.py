"""MIDI Type 0/1, controller, tempo and Cubase profile roundtrip regression."""
from __future__ import annotations

import mido
import pytest

from midivolt.cubase_smf import inspect_smf, prepare_smf, compare_smf
from midivolt.cubase_cli import main


def create_type1(path, ppq=960, offconductor=False):
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)
    conductor = mido.MidiTrack()
    conductor.extend([
        mido.MetaMessage("track_name", name="MIDIVOLT conductor", time=0),
        mido.MetaMessage("set_tempo", tempo=857143, time=0),
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        mido.MetaMessage("key_signature", key="F", time=0),
        mido.MetaMessage("end_of_track", time=0),
    ])
    lead = mido.MidiTrack()
    lead.extend([
        mido.MetaMessage("track_name", name="Synth flute", time=0),
        mido.Message("program_change", channel=0, program=73, time=0),
        mido.Message("control_change", channel=0, control=1, value=64, time=0),
        mido.Message("pitchwheel", channel=0, pitch=257, time=0),
        mido.Message("note_on", channel=0, note=65, velocity=83, time=240),
        mido.Message("note_off", channel=0, note=65, velocity=0, time=480),
        mido.MetaMessage("marker", text="Verse", time=0),
        mido.Message("sysex", data=(0x7D, 0x01), time=0),
    ])
    if offconductor:
        lead.append(mido.MetaMessage("set_tempo", tempo=700000, time=240))
    lead.append(mido.MetaMessage("end_of_track", time=0))
    bass = mido.MidiTrack()
    bass.extend([
        mido.MetaMessage("track_name", name="Bass", time=0),
        mido.Message("program_change", channel=1, program=32, time=0),
        mido.Message("note_on", channel=1, note=41, velocity=80, time=240),
        mido.Message("note_off", channel=1, note=41, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=0),
    ])
    midi.tracks = [conductor, lead, bass]
    midi.save(str(path))
    return path


def create_type0(path):
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=750000, time=0),
        mido.MetaMessage("time_signature", numerator=6, denominator=8, time=0),
        mido.Message("program_change", channel=0, program=73, time=0),
        mido.Message("program_change", channel=9, program=0, time=0),
        mido.Message("note_on", channel=0, note=60, velocity=90, time=240),
        mido.Message("note_on", channel=9, note=36, velocity=100, time=0),
        mido.Message("note_off", channel=9, note=36, velocity=0, time=60),
        mido.Message("note_off", channel=0, note=60, velocity=0, time=180),
        mido.MetaMessage("end_of_track", time=0),
    ])
    midi.tracks.append(track)
    midi.save(str(path))
    return path


def test_type1_strict_preservation_of_meta_channels_cc_pitch_sysex(tmp_path):
    source = create_type1(tmp_path / "source.mid", offconductor=True)
    info = inspect_smf(source)
    assert info["type"] == 1
    assert info["ppq"] == 960
    assert info["notes_on"] == 2
    assert info["control_changes"] == 1
    assert info["pitch_bends"] == 1
    assert info["sysex_events"] == 1
    assert info["nonconductor_global_meta"] == 1
    result = prepare_smf(source, tmp_path / "cubase.mid")
    assert result["type"] == 1
    assert result["ppq_export"] == 480
    exported = mido.MidiFile(str(tmp_path / "cubase.mid"))
    assert exported.type == 1
    assert exported.ticks_per_beat == 480
    assert len(exported.tracks) == 3
    assert all(
        msg.type not in ("set_tempo", "time_signature", "key_signature")
        for track in exported.tracks[1:] for msg in track
    )
    assert result["all_midi_events_preserved_after_tick_rescale"]
    assert compare_smf(source, result["output"])["exact_event_match"]


def test_type0_split_channels_drums_keep_channel9(tmp_path):
    source = create_type0(tmp_path / "type0.mid")
    result = prepare_smf(source, tmp_path / "type1.mid", ppq=480)
    assert result["tracks"] == 3
    output = mido.MidiFile(str(tmp_path / "type1.mid"))
    assert output.type == 1
    musical_channels = [
        {message.channel for message in track if hasattr(message, "channel")}
        for track in output.tracks[1:]
    ]
    assert musical_channels == [{0}, {9}]
    assert compare_smf(source, result["output"])["exact_event_match"]


def test_prepare_refuses_to_overwrite_source_or_existing_output(tmp_path):
    source = create_type1(tmp_path / "original.mid")
    previous = source.read_bytes()
    with pytest.raises(ValueError, match="differ"):
        prepare_smf(source, source)
    out = tmp_path / "out.mid"
    prepare_smf(source, out)
    with pytest.raises(FileExistsError):
        prepare_smf(source, out)
    assert source.read_bytes() == previous


def test_ppq_downsampling_refuses_collapsed_notes(tmp_path):
    midi = mido.MidiFile(type=1, ticks_per_beat=960)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500000, time=0)]))
    midi.tracks.append(mido.MidiTrack([
        mido.Message("note_on", channel=0, note=65, velocity=90, time=1),
        mido.Message("note_off", channel=0, note=65, velocity=0, time=1)]))
    src = tmp_path / "tiny.mid"
    midi.save(src)
    with pytest.raises(ValueError, match="collapse"):
        prepare_smf(src, tmp_path / "out.mid", ppq=24)
    assert not (tmp_path / "out.mid").exists()


def test_bad_smf_type2_is_rejected(tmp_path):
    midi = mido.MidiFile(type=2, ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.Message("note_on", channel=0, note=60, velocity=80, time=0),
        mido.Message("note_off", channel=0, note=60, velocity=0, time=480),
    ]))
    path = tmp_path / "type2.mid"
    midi.save(path)
    with pytest.raises(ValueError, match="type 2"):
        inspect_smf(path)


def test_compare_detects_changed_pitch_and_strict_cli(tmp_path, capsys):
    src = create_type1(tmp_path / "source.mid")
    out = tmp_path / "roundtrip.mid"
    prepare_smf(src, out)
    exported = mido.MidiFile(str(out))
    edited = False
    for track in exported.tracks:
        for message in track:
            if message.type == "note_on" and message.velocity > 0:
                message.note += 1
                edited = True
                break
        if edited:
            break
    assert edited
    exported.save(out)
    report = compare_smf(src, out)
    assert not report["exact_event_match"]
    assert report["missing_events"] >= 1
    assert report["added_events"] >= 1
    assert main(["compare", "--reference", str(src),
                 "--returned", str(out), "--strict"]) == 3


def test_cli_check_and_prepare_and_exact_compare(tmp_path, capsys):
    src = create_type1(tmp_path / "source.mid")
    out = tmp_path / "prepared.mid"
    assert main(["check", "--input", str(src)]) == 0
    assert main(["prepare", "--input", str(src),
                 "--out", str(out), "--ppq", "480"]) == 0
    assert main(["compare", "--reference", str(src),
                 "--returned", str(out), "--strict"]) == 0


def test_manual_roundtrip_can_be_distinct_file_but_same_events(tmp_path):
    src = create_type1(tmp_path / "source.mid")
    first = tmp_path / "prepared.mid"
    second = tmp_path / "returned.mid"
    prepare_smf(src, first)
    prepare_smf(first, second)
    assert compare_smf(first, second)["exact_event_match"]
    assert compare_smf(src, second)["exact_event_match"]


def test_invalid_destination_or_ppq_rejected(tmp_path):
    src = create_type1(tmp_path / "source.mid")
    for invalid_ppq in (0, 961, True):
        with pytest.raises(ValueError, match="PPQ"):
            prepare_smf(src, tmp_path / "out.mid", ppq=invalid_ppq)
    with pytest.raises(ValueError, match="Output"):
        prepare_smf(src, tmp_path / "out.wav")
