"""K5 offline acceptance: explainable structural scores and bounded retries."""

from copy import deepcopy

import pretty_midi
import pytest

from midivolt.part_quality import evaluate_part_structure
from midivolt.part_orchestrator import compose_strict_parts


def melody():
    midi = pretty_midi.PrettyMIDI(initial_tempo=60)
    track = pretty_midi.Instrument(73, name="Locked Flute")
    track.notes.append(pretty_midi.Note(85, 65, 0, 1))
    track.control_changes.append(pretty_midi.ControlChange(1, 30, 0))
    midi.instruments.append(track)
    return midi


def part(notes, *, program=0):
    track = pretty_midi.Instrument(program=program, name="New")
    for pitch, start, end in notes:
        track.notes.append(pretty_midi.Note(80, pitch, start, end))
    return track


def gen_midi(track):
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    midi.instruments.append(track)
    return midi


class SequenceProvider:
    name = "fake-sequence"

    def __init__(self, tracks):
        self.tracks = tracks
        self.calls = []

    def generate(self, prompt, *, tempo, seed=None):
        self.calls.append((prompt, tempo, seed))
        track = self.tracks[min(len(self.calls) - 1, len(self.tracks) - 1)]
        return gen_midi(deepcopy(track))


def test_clean_track_scores_one_and_has_no_warnings():
    metrics = evaluate_part_structure(
        melody(), part([(60, 0, 1), (64, 1, 2), (67, 2, 3)]), "piano"
    )
    assert metrics["score"] == 1.0
    assert metrics["warnings"] == []
    assert metrics["notes"] == 3
    assert metrics["metric_type"] == "symbolic_structure_only"


def test_exact_duplicates_score_below_default_threshold():
    notes = [(60, 0, 1)] * 4
    metrics = evaluate_part_structure(melody(), part(notes), "piano")
    assert metrics["duplicate_note_events"] == 3
    assert metrics["score"] < 0.75
    assert "duplicate_note_events" in metrics["warnings"]


def test_out_of_register_and_micro_events_are_reported_not_relabelled():
    metrics = evaluate_part_structure(
        melody(), part([(25, 0, 0.005), (60, 1, 1.5)], program=40), "violin"
    )
    assert metrics["out_of_register_notes"] == 1
    assert metrics["micro_duration_notes"] == 1
    assert "notes_outside_advisory_register" in metrics["warnings"]
    assert metrics["score"] < 1


def test_quality_retry_uses_next_seed_and_keeps_original_immutable():
    src = melody()
    original = deepcopy(src)
    repeated = part([(60, 0, 0.5)] * 4)
    clean = part([(60, 0, 0.5), (64, 0.5, 1.0)])
    provider = SequenceProvider([repeated, clean])
    midi, plan, review = compose_strict_parts(
        src, "鋼琴", provider, locked_tracks=(0,),
        seed=42, quality_retries=1, minimum_structure_score=0.75,
    )
    attempts = plan["quality_attempts"]
    assert [a["accepted"] for a in attempts] == [False, True]
    assert [a["seed"] for a in attempts] == [42, 43]
    assert attempts[0]["metrics"]["score"] < 0.75
    assert attempts[1]["metrics"]["score"] == 1.0
    assert plan["quality_policy"]["quality_retries"] == 1
    assert len(midi.instruments) == 2
    assert review["notes_added"] == 2 and review["notes_removed"] == 0
    assert len(src.instruments) == 1
    assert src.instruments[0].notes[0].end == original.instruments[0].notes[0].end
    assert src.instruments[0].control_changes[0].value == 30


def test_retries_exhaust_and_no_partial_result_is_returned():
    provider = SequenceProvider([part([(60, 0, 0.5)] * 4)])
    src = melody()
    with pytest.raises(ValueError, match="Rejected after 3 attempt"):
        compose_strict_parts(
            src, "鋼琴", provider, locked_tracks=(0,),
            seed=30, quality_retries=2, minimum_structure_score=0.75,
        )
    assert [c[2] for c in provider.calls] == [30, 31, 32]
    assert len(src.instruments) == 1


def test_wrong_gm_can_retry_without_forging_program_change():
    wrong = part([(60, 0, 0.5)], program=0)
    correct = part([(60, 0, 0.5)], program=40)
    provider = SequenceProvider([wrong, correct])
    result, plan, _ = compose_strict_parts(
        melody(), "小提琴", provider, locked_tracks=(0,),
        seed=21, quality_retries=1,
    )
    assert [a["accepted"] for a in plan["quality_attempts"]] == [False, True]
    assert "expected GM 40" in plan["quality_attempts"][0]["reason"]
    assert result.instruments[1].program == 40


def test_generator_crash_is_not_hidden_by_retries():
    class Crashes:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, *, tempo, seed=None):
            self.calls += 1
            raise RuntimeError("checkpoint corrupted")

    model = Crashes()
    with pytest.raises(RuntimeError, match="checkpoint corrupted"):
        compose_strict_parts(
            melody(), "鋼琴", model, locked_tracks=(0,),
            quality_retries=3,
        )
    assert model.calls == 1


@pytest.mark.parametrize("threshold,retries", [
    (float("nan"), 0), (float("inf"), 0), (-0.01, 0), (1.1, 0),
    (True, 0), (0.75, -1), (0.75, 4), (0.75, True),
])
def test_invalid_quality_policy_refuses_before_generation(threshold, retries):
    provider = SequenceProvider([part([(60, 0, 1)])])
    with pytest.raises(ValueError):
        compose_strict_parts(
            melody(), "鋼琴", provider, locked_tracks=(0,),
            minimum_structure_score=threshold, quality_retries=retries,
        )
    assert provider.calls == []


def test_max_seed_overflow_is_rejected_before_generation():
    provider = SequenceProvider([part([(60, 0, 1)])])
    with pytest.raises(ValueError, match="seeds"):
        compose_strict_parts(
            melody(), "鋼琴、小提琴", provider, locked_tracks=(0,),
            seed=2**31 - 3, quality_retries=1,
        )
    assert not provider.calls


def test_no_duplicate_track_publishing_when_second_role_fails():
    class Mixed:
        def __init__(self):
            self.calls = []

        def generate(self, prompt, *, tempo, seed=None):
            self.calls.append(prompt)
            if "Violin" in prompt:
                return gen_midi(part([(60, 0, 0.5)], program=0))
            return gen_midi(part([(60, 0, 0.5)], program=0))

    src = melody()
    generator = Mixed()
    with pytest.raises(ValueError, match="expected GM 40"):
        compose_strict_parts(
            src, "鋼琴、小提琴", generator,
            locked_tracks=(0,), quality_retries=1,
        )
    assert len(generator.calls) == 3
    assert len(src.instruments) == 1
