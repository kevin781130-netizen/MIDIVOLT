"""Conservative, explainable MIDI event-structure diagnostics.

This is NOT an aesthetic score, harmonic correctness score, or transcription
accuracy measurement. Only objective symbolic anomalies are considered.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite

import pretty_midi

# Advisory MIDI-note ranges, not absolute acoustic/instrument limits.
_REGISTER = {
    "bass": (28, 72),
    "piano": (21, 108),
    "guitar": (40, 88),
    "strings": (36, 103),
    "violin": (55, 103),
    "viola": (48, 96),
    "cello": (36, 84),
    "woodwinds": (45, 104),
    "flute": (60, 100),
    "oboe": (55, 95),
    "clarinet": (48, 100),
    "bassoon": (34, 88),
    "keys": (21, 108),
}


def evaluate_part_structure(
    source: pretty_midi.PrettyMIDI,
    track: pretty_midi.Instrument,
    role: str,
) -> dict:
    """Return a deterministic 0..1 structural score and interpretable metrics.

    Counts distinct note events using the source's beat/tick grid. No audio,
    model service, training data, network or dependencies beyond pretty_midi.
    Instrument ranges are advisory penalties, never direct pitch rejections.
    """
    if not isinstance(source, pretty_midi.PrettyMIDI):
        raise TypeError("source must be PrettyMIDI.")
    if not isinstance(track, pretty_midi.Instrument):
        raise TypeError("track must be a PrettyMIDI Instrument.")
    if role not in _REGISTER and role != "drums":
        raise ValueError(f"Unsupported scoring role: {role}.")
    if not track.notes:
        raise ValueError("Cannot score an empty MIDI part.")

    resolution = source.resolution
    events = []
    micro = 0
    off_register = 0
    lo, hi = _REGISTER.get(role, (35, 81))
    for note in track.notes:
        if not all(isfinite(v) for v in (note.start, note.end)) or note.end <= note.start:
            raise ValueError("Invalid generated note duration.")
        start = int(source.time_to_tick(note.start))
        end = int(source.time_to_tick(note.end))
        if end <= start:
            raise ValueError("Invalid or collapsed generated MIDI note.")
        events.append((int(note.pitch), start, end))
        micro += (end - start) / resolution < (1.0 / 64.0)
        off_register += not (lo <= note.pitch <= hi)
    count = len(events)
    duplicates = sum(n - 1 for n in Counter(events).values())
    duration_beats = max(1.0, (max(t for _, _, t in events) -
                               min(t for _, t, _ in events)) / resolution)
    per_beat = count / duration_beats

    duplicate_ratio = duplicates / count
    range_ratio = 0.0 if role == "drums" else off_register / count
    micro_ratio = micro / count
    density_excess = min(1.0, max(0.0, (per_beat - 12.0) / 12.0))
    score = max(0.0, 1.0 - (
        0.55 * duplicate_ratio + 0.35 * range_ratio +
        0.20 * micro_ratio + 0.25 * density_excess
    ))
    warnings = []
    if duplicates:
        warnings.append("duplicate_note_events")
    if off_register and role != "drums":
        warnings.append("notes_outside_advisory_register")
    if micro:
        warnings.append("micro_duration_notes")
    if per_beat > 12.0:
        warnings.append("dense_midi_events")
    return {
        "score": round(score, 4),
        "notes": count,
        "duplicate_note_events": duplicates,
        "out_of_register_notes": 0 if role == "drums" else off_register,
        "micro_duration_notes": micro,
        "notes_per_beat": round(per_beat, 3),
        "warnings": warnings,
        "metric_type": "symbolic_structure_only",
    }
