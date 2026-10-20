"""MIDI serialization tests that do not require optional AI/music21 modules."""

import pretty_midi
import pytest

from midivolt.io import read_midi, write_midi


def example_midi():
    midi = pretty_midi.PrettyMIDI(initial_tempo=70)
    lead = pretty_midi.Instrument(program=73, name="Synth flute")
    lead.notes.append(pretty_midi.Note(velocity=87, pitch=69, start=0, end=0.75))
    midi.instruments.append(lead)
    return midi


def test_real_midi_round_trip_and_existing_file_protection(tmp_path):
    source = example_midi()
    path = tmp_path / "song.mid"
    assert write_midi(source, path) == path
    restored = read_midi(path)
    assert restored.instruments[0].name == "Synth flute"
    assert restored.instruments[0].notes[0].pitch == 69
    data = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_midi(source, path)
    assert path.read_bytes() == data
    assert write_midi(source, path, overwrite=True) == path
    assert list(tmp_path.iterdir()) == [path]


def test_partial_serialization_cannot_damage_original(tmp_path):
    path = tmp_path / "safe.mid"
    write_midi(example_midi(), path)
    original_bytes = path.read_bytes()

    class FailingWriter:
        def write(self, candidate):
            from pathlib import Path
            Path(candidate).write_bytes(b"garbage partial MIDI")
            raise RuntimeError("disk write interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        write_midi(FailingWriter(), path, overwrite=True)
    assert path.read_bytes() == original_bytes
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_creation_cannot_get_overwritten(tmp_path):
    path = tmp_path / "song.mid"

    class ConcurrentWriter:
        def write(self, candidate):
            from pathlib import Path
            Path(candidate).write_bytes(b"fresh")
            path.write_bytes(b"another process created this file")

    with pytest.raises(FileExistsError, match="Refusing"):
        write_midi(ConcurrentWriter(), path)
    assert path.read_bytes() == b"another process created this file"
    assert list(tmp_path.iterdir()) == [path]


def test_bad_output_path_never_writes(tmp_path):
    with pytest.raises(ValueError):
        write_midi(example_midi(), tmp_path / "song.wav")
    with pytest.raises(FileNotFoundError):
        write_midi(example_midi(), tmp_path / "missing" / "song.mid")
