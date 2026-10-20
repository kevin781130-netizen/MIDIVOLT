"""Non-destructive MIDI accompaniment generation."""

from __future__ import annotations

from copy import deepcopy
from math import isfinite

import pretty_midi

from .theory import parse_chords


def add_accompaniment(
    original: pretty_midi.PrettyMIDI,
    progression: str,
    *,
    beats_per_chord: float = 4.0,
    velocity: int = 78,
    add_bass: bool = True,
    start_beat: float = 0.0,
) -> pretty_midi.PrettyMIDI:
    """Deep-copy a MIDI object and add non-destructive chord/bass tracks.

    Beats are quarter-note units; tick-to-time uses the original tempo map.
    Existing notes, instruments and tempo events are not modified.
    """
    if not isfinite(beats_per_chord) or beats_per_chord <= 0:
        raise ValueError("beats_per_chord must be a finite positive number.")
    if not isfinite(start_beat) or start_beat < 0:
        raise ValueError("start_beat must be finite and nonnegative.")
    if not isinstance(velocity, int) or not 1 <= velocity <= 127:
        raise ValueError("velocity must be an integer from 1 to 127.")

    symbols = parse_chords(progression)
    result = deepcopy(original)
    chords = pretty_midi.Instrument(program=0, name="MIDIVOLT Chords")
    bass = pretty_midi.Instrument(program=32, name="MIDIVOLT Bass")

    for i, symbol in enumerate(symbols):
        first_tick = round((start_beat + i * beats_per_chord) * result.resolution)
        last_tick = round((start_beat + (i + 1) * beats_per_chord) * result.resolution)
        if last_tick <= first_tick:
            raise ValueError("Chord duration rounds to zero MIDI ticks.")
        start = result.tick_to_time(first_tick)
        end = result.tick_to_time(last_tick)
        if end <= start:
            raise ValueError("Chord timing must increase strictly.")
        # Root-position chord around octave 4; avoid out-of-range notes.
        root_pitch = 60 + symbol.root_pc
        for semitones in symbol.intervals:
            pitch = root_pitch + semitones
            if not 0 <= pitch <= 127:
                raise ValueError("Accompaniment pitch outside MIDI range.")
            chords.notes.append(
                pretty_midi.Note(velocity=velocity, pitch=pitch, start=start, end=end)
            )
        if add_bass:
            bass.notes.append(
                pretty_midi.Note(
                    velocity=max(1, velocity - 6),
                    pitch=36 + symbol.bass_pc,
                    start=start,
                    end=end,
                )
            )

    result.instruments.append(chords)
    if add_bass:
        result.instruments.append(bass)
    return result
