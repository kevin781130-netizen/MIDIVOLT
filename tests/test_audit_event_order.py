import mido
import pytest
from midivolt.cubase_smf import compare_smf

@pytest.mark.parametrize('kind', ['channel', 'tempo'])
def test_strict_rejects_same_tick_order_change(tmp_path, kind):
    mid = mido.MidiFile(type=0 if kind == 'channel' else 1)
    track = mido.MidiTrack(); mid.tracks.append(track)
    if kind == 'channel':
        track.extend([mido.Message('note_off', note=60), mido.Message('note_on', note=60, velocity=90)])
    else:
        track.extend([mido.MetaMessage('set_tempo', tempo=500000), mido.MetaMessage('set_tempo', tempo=400000)])
    a, b = tmp_path/'a.mid', tmp_path/'b.mid'
    mid.save(a)
    track.reverse()
    mid.save(b)
    assert not compare_smf(a, b)['exact_event_match']
