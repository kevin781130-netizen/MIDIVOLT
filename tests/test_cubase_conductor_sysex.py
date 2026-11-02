"""Conductor SysEx must survive genuine Type-1 Cubase normalization."""
from __future__ import annotations

import mido
import pytest

from midivolt.cubase_smf import compare_smf, prepare_smf


def _absolute_sysex(track):
    tick = 0
    found = []
    for message in track:
        tick += message.time
        if message.type == "sysex":
            found.append((tick, tuple(message.data)))
    return found


@pytest.mark.parametrize("ppq", [220, 480, 960])
@pytest.mark.parametrize("with_conductor_notes", [False, True])
def test_conductor_sysex_remains_on_conductor(tmp_path, ppq, with_conductor_notes):
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)
    conductor = mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.Message("sysex", data=(0x7D, 0x01), time=ppq//2),
        mido.Message("sysex", data=(0x7D, 0x02), time=ppq//2),
    ])
    if with_conductor_notes:
        conductor.extend([
            mido.Message("note_on", channel=0, note=67, velocity=90, time=0),
            mido.Message("note_off", channel=0, note=67, velocity=0, time=ppq),
        ])
        tail = ppq
    else:
        tail = ppq*2
    conductor.append(mido.MetaMessage("end_of_track", time=tail))
    lead = mido.MidiTrack([
        mido.MetaMessage("track_name", name="Lead", time=0),
        mido.Message("note_on", channel=1, note=60, velocity=90, time=0),
        mido.Message("note_off", channel=1, note=60, velocity=0, time=ppq),
        mido.MetaMessage("end_of_track", time=2*ppq),
    ])
    midi.tracks = [conductor, lead]
    src = tmp_path / "original.mid"
    out = tmp_path / "cubase.mid"
    midi.save(src)
    result = prepare_smf(src, out, ppq=ppq)
    exported = mido.MidiFile(out)
    assert result["type"] == 1
    assert _absolute_sysex(exported.tracks[0]) == [(ppq//2, (125, 1)), (ppq, (125, 2))]
    assert sum(msg.type == "sysex" for track in exported.tracks[1:] for msg in track) == 0
    proof = compare_smf(src, out)
    assert proof["missing_events"] == proof["added_events"] == 0
    assert proof["musical_track_membership_preserved"]
    assert proof["song_duration_preserved"]
    assert proof["exact_event_match"]


def test_nonconductor_sysex_stays_with_instrument_lane(tmp_path):
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks = [
        mido.MidiTrack([mido.MetaMessage("end_of_track", time=960)]),
        mido.MidiTrack([
            mido.MetaMessage("track_name", name="Hardware synth", time=0),
            mido.Message("sysex", data=(0x7D, 0x21), time=240),
            mido.Message("note_on", channel=0, note=64, velocity=99, time=0),
            mido.Message("note_off", channel=0, note=64, velocity=0, time=480),
            mido.MetaMessage("end_of_track", time=240),
        ]),
    ]
    src, out = tmp_path/"src.mid", tmp_path/"dst.mid"
    midi.save(src)
    prepare_smf(src, out, ppq=480)
    returned = mido.MidiFile(out)
    assert _absolute_sysex(returned.tracks[0]) == []
    assert _absolute_sysex(returned.tracks[1]) == [(240, (125, 33))]
    assert compare_smf(src, out)["exact_event_match"]
