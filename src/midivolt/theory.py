"""Symbolic music analysis built on the BSD-licensed music21 library."""

from __future__ import annotations

from dataclasses import dataclass

import pretty_midi


@dataclass(frozen=True)
class ChordSpec:
    symbol: str
    root_pc: int
    bass_pc: int
    intervals: tuple[int, ...]


def _normalize_chord_symbol(token: str) -> str:
    """Translate common lead-sheet flat note names to music21's hyphen form.

    music21 uses B- for B-flat in chord roots and slash basses; a b inside
    a chord suffix (for example C7b9) remains an alteration.
    """
    if not token:
        return token
    if token[0].upper() in "ABCDEFG" and token[1:2] == "b":
        token = token[0].upper() + "-" + token[2:]
    slash = token.rfind("/")
    if slash >= 0:
        bass = token[slash + 1:]
        if len(bass) >= 2 and bass[0].upper() in "ABCDEFG" and bass[1:2] == "b":
            token = token[:slash + 1] + bass[0].upper() + "-" + bass[2:]
    return token


def parse_chords(progression: str) -> list[ChordSpec]:
    """Parse whitespace/comma-separated lead-sheet symbols, e.g. Fmaj7 Dm7 Gm7 C7."""
    from music21 import harmony

    tokens = progression.replace(",", " ").split()
    if not 1 <= len(tokens) <= 128:
        raise ValueError("Provide between 1 and 128 chord symbols.")
    result: list[ChordSpec] = []
    for token in tokens:
        try:
            symbol = harmony.ChordSymbol(_normalize_chord_symbol(token))
            pitches = symbol.pitches
            if not pitches or symbol.root() is None or symbol.bass() is None:
                raise ValueError("Unrecognized chord")
            root_pc = symbol.root().pitchClass
            bass_pc = symbol.bass().pitchClass
            chord_pitches = pitches
            normalized = _normalize_chord_symbol(token)
            if "/" in normalized:
                # music21 會把非和弦音的 slash 低音加入 pitches；和弦聲部只取和弦本體，
                # 低音另由 bass_pc 提供，避免低音重複混入和弦軌。
                body = harmony.ChordSymbol(normalized[:normalized.rfind("/")])
                if body.pitches and body.root() is not None and body.root().pitchClass == root_pc:
                    chord_pitches = body.pitches
            intervals = tuple(sorted({(p.pitchClass - root_pc) % 12 for p in chord_pitches}))
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
    from music21 import note, stream

    s = stream.Stream()
    for event in pitched[:10000]:
        item = note.Note(event.pitch)
        item.quarterLength = max(0.01, event.end - event.start)
        s.insert(event.start, item)
    detected = s.analyze("key")
    return f"{detected.tonic.name} {detected.mode}"
