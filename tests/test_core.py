"""Functional tests for commercially safe first-slice MIDI operations."""

from pathlib import Path

import pretty_midi
import pytest

from midivolt.arrange import add_accompaniment
from midivolt.cli import main
from midivolt.io import read_midi, write_midi
from midivolt.theory import estimate_key, parse_chords


def melody_source() -> pretty_midi.PrettyMIDI:
    midi = pretty_midi.PrettyMIDI(initial_tempo=70)
    melody = pretty_midi.Instrument(program=73, name="Locked flute")
    for i, pitch in enumerate((65, 69, 72, 69)):
        melody.notes.append(pretty_midi.Note(90, pitch, i * 0.8, (i + 1) * 0.8))
    midi.instruments.append(melody)
    return midi


def test_chords_parse_including_slash_bass():
    specs = parse_chords("Fmaj7 Dm7 Gm7 C7 C/E")
    assert len(specs) == 5
    assert specs[0].root_pc == 5
    assert set(specs[0].intervals) == {0, 4, 7, 11}
    assert specs[-1].bass_pc == 4


@pytest.mark.parametrize("chords", ["", "blahZ", "Fmaj7 " * 129])
def test_reject_invalid_progression(chords):
    with pytest.raises(ValueError):
        parse_chords(chords)


def test_arrangement_preserves_existing_melody_and_tempo(tmp_path):
    original = melody_source()
    original_events = [(n.pitch, n.start, n.end, n.velocity) for n in original.instruments[0].notes]
    result = add_accompaniment(original, "Fmaj7 Dm7 Gm7 C7")
    assert len(original.instruments) == 1
    assert len(result.instruments) == 3
    assert [(n.pitch, n.start, n.end, n.velocity) for n in result.instruments[0].notes] == original_events
    assert result.instruments[1].name == "MIDIVOLT Chords"
    assert len(result.instruments[1].notes) == 16
    assert len(result.instruments[2].notes) == 4
    assert result.get_tempo_changes()[1].tolist() == original.get_tempo_changes()[1].tolist()

    path = tmp_path / "arranged.mid"
    write_midi(result, path)
    reloaded = read_midi(path)
    assert len(reloaded.instruments) == 3
    assert len(reloaded.instruments[1].notes) == 16
    with pytest.raises(FileExistsError):
        write_midi(result, path)
    write_midi(result, path, overwrite=True)


def test_bad_timing_rejected():
    with pytest.raises(ValueError):
        add_accompaniment(melody_source(), "C", beats_per_chord=0)
    with pytest.raises(ValueError):
        add_accompaniment(melody_source(), "C", start_beat=-1)


def test_cli_create_analyze_arrange(tmp_path, capsys):
    demo = tmp_path / "demo.mid"
    arranged = tmp_path / "arranged.mid"
    assert main(["create", "--chords", "Fmaj7 Dm7 Gm7 C7", "--bpm", "70", "--out", str(demo)]) == 0
    assert demo.is_file()
    assert main(["analyze", "--input", str(demo)]) == 0
    assert '"tracks"' in capsys.readouterr().out
    assert main(["arrange", "--input", str(demo), "--chords", "C7", "--out", str(arranged)]) == 0
    assert len(read_midi(arranged).instruments) == 4
    assert main(["create", "--chords", "C", "--out", str(demo)]) == 2


def test_key_estimate_no_drums_or_short_phrase():
    midi = pretty_midi.PrettyMIDI()
    assert estimate_key(midi) is None
    drums = pretty_midi.Instrument(program=0, is_drum=True)
    drums.notes.append(pretty_midi.Note(100, 36, 0, 1))
    midi.instruments.append(drums)
    assert estimate_key(midi) is None
