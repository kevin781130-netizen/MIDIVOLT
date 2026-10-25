"""K6 deterministic harmony diagnostics: explicit context, safe optional gating."""

from copy import deepcopy

import pretty_midi
import pytest

from midivolt.harmony_quality import prepare_harmonic_context, evaluate_part_harmony
from midivolt.part_orchestrator import compose_strict_parts


def source():
    m = pretty_midi.PrettyMIDI(initial_tempo=60)
    flute = pretty_midi.Instrument(program=73, name="Locked melody")
    flute.notes.append(pretty_midi.Note(88, 60, 0, 1))
    flute.control_changes.append(pretty_midi.ControlChange(1, 40, 0))
    m.instruments.append(flute)
    return m


def instrument(notes, *, program=0, drum=False):
    t = pretty_midi.Instrument(program=program, name="Candidate", is_drum=drum)
    for pitch, start, end in notes:
        t.notes.append(pretty_midi.Note(80, pitch, start, end))
    return t


def midi(track):
    m = pretty_midi.PrettyMIDI(initial_tempo=120)
    m.instruments.append(track)
    return m


class SequenceProvider:
    def __init__(self, tracks):
        self.tracks = tracks
        self.calls = []

    def generate(self, prompt, *, tempo, seed=None):
        self.calls.append((prompt, tempo, seed))
        return midi(deepcopy(self.tracks[min(len(self.calls)-1, len(self.tracks)-1)]))


def test_explicit_key_major_minor_flats_and_sharps():
    assert 1 in prepare_harmonic_context(key="D major")["scale_pitch_classes"]
    assert 10 in prepare_harmonic_context(key="Bb major")["scale_pitch_classes"]
    assert 8 in prepare_harmonic_context(key="F# minor")["scale_pitch_classes"]
    context = prepare_harmonic_context(key="C major")
    result = evaluate_part_harmony(source(), instrument([(60, 0, 1), (64, 1, 2)]), "piano", context)
    assert result["score"] == 1.0
    assert result["out_of_scale_notes"] == 0
    assert result["metric_type"] == "symbolic_harmony_advisory"


def test_sustained_nonchord_on_strong_beat_is_distinguished_from_short_tension():
    ctx = prepare_harmonic_context(chords="Cmaj7 Dm7", beats_per_chord=4)
    good = evaluate_part_harmony(
        source(), instrument([(60, 0, 1), (62, 4, 5)]), "piano", ctx)
    bad = evaluate_part_harmony(
        source(), instrument([(66, 0, 1), (62, 4, 5)]), "piano", ctx)
    assert good["strong_beat_nonchord_notes"] == 0
    assert bad["strong_beat_nonchord_notes"] == 1
    assert bad["score"] < good["score"]
    short_tension = evaluate_part_harmony(
        source(), instrument([(66, 0, 0.25)]), "piano", ctx)
    assert short_tension["strong_beat_nonchord_notes"] == 0


def test_chord_progression_never_silently_loops():
    ctx = prepare_harmonic_context(chords="Cmaj7", beats_per_chord=4)
    result = evaluate_part_harmony(
        source(), instrument([(60, 0, 1), (60, 4, 5)]), "piano", ctx)
    assert result["chord_evaluated_notes"] == 1
    assert result["notes_without_chord_context"] == 1
    assert "notes_beyond_supplied_chord_progression" in result["warnings"]


def test_dissonance_and_leaps_are_advisory_only():
    # The source melody is C4. C#4 is semitone dissonant but can be intended.
    ctx = prepare_harmonic_context(key="C major")
    result = evaluate_part_harmony(
        source(), instrument([(61, 0, 1), (82, 1, 2)]),
        "piano", ctx, reference_tracks=(0,))
    assert result["simultaneous_semitone_events"] == 1
    assert result["melodic_leaps_over_octave"] == 1
    assert "simultaneous_semitone_against_locked_reference" in result["warnings"]


def test_drums_skip_pitch_harmony_even_with_explicit_key():
    ctx = prepare_harmonic_context(key="C major")
    result = evaluate_part_harmony(
        source(), instrument([(36, 0, 1)], drum=True),
        "drums", ctx, reference_tracks=(0,))
    assert result["score"] is None and result["status"] == "not_applicable"


def test_default_uses_advisory_mode_without_rejecting_tension():
    provider = SequenceProvider([instrument([(66, 0, 0.5)])])
    new, plan, report = compose_strict_parts(
        source(), "鋼琴", provider, locked_tracks=(0,),
        harmonic_key="C major", quality_retries=0,
    )
    assert len(new.instruments) == 2 and report["notes_added"] == 1
    assert plan["quality_attempts"][0]["accepted"]
    assert plan["quality_attempts"][0]["harmony_metrics"]["out_of_scale_notes"] == 1
    assert not plan["quality_policy"]["harmony_gating_enabled"]


def test_optional_gate_retries_when_declared_key_mismatches():
    bad = instrument([(66, 0, 0.5)])
    good = instrument([(60, 0, 0.5)])
    src = source()
    before = deepcopy(src)
    provider = SequenceProvider([bad, good])
    new, plan, diff = compose_strict_parts(
        src, "鋼琴", provider, locked_tracks=(0,), harmonic_key="C major",
        minimum_harmony_score=0.85, quality_retries=1, seed=13,
    )
    assert [a["accepted"] for a in plan["quality_attempts"]] == [False, True]
    assert [a["seed"] for a in plan["quality_attempts"]] == [13, 14]
    assert plan["quality_attempts"][0]["harmony_metrics"]["score"] < 0.85
    assert plan["quality_attempts"][1]["harmony_metrics"]["score"] == 1.0
    assert plan["quality_policy"]["harmony_gating_enabled"]
    assert diff["notes_added"] == 1
    assert len(src.instruments) == 1
    assert src.instruments[0].control_changes[0].value == before.instruments[0].control_changes[0].value


def test_failed_gate_never_yields_partial_midi():
    provider = SequenceProvider([instrument([(66, 0, 0.5)])])
    src = source()
    with pytest.raises(ValueError, match="symbolic harmony score"):
        compose_strict_parts(
            src, "鋼琴", provider, locked_tracks=(0,),
            harmonic_key="C major", minimum_harmony_score=0.90,
            quality_retries=1, seed=4,
        )
    assert len(provider.calls) == 2
    assert len(src.instruments) == 1


@pytest.mark.parametrize("key,chords,span,minimum", [
    ("C locrian", None, 4, None),
    ("H major", None, 4, None),
    ("C major", None, float("nan"), None),
    ("C major", None, 0, None),
    (None, None, 4, 0.5),
    ("C major", None, 4, 1.5),
    ("C major", None, 4, float("inf")),
])
def test_preflight_rejects_invalid_context_without_calling_model(key, chords, span, minimum):
    provider = SequenceProvider([instrument([(60, 0, 0.5)])])
    with pytest.raises(ValueError):
        compose_strict_parts(
            source(), "鋼琴", provider, locked_tracks=(0,),
            harmonic_key=key, harmonic_chords=chords, beats_per_chord=span,
            minimum_harmony_score=minimum,
        )
    assert not provider.calls
