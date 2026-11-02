"""Protect Cubase MIDI track ownership against false PASS in global event audit."""
from pathlib import Path
import mido
import pytest

from midivolt.cubase_cli import main as cubase_main
from midivolt.cubase_smf import compare_smf, prepare_smf


def create(path, *, swapped=False, all_on_one=False, type1=True):
    midi = mido.MidiFile(type=1 if type1 else 0, ticks_per_beat=480)
    names = [('Lead', 60), ('Bass', 48)]
    if swapped:
        names = [('Lead', 48), ('Bass', 60)]
    conductor = mido.MidiTrack([
        mido.MetaMessage('set_tempo', tempo=500000, time=0),
        mido.MetaMessage('end_of_track', time=1920)])
    if type1:
        midi.tracks.append(conductor)
        for name, note in names:
            lane = mido.MidiTrack([
                mido.MetaMessage('track_name', name=name, time=0),
                mido.Message('program_change', channel=0, program=0, time=0),
                mido.Message('note_on', channel=0, note=note, velocity=70, time=0),
                mido.Message('note_off', channel=0, note=note, velocity=0, time=480),
                mido.MetaMessage('end_of_track', time=1440)])
            midi.tracks.append(lane)
    else:
        track=mido.MidiTrack([
            mido.MetaMessage('set_tempo', tempo=500000, time=0),
            mido.Message('note_on', channel=0, note=60, velocity=70, time=0),
            mido.Message('note_on', channel=9, note=36, velocity=70, time=0),
            mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
            mido.Message('note_off', channel=9, note=36, velocity=0, time=0),
            mido.MetaMessage('end_of_track', time=1440),
        ])
        midi.tracks=[track]
    if all_on_one:
        # Keep the complete global event multiset and conductor EOT, but move
        # all notes from Bass to Lead without changing note/channel/timestamps.
        bass = midi.tracks[2]
        lead = midi.tracks[1]
        # Rebuild in absolute-time order; remove Bass note events.
        moved=[]; current=0
        for msg in bass:
            current += msg.time
            if msg.type in ('note_on','note_off'):
                moved.append((current,msg.copy(time=0)))
        current=0; events=[]
        for msg in lead:
            current+=msg.time
            if msg.type!='end_of_track':events.append((current,msg.copy(time=0)))
        events+=moved
        events.sort(key=lambda t:t[0])
        new=mido.MidiTrack(); at=0
        for tick,msg in events:
            new.append(msg.copy(time=tick-at));at=tick
        new.append(mido.MetaMessage('end_of_track', time=1920-at))
        midi.tracks[1]=new
        midi.tracks[2]=mido.MidiTrack([
            mido.MetaMessage('track_name', name='Bass', time=0),
            mido.Message('program_change',channel=0,program=0,time=0),
            mido.MetaMessage('end_of_track',time=1920)])
    midi.save(str(path))
    return path


def test_strict_rejects_lead_bass_swap_with_identical_global_events(tmp_path):
    src=create(tmp_path/'source.mid')
    bad=create(tmp_path/'swapped.mid',swapped=True)
    result=compare_smf(src,bad)
    assert result['missing_events']==result['added_events']==0
    assert result['song_duration_preserved'] is True
    assert result['musical_track_membership_preserved'] is False
    assert result['exact_event_match'] is False
    assert cubase_main(['compare','--reference',str(src),'--returned',str(bad),'--strict'])==3


def test_strict_rejects_collapse_of_two_lanes_with_identical_events(tmp_path):
    src=create(tmp_path/'source.mid')
    bad=create(tmp_path/'collapsed.mid',all_on_one=True)
    result=compare_smf(src,bad)
    assert result['missing_events']==result['added_events']==0
    assert result['musical_track_membership_preserved'] is False
    assert result['exact_event_match'] is False


def test_type1_relocation_and_track_order_permutation_remain_valid(tmp_path):
    src=create(tmp_path/'original.mid')
    exported=tmp_path/'cubase.mid'
    prepare_smf(src,exported,ppq=480)
    proof=compare_smf(src,exported)
    assert proof['musical_track_membership_preserved'] is True
    assert proof['exact_event_match'] is True
    midi=mido.MidiFile(exported)
    midi.tracks[1],midi.tracks[2] = midi.tracks[2],midi.tracks[1]
    reordered=tmp_path/'reordered.mid'
    midi.save(reordered)
    assert compare_smf(src,reordered)['exact_event_match'] is True


@pytest.mark.parametrize('dst_ppq',[220,480,960])
def test_type0_split_into_type1_does_not_fail_track_membership(tmp_path,dst_ppq):
    src=create(tmp_path/'combined.mid',type1=False)
    output=tmp_path/'type1.mid'
    prepare_smf(src,output,ppq=dst_ppq)
    report=compare_smf(src,output)
    assert report['exact_event_match'] is True
    assert report['musical_track_membership_preserved'] is True


def test_type1_to_type0_is_not_accepted_as_lossless_multitrack(tmp_path):
    src=create(tmp_path/'source.mid')
    raw=mido.MidiFile(src)
    merged=mido.MidiFile(type=0,ticks_per_beat=480)
    timed=[]
    for track in raw.tracks:
        absolute=0
        for msg in track:
            absolute+=msg.time
            if msg.type!='end_of_track':timed.append((absolute,msg.copy(time=0)))
    new=mido.MidiTrack(); at=0
    for tick,msg in sorted(timed,key=lambda x:x[0]):
        new.append(msg.copy(time=tick-at));at=tick
    new.append(mido.MetaMessage('end_of_track',time=1920-at))
    merged.tracks=[new]
    path=tmp_path/'merged.mid';merged.save(path)
    result=compare_smf(src,path)
    assert result['missing_events']==result['added_events']==0
    assert result['musical_track_membership_preserved'] is False
    assert result['exact_event_match'] is False
