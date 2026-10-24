"""Offline acceptance tests: provider boundary, tempo mapping, and track locks."""

from copy import deepcopy

import pretty_midi
import pytest

from midivolt.composition_engine import CompositionRequest, compose_candidate


class FakeGenerator:
    name = "fixture-only"

    def __init__(self, payload=None):
        self.payload = payload
        self.calls = []

    def generate(self, prompt, *, tempo, seed=None):
        self.calls.append((prompt, tempo, seed))
        if self.payload is not None:
            return self.payload
        midi = pretty_midi.PrettyMIDI(initial_tempo=120)
        piano = pretty_midi.Instrument(program=0, name="Piano")
        piano.notes.append(pretty_midi.Note(86, 60, 0.0, 0.5))
        piano.control_changes.append(pretty_midi.ControlChange(64, 127, 0.5))
        bass = pretty_midi.Instrument(program=32, name="Bass")
        bass.notes.append(pretty_midi.Note(75, 36, 0.0, 0.5))
        midi.instruments.extend((piano, bass))
        return midi


def melody():
    midi = pretty_midi.PrettyMIDI(initial_tempo=60)
    flute = pretty_midi.Instrument(program=73, name="Locked Melody")
    flute.notes.append(pretty_midi.Note(95, 69, 0, 1))
    flute.pitch_bends.append(pretty_midi.PitchBend(100, 0.2))
    midi.instruments.append(flute)
    return midi


def test_appends_multitrack_and_maps_beats_to_original_tempo():
    original = melody()
    snapshot = deepcopy(original)
    provider = FakeGenerator()
    candidate, review = compose_candidate(
        original, provider,
        CompositionRequest("  Add piano and bass  ", locked_tracks=(0,), seed=42),
    )
    assert provider.calls == [("Add piano and bass", 60.0, 42)]
    assert [i.name for i in candidate.instruments] == ["Locked Melody", "Piano", "Bass"]
    assert len(original.instruments) == 1
    assert original.instruments[0].notes[0].end == snapshot.instruments[0].notes[0].end
    assert original.instruments[0].pitch_bends[0].pitch == 100
    assert candidate.instruments[0].pitch_bends[0].pitch == 100
    assert candidate.instruments[1].notes[0].end == pytest.approx(1.0, abs=0.002)
    assert candidate.instruments[1].control_changes[0].time == pytest.approx(1.0, abs=0.002)
    assert candidate.get_tempo_changes()[1].tolist() == [60.0]
    assert review["notes_added"] == 2
    assert review["notes_removed"] == 0
    assert review["locked_tracks"] == [0]


@pytest.mark.parametrize("prompt,locks", [
    ("", (0,)), ("ok", ()), ("ok", (1,)), ("ok", (0, 0)),
])
def test_invalid_plan_rejected_before_generator_runs(prompt, locks):
    provider = FakeGenerator()
    with pytest.raises(ValueError):
        compose_candidate(melody(), provider, CompositionRequest(prompt, locked_tracks=locks))
    assert not provider.calls


def test_empty_model_output_is_rejected():
    empty = pretty_midi.PrettyMIDI()
    empty.instruments.append(pretty_midi.Instrument(0, name="Empty"))
    with pytest.raises(ValueError, match="no notes"):
        compose_candidate(melody(), FakeGenerator(empty), CompositionRequest("Write", (0,)))


def test_invalid_or_collapsed_note_is_rejected():
    payload = pretty_midi.PrettyMIDI(initial_tempo=120)
    part = pretty_midi.Instrument(program=0, name="Piano")
    part.notes.append(pretty_midi.Note(80, 60, 0, 0.000001))
    payload.instruments.append(part)
    with pytest.raises(ValueError, match="collapsed"):
        compose_candidate(melody(), FakeGenerator(payload), CompositionRequest("Write", (0,)))


def test_track_and_note_budgets_are_enforced():
    payload = FakeGenerator().generate("x", tempo=60)
    with pytest.raises(ValueError, match="number of new tracks"):
        compose_candidate(melody(), FakeGenerator(payload), CompositionRequest("Write", (0,), max_new_tracks=1))
    with pytest.raises(ValueError, match="notes/automation"):
        compose_candidate(melody(), FakeGenerator(payload), CompositionRequest("Write", (0,), max_new_notes=1))


def test_no_provider_weights_or_network_are_needed():
    candidate, _ = compose_candidate(melody(), FakeGenerator(), CompositionRequest("Demo", (0,)))
    assert len(candidate.instruments) == 3


def test_real_midi_roundtrip_accepts_numpy_integer_program(tmp_path):
    """Regression: pretty_midi parses GM program-change values as numpy.int64."""
    generated = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0, name="AI piano")
    piano.notes.append(pretty_midi.Note(90, 60, 0, 0.5))
    generated.instruments.append(piano)
    output = tmp_path / "generated.mid"
    generated.write(str(output))
    loaded = pretty_midi.PrettyMIDI(str(output))
    from numbers import Integral
    assert isinstance(loaded.instruments[0].program, Integral)
    assert type(loaded.instruments[0].program) is not int  # NumPy scalar on real read
    candidate, diff = compose_candidate(
        melody(), FakeGenerator(loaded),
        CompositionRequest("Add piano", locked_tracks=(0,)),
    )
    assert [track.program for track in candidate.instruments] == [73, 0]
    assert diff["notes_added"] == 1
    assert diff["notes_removed"] == 0


def test_boolean_program_still_rejected():
    """bool is an Integral subclass but not a valid program number type."""
    raw = FakeGenerator().generate("test", tempo=120)
    raw.instruments[0].program = True
    with pytest.raises(ValueError, match="invalid MIDI program"):
        compose_candidate(
            melody(), FakeGenerator(raw),
            CompositionRequest("Add piano", locked_tracks=(0,)),
        )
