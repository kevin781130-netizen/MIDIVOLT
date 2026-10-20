"""Interchange tests (do not require Sawdust or tsov installed)."""

import pretty_midi
import pytest

from midivolt.bridges import prepare_bridge


def _sample(path):
    midi = pretty_midi.PrettyMIDI(initial_tempo=70)
    track = pretty_midi.Instrument(program=73, name="Flute")
    track.notes.append(pretty_midi.Note(90, 69, 0.22, 0.91))
    midi.instruments.append(track)
    midi.write(str(path))


def test_tsov_bridge_preserves_source_and_notes(tmp_path):
    source = tmp_path / "source.mid"
    _sample(source)
    before = source.read_bytes()
    result = prepare_bridge(source, tmp_path / "tsov.mid", "tsov")
    output = pretty_midi.PrettyMIDI(str(result.output))
    assert result.notes == 1
    assert output.instruments[0].notes[0].pitch == 69
    assert source.read_bytes() == before


def test_sawdust_quantize_is_opt_in(tmp_path):
    source = tmp_path / "source.mid"
    _sample(source)
    raw = prepare_bridge(source, tmp_path / "normal.mid", "sawdust")
    grid = prepare_bridge(
        source, tmp_path / "quantized.mid", "sawdust", quantize=True
    )
    original = pretty_midi.PrettyMIDI(str(raw.output)).instruments[0].notes[0]
    snapped = pretty_midi.PrettyMIDI(str(grid.output)).instruments[0].notes[0]
    assert raw.quantized_notes == 0
    assert grid.quantized_notes == 1
    assert snapped.start != original.start
    assert (snapped.pitch, snapped.velocity) == (original.pitch, original.velocity)


def test_same_file_forbidden_even_when_overwriting(tmp_path):
    source = tmp_path / "source.mid"
    _sample(source)
    with pytest.raises(ValueError):
        prepare_bridge(source, source, "tsov", overwrite=True)


def test_output_protection_and_validation(tmp_path):
    source = tmp_path / "source.mid"
    _sample(source)
    destination = tmp_path / "out.mid"
    prepare_bridge(source, destination, "tsov")
    with pytest.raises(FileExistsError):
        prepare_bridge(source, destination, "tsov")
    with pytest.raises(ValueError):
        prepare_bridge(source, tmp_path / "bad.mid", "not-a-target")
    with pytest.raises(ValueError):
        prepare_bridge(source, tmp_path / "bad.mid", "tsov", quantize=True)


def test_sawdust_warnings_for_excess_channels(tmp_path):
    source = tmp_path / "source.mid"
    midi = pretty_midi.PrettyMIDI()
    for n in range(16):
        track = pretty_midi.Instrument(program=n)
        track.notes.append(pretty_midi.Note(75, 60+n, n, n+0.25))
        midi.instruments.append(track)
    midi.write(str(source))
    result = prepare_bridge(source, tmp_path / "out.mid", "sawdust")
    assert any("15 pitched" in s for s in result.warnings)
