#!/usr/bin/env python3
"""Fail-closed real music21 acceptance for MIDIVOLT chord and key features.

Run from the repository root with the project's supported Python and an
installed music21 9.7.x environment:
    python scripts/accept_music21_core.py

This is an integration gate, not a mocked unit test. It refuses to report
PASS when music21 is missing or outside the supported version range.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path


def emit(status: str, *, code: int, **details) -> int:
    print(json.dumps({"status": status, **details}, sort_keys=True))
    return code


def version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    return tuple(int(part) for part in match.groups()) if match else None


def _key_fixture(tonic_pc: int, weights: list[float]):
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    instrument = pretty_midi.Instrument(program=0, name="Key profile fixture")
    cursor = 0.0
    for offset, weight in enumerate(weights):
        pitch = 60 + ((tonic_pc + offset) % 12)
        instrument.notes.append(
            pretty_midi.Note(velocity=90, pitch=pitch, start=cursor, end=cursor + weight)
        )
        cursor += weight
    midi.instruments.append(instrument)
    return midi


def run_acceptance() -> dict:
    import pretty_midi

    from midivolt.arrange import add_accompaniment
    from midivolt.theory import estimate_key, parse_chords

    # These expected pitch-class sets are based on documented music21
    # ChordSymbol forms: major/minor sevenths, half-diminished, and slash bass.
    cases = [
        ("Bbmaj7", 10, 10, {0, 4, 7, 11}),
        ("Ebm7", 3, 3, {0, 3, 7, 10}),
        ("C7/Bb", 0, 10, {0, 4, 7, 10}),
        ("Bb7/Eb", 10, 3, {0, 4, 7, 10}),
        ("Dbm7b5", 1, 1, {0, 3, 6, 10}),
        ("C/E", 0, 4, {0, 4, 7}),
    ]
    specs = parse_chords(" ".join(item[0] for item in cases))
    assert len(specs) == len(cases), "Chord parser returned the wrong number of symbols"
    for spec, (symbol, root_pc, bass_pc, intervals) in zip(specs, cases):
        assert spec.symbol == symbol, f"Original chord label changed: {symbol}"
        assert spec.root_pc == root_pc, f"Wrong root pitch class for {symbol}: {spec.root_pc}"
        assert spec.bass_pc == bass_pc, f"Wrong bass pitch class for {symbol}: {spec.bass_pc}"
        assert set(spec.intervals) == intervals, (
            f"Wrong chord intervals for {symbol}: {spec.intervals}"
        )

    # A genuinely invalid root must fail closed.
    try:
        parse_chords("H-7")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid chord H-7 was accepted")

    # Exercise actual MIDI generation and slash-bass routing. The original
    # melody object must remain byte-for-byte equivalent at the event level.
    source = pretty_midi.PrettyMIDI(initial_tempo=120)
    lead = pretty_midi.Instrument(program=73, name="Original melody")
    lead.notes.append(pretty_midi.Note(velocity=91, pitch=72, start=0.25, end=0.75))
    source.instruments.append(lead)
    original_events = [
        (n.pitch, n.velocity, n.start, n.end) for n in source.instruments[0].notes
    ]
    original_tempo = source.get_tempo_changes()
    arranged = add_accompaniment(
        source, "C7/Bb Fmaj7/A", beats_per_chord=4.0, start_beat=2.0
    )
    assert len(source.instruments) == 1, "Source MIDI was mutated"
    assert [
        (n.pitch, n.velocity, n.start, n.end) for n in source.instruments[0].notes
    ] == original_events, "Original melody notes changed"
    assert len(arranged.instruments) == 3, "Expected original + chord + bass tracks"
    chord_track, bass_track = arranged.instruments[1:]
    assert chord_track.name == "MIDIVOLT Chords"
    assert bass_track.name == "MIDIVOLT Bass"
    assert [n.pitch for n in chord_track.notes[:4]] == [60, 64, 67, 70]
    assert [n.pitch for n in chord_track.notes[4:]] == [65, 69, 72, 76]
    assert [n.pitch for n in bass_track.notes] == [46, 45], (
        "Slash-chord bass notes were not routed from Bb and A"
    )
    assert [(round(n.start, 6), round(n.end, 6)) for n in bass_track.notes] == [
        (1.0, 3.0), (3.0, 5.0)
    ], "Accompaniment did not follow the requested beat offsets"
    assert source.get_tempo_changes()[1].tolist() == original_tempo[1].tolist()

    # Use the Krumhansl-Schmuckler pitch-class profiles as deterministic
    # fixtures, rotated to C major and A minor. This tests music21's real
    # Stream.analyze('key') path through MIDIVOLT's public adapter.
    major_profile = [
        6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
        2.52, 5.19, 2.39, 3.66, 2.29, 2.88,
    ]
    minor_profile = [
        6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
        2.54, 4.75, 3.98, 2.69, 3.34, 3.17,
    ]
    c_major = estimate_key(_key_fixture(0, major_profile))
    a_minor = estimate_key(_key_fixture(9, minor_profile))
    assert c_major == "C major", f"Expected C major, got {c_major!r}"
    assert a_minor == "A minor", f"Expected A minor, got {a_minor!r}"

    return {
        "chord_symbols": len(cases),
        "invalid_chord_rejected": True,
        "arrangement": {
            "chord_notes": len(chord_track.notes),
            "bass_notes": len(bass_track.notes),
            "slash_bass_midi": [n.pitch for n in bass_track.notes],
            "source_preserved": True,
        },
        "key_detection": {"C_major": c_major, "A_minor": a_minor},
    }


def main() -> int:
    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        return emit(
            "BLOCKED_UNSUPPORTED_PYTHON",
            code=2,
            python=sys.version.split()[0],
            required="CPython 3.11–3.13",
        )
    try:
        import music21
        from importlib.metadata import version as package_version
        installed_version = package_version("music21")
    except (ImportError, ModuleNotFoundError, Exception) as exc:
        return emit(
            "BLOCKED_MUSIC21_NOT_INSTALLED",
            code=2,
            python=sys.version.split()[0],
            error=f"{type(exc).__name__}: {exc}",
            required="music21>=9.7.1,<10",
        )

    parsed_version = version_tuple(installed_version)
    if parsed_version is None or not ((9, 7, 1) <= parsed_version < (10, 0, 0)):
        return emit(
            "BLOCKED_UNSUPPORTED_MUSIC21_VERSION",
            code=2,
            python=sys.version.split()[0],
            music21=installed_version,
            required="music21>=9.7.1,<10",
        )

    # Prefer this checkout's exact source tree over any unrelated installed
    # MIDIVOLT copy; music21 itself remains the real installed dependency.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    try:
        result = run_acceptance()
    except Exception as exc:
        traceback.print_exc()
        return emit(
            "FAIL",
            code=1,
            python=sys.version.split()[0],
            music21=installed_version,
            error=f"{type(exc).__name__}: {exc}",
        )

    return emit(
        "PASS_REAL_MUSIC21_ACCEPTANCE",
        code=0,
        python=sys.version.split()[0],
        music21=installed_version,
        results=result,
    )


if __name__ == "__main__":
    raise SystemExit(main())
