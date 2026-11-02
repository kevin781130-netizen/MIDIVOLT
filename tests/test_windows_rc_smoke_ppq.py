"""Regress an actual Windows RC smoke fail caused by 220->480 PPQ quantization."""
from pathlib import Path

import mido
import pretty_midi
import pytest

from midivolt.cubase_smf import prepare_smf, compare_smf
from midivolt.prompt_music import parse_prompt, generate_sketch

ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_smoke_uses_actual_approved_midi_ppq():
    source = (ROOT / "packaging/windows/Smoke-MIDIVOLT.ps1").read_text(encoding="utf-8")
    assert 'mido.MidiFile(sys.argv[1]).ticks_per_beat' in source
    assert '"--ppq", "$sourcePpq"' in source
    assert '"--ppq", "480"' not in source
    assert 'Could not determine the approved MIDI PPQ' in source
    assert 'outside the supported 24..960 range' in source


@pytest.mark.parametrize('resolution', [220, 480, 960])
def test_real_midi_strict_compare_is_lossless_when_ppq_unchanged(tmp_path, resolution):
    spec = parse_prompt('C major 2 bars full arrangement 120 BPM', bars=2, seed=42)
    midi = generate_sketch(spec)
    if resolution != midi.resolution:
        # Reconstruct the same genuine generated MIDI in a new resolution.
        changed = pretty_midi.PrettyMIDI(initial_tempo=120, resolution=resolution)
        changed.instruments = midi.instruments
        midi = changed
    source = tmp_path / 'approved.mid'
    converted = tmp_path / 'cubase-type1.mid'
    midi.write(str(source))
    source_ppq = mido.MidiFile(str(source)).ticks_per_beat
    assert source_ppq == resolution
    result = prepare_smf(source, converted, ppq=source_ppq)
    proof = compare_smf(source, converted)
    assert result['type'] == 1
    assert result['ppq_export'] == source_ppq
    assert proof['exact_event_match'] is True
    assert proof['missing_events'] == proof['added_events'] == 0


def test_fixed_480_ppq_can_break_strict_event_match_for_actual_product_midi(tmp_path):
    src = tmp_path / 'generated.mid'
    dst = tmp_path / 'forced480.mid'
    generate_sketch(parse_prompt('C major 2 bars full arrangement', bars=2, seed=42)).write(str(src))
    assert mido.MidiFile(str(src)).ticks_per_beat == 220
    prepare_smf(src, dst, ppq=480)
    proof = compare_smf(src, dst)
    assert proof['exact_event_match'] is False
    assert proof['missing_events'] > 0 and proof['added_events'] > 0
