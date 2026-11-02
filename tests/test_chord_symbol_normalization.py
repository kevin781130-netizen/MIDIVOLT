"""Lead-sheet flat spelling compatibility for the music21 adapter."""
from __future__ import annotations

import pytest

from midivolt.theory import _normalize_chord_symbol, parse_chords


@pytest.mark.parametrize(("source", "expected"), [
    ("Bbmaj7", "B-maj7"),
    ("Ebm7", "E-m7"),
    ("Ab7", "A-7"),
    ("Dbm7b5", "D-m7b5"),
    ("C7/Bb", "C7/B-"),
    ("Bb7/Eb", "B-7/E-"),
    ("G7b9", "G7b9"),
    ("F7#9", "F7#9"),
    ("C/E", "C/E"),
])
def test_normalizes_only_flat_root_and_slash_bass(source: str, expected: str):
    assert _normalize_chord_symbol(source) == expected


def test_music21_parses_common_flat_roots_and_slash_basses():
    pytest.importorskip("music21")
    specs = parse_chords("Bbmaj7 Ebm7 C7/Bb Bb7/Eb")
    assert [(x.root_pc, x.bass_pc) for x in specs] == [
        (10, 10), (3, 3), (0, 10), (10, 3),
    ]
    assert set(specs[0].intervals) == {0, 4, 7, 11}
    assert set(specs[1].intervals) == {0, 3, 7, 10}
    assert set(specs[2].intervals) == {0, 4, 7, 10}


def test_non_chord_tone_slash_bass_is_not_added_to_chord_voicing():
    # 回歸：Bb7/Eb 的 Eb 是低音而非和弦音，不得出現在和弦音程中。
    pytest.importorskip("music21")
    spec = parse_chords("Bb7/Eb")[0]
    assert spec.bass_pc == 3
    assert set(spec.intervals) == {0, 4, 7, 10}
    assert set(parse_chords("C/E")[0].intervals) == {0, 4, 7}
