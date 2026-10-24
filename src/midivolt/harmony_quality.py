"""Optional, explicit-context harmony diagnostics for MIDI candidate tracks.

No inferred key, no claim of musicological correctness. Non-chord tones, jazz
extensions, passing notes and dissonances can be intentional; diagnostics
are advisory unless the caller opts into a separate minimum-score gate.
"""
from __future__ import annotations

from math import isfinite
import re

import pretty_midi

_KEY = re.compile(r"^([A-Ga-g])([#b]?)[ ]+(major|minor)$", re.IGNORECASE)
_ROOT = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),  # natural minor only
}


def prepare_harmonic_context(
    *, key: str | None = None, chords: str | None = None,
    beats_per_chord: float = 4.0,
) -> dict | None:
    """Validate all user-declared harmony *before* model execution.

    Chord parsing delegates to MIDIVOLT's existing music21-backed grammar.
    Progressions begin on beat zero, last beats_per_chord each and NEVER
    wrap/loop without explicit instruction.
    """
    if type(beats_per_chord) not in (int, float) or not isfinite(beats_per_chord) or not 0.25 <= beats_per_chord <= 64:
        raise ValueError("beats_per_chord must be finite in 0.25..64.")
    if key is None and chords is None:
        return None
    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise ValueError("key must be e.g. 'C major' or 'A minor'.")
    if chords is not None and (not isinstance(chords, str) or not chords.strip()):
        raise ValueError("chords must be explicit lead-sheet chord symbols.")

    pitch_classes = None
    if key is not None:
        m = _KEY.fullmatch(key.strip())
        if not m:
            raise ValueError("Use an explicit key, e.g. 'C major' or 'F# minor'.")
        root = (_ROOT[m[1].upper()] + (1 if m[2] == "#" else -1 if m[2] == "b" else 0)) % 12
        pitch_classes = tuple(sorted((root + interval) % 12 for interval in _SCALES[m[3].lower()]))

    resolved = []
    if chords is not None:
        # Keep this a lazy import so key-only validation does not require
        # initializing the heavy music21 parser.
        from .theory import parse_chords

        for chord in parse_chords(chords):
            resolved.append({
                "symbol": chord.symbol,
                "pitches": tuple(sorted((chord.root_pc + d) % 12 for d in chord.intervals)),
            })
    return {
        "key": key.strip() if key is not None else None,
        "scale_pitch_classes": pitch_classes,
        "chords": resolved,
        "beats_per_chord": float(beats_per_chord),
    }


def evaluate_part_harmony(
    source: pretty_midi.PrettyMIDI,
    track: pretty_midi.Instrument,
    role: str,
    context: dict,
    *,
    reference_tracks: tuple[int, ...] = (),
) -> dict:
    """Return explainable symbolic tonal diagnostics, not an aesthetic score.

    Harmony events are compared at note *onset* in source quarter-note beats;
    tie/anticipation/passing-tone handling is intentionally conservative.
    Notes beyond the supplied chord progression are unscored for chords.
    Simultaneous semitone conflicts against reference tracks are advisory.
    """
    if not isinstance(source, pretty_midi.PrettyMIDI) or not isinstance(track, pretty_midi.Instrument):
        raise TypeError("Expected source PrettyMIDI and generated Instrument.")
    if not isinstance(context, dict) or "beats_per_chord" not in context:
        raise ValueError("Explicit validated harmonic context is required.")
    if type(reference_tracks) is not tuple or any(type(i) is not int or i < 0 or i >= len(source.instruments) for i in reference_tracks):
        raise ValueError("Invalid reference track indices.")
    if not track.notes:
        raise ValueError("Cannot evaluate harmony for empty track.")

    if role == "drums" or track.is_drum:
        return {"metric_type": "symbolic_harmony_advisory", "status": "not_applicable",
                "score": None, "warnings": [], "notes": len(track.notes)}

    beat_unit = source.resolution
    notes = sorted(track.notes, key=lambda n: (n.start, n.pitch, n.end))
    chord_events = context["chords"]
    scale = context["scale_pitch_classes"]
    span = context["beats_per_chord"]
    n_off_scale = 0
    chord_evaluated = 0
    strong_chord_misses = 0
    passing_notes = 0
    uncovered = 0
    melodic_leaps = 0
    leap_pairs = 0
    previous = None
    dissonant_onsets = 0

    references = [
        note
        for i in reference_tracks
        for note in source.instruments[i].notes
        if not source.instruments[i].is_drum
    ]
    # Avoid quadratic blowup for long references by bounding the comparisons.
    # This is a diagnostic, not a complete voice-leading solver.
    compare_reference = len(references) * len(notes) <= 250000

    for current in notes:
        if not all(isfinite(v) for v in (current.start, current.end)) or current.end <= current.start:
            raise ValueError("Generated notes must have valid durations.")
        start_beat = source.time_to_tick(current.start) / beat_unit
        duration_beats = (source.time_to_tick(current.end) -
                          source.time_to_tick(current.start)) / beat_unit
        if scale is not None and current.pitch % 12 not in scale:
            n_off_scale += 1

        is_passing = (
            previous is not None and current.start >= previous.end
            and abs(current.pitch - previous.pitch) <= 2
            and duration_beats <= 0.5
        )
        if is_passing:
            passing_notes += 1

        if chord_events:
            slot = int((start_beat + 1e-7) // span)
            if 0 <= slot < len(chord_events):
                chord_evaluated += 1
                # Penalize only sustained/strong-beat dissonances. Passing
                # notes and chord extensions are not automatically incorrect.
                on_strong_beat = (start_beat % span) < 0.125
                if (current.pitch % 12 not in chord_events[slot]["pitches"] and
                        on_strong_beat and duration_beats > 0.5 and not is_passing):
                    strong_chord_misses += 1
            else:
                uncovered += 1

        if previous is not None and current.start >= previous.end:
            leap_pairs += 1
            if abs(current.pitch - previous.pitch) > 12:
                melodic_leaps += 1

        if compare_reference and any(
            reference.start < current.end and reference.end > current.start
            and abs(reference.pitch - current.pitch) % 12 in (1, 11)
            and min(reference.end, current.end) - max(reference.start, current.start) >= 0.25
            for reference in references
        ):
            dissonant_onsets += 1
        previous = current

    n = len(notes)
    # Major/minor borrowed chords, alterations, appoggiaturas, tritones and
    # intentional tension are possible: this is only a conservative heuristic.
    off_scale_ratio = n_off_scale / n if scale is not None else 0.0
    nonchord_ratio = strong_chord_misses / chord_evaluated if chord_evaluated else 0.0
    leap_ratio = melodic_leaps / leap_pairs if leap_pairs else 0.0
    score = max(0.0, 1.0 - 0.35 * off_scale_ratio -
                0.50 * nonchord_ratio - 0.10 * leap_ratio)
    warnings = []
    if n_off_scale:
        warnings.append("notes_outside_declared_scale")
    if strong_chord_misses:
        warnings.append("sustained_nonchord_notes_on_strong_beats")
    if melodic_leaps:
        warnings.append("large_melodic_leaps")
    if dissonant_onsets:
        warnings.append("simultaneous_semitone_against_locked_reference")
    if uncovered:
        warnings.append("notes_beyond_supplied_chord_progression")
    if not compare_reference:
        warnings.append("reference_overlap_analysis_skipped_due_to_size")

    return {
        "metric_type": "symbolic_harmony_advisory",
        "status": "evaluated",
        "score": round(score, 4),
        "notes": n,
        "out_of_scale_notes": n_off_scale,
        "strong_beat_nonchord_notes": strong_chord_misses,
        "chord_evaluated_notes": chord_evaluated,
        "notes_without_chord_context": uncovered,
        "possible_passing_notes": passing_notes,
        "melodic_leaps_over_octave": melodic_leaps,
        "simultaneous_semitone_events": dissonant_onsets,
        "warnings": warnings,
    }
