"""Symbolic music analysis built on the BSD-licensed music21 library."""

from __future__ import annotations

from dataclasses import dataclass

import pretty_midi
from music21 import harmony, note, stream


@dataclass(frozen=True)
class ChordSpec:
    symbol: str
    root_pc: int
    bass_pc: int
    intervals: tuple[int, ...]


def parse_chords(progression: str) -> list[ChordSpec]:
    """Parse whitespace/comma-separated lead-sheet symbols, e.g. Fmaj7 Dm7 Gm7 C7."""
    tokens = progression.replace(",", " ").split()
    if not 1 <= len(tokens) <= 128:
        raise ValueError("Provide between 1 and 128 chord symbols.")
    result: list[ChordSpec] = []
    for token in tokens:
        try:
            symbol = harmony.ChordSymbol(token)
            pitches = symbol.pitches
            if not pitches or symbol.root() is None or symbol.bass() is None:
                raise ValueError("Unrecognized chord")
            root_pc = symbol.root().pitchClass
            bass_pc = symbol.bass().pitchClass
            intervals = tuple(sorted({(p.pitchClass - root_pc) % 12 for p in pitches}))
            if not intervals:
                raise ValueError("Chord has no pitches")
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            raise ValueError(f"Invalid chord symbol: {token!r}") from exc
        result.append(ChordSpec(token, root_pc, bass_pc, intervals))
    return result


def estimate_key(midi: pretty_midi.PrettyMIDI) -> str | None:
    """Return a best-effort key label; omit drums and very short phrases."""
    pitched = [
        n for inst in midi.instruments if not inst.is_drum for n in inst.notes
        if 0 <= n.pitch <= 127 and n.end > n.start
    ]
    if len(pitched) < 3:
        return None
    s = stream.Stream()
    for event in pitched[:10000]:
        item = note.Note(event.pitch)
        item.quarterLength = max(0.01, event.end - event.start)
        s.insert(event.start, item)
    detected = s.analyze("key")
    return f"{detected.tonic.name} {detected.mode}"
