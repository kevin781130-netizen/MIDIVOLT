"""Real SMF song-end regressions: Cubase export must not silently trim empty bars."""
from __future__ import annotations

import mido
import pytest

from midivolt.cubase_smf import prepare_smf, compare_smf
from midivolt.cubase_cli import main as cubase_main


def end(track):
    return sum(msg.time for msg in track)


def test_type1_preserves_trailing_silence_on_conductor_and_tracks(tmp_path):
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks = [
        mido.MidiTrack([
            mido.MetaMessage('set_tempo', tempo=500000, time=0),
            mido.MetaMessage('end_of_track', time=1920),
        ]),
        mido.MidiTrack([
            mido.MetaMessage('track_name', name='lead', time=0),
            mido.Message('note_on', channel=0, note=60, velocity=90, time=0),
            mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
            mido.MetaMessage('end_of_track', time=960),
        ]),
        mido.MidiTrack([
            mido.MetaMessage('track_name', name='bass', time=0),
            mido.Message('note_on', channel=1, note=48, velocity=90, time=0),
            mido.Message('note_off', channel=1, note=48, velocity=0, time=480),
            mido.MetaMessage('end_of_track', time=1440),
        ]),
    ]
    src, dst = tmp_path/'original.mid', tmp_path/'cubase.mid'
    midi.save(src)
    result = prepare_smf(src, dst, ppq=480)
    saved = mido.MidiFile(dst)
    assert [end(t) for t in saved.tracks] == [1920, 1440, 1920]
    assert result['song_end_tick_original'] == 1920
    assert result['song_end_tick_export'] == 1920
    assert result['song_duration_preserved_after_tick_rescale']
    assert compare_smf(src, dst)['exact_event_match'] is True


def test_type0_split_preserves_original_song_end_on_every_lane(tmp_path):
    midi = mido.MidiFile(type=0, ticks_per_beat=960)
    midi.tracks = [mido.MidiTrack([
        mido.MetaMessage('set_tempo', tempo=500000, time=0),
        mido.Message('note_on', channel=0, note=60, velocity=90, time=0),
        mido.Message('note_on', channel=9, note=36, velocity=90, time=0),
        mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
        mido.Message('note_off', channel=9, note=36, velocity=0, time=0),
        mido.MetaMessage('end_of_track', time=1440),
    ])]
    src, dst = tmp_path/'type0.mid', tmp_path/'type1.mid'
    midi.save(src)
    prepare_smf(src, dst, ppq=480)
    saved = mido.MidiFile(dst)
    assert saved.type == 1
    assert saved.ticks_per_beat == 480
    assert [end(t) for t in saved.tracks] == [960, 960, 960]
    assert compare_smf(src, dst)['exact_event_match'] is True


def test_strict_compare_rejects_silent_tail_truncation_even_if_events_identical(tmp_path):
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks = [mido.MidiTrack([
        mido.Message('note_on', note=60, velocity=90, time=0),
        mido.Message('note_off', note=60, velocity=0, time=480),
        mido.MetaMessage('end_of_track', time=1440),
    ])]
    source, shortened = tmp_path/'source.mid', tmp_path/'trimmed.mid'
    midi.save(source)
    midi.tracks[0][-1] = mido.MetaMessage('end_of_track', time=0)
    midi.save(shortened)
    result = compare_smf(source, shortened)
    assert result['missing_events'] == result['added_events'] == 0
    assert result['song_duration_preserved'] is False
    assert result['exact_event_match'] is False
    assert cubase_main(['compare', '--reference', str(source), '--returned', str(shortened), '--strict']) == 3


@pytest.mark.parametrize('src_ppq,dst_ppq,source_end,expected_end', [
    (220, 220, 880, 880),
    (960, 480, 1920, 960),
    (480, 960, 1920, 3840),
])
def test_export_preserves_song_end_through_ppq_rescaling(
        tmp_path, src_ppq, dst_ppq, source_end, expected_end):
    midi = mido.MidiFile(type=1, ticks_per_beat=src_ppq)
    midi.tracks = [mido.MidiTrack([
        mido.Message('note_on', note=62, velocity=80, time=0),
        mido.Message('note_off', note=62, velocity=0, time=src_ppq),
        mido.MetaMessage('end_of_track', time=source_end - src_ppq),
    ])]
    src, dst = tmp_path/'src.mid', tmp_path/'dst.mid'
    midi.save(src)
    output = prepare_smf(src, dst, ppq=dst_ppq)
    saved = mido.MidiFile(dst)
    assert max(map(end, saved.tracks)) == expected_end
    assert output['song_end_tick_export'] == expected_end
    assert compare_smf(src, dst)['exact_event_match'] is True
