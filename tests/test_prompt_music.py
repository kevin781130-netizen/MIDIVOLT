"""Original MIDI Agent-style product-workflow slice: real serialized MIDI.

These are deterministic symbolic-generation tests, NOT claims of LLM
composition quality or DAW/VST host acceptance.
"""
from __future__ import annotations

from pathlib import Path

import pretty_midi
import pytest

from midivolt.prompt_music import PARTS, parse_prompt, generate_sketch, report
from midivolt.prompt_cli import main
from midivolt.io import read_midi, write_midi


def score(midi):
    return tuple(
        (tr.name, tr.program, tr.is_drum,
         tuple((n.pitch, n.start, n.end, n.velocity) for n in tr.notes))
        for tr in midi.instruments
    )


def test_full_song_prompt_generates_four_separate_editable_midi_tracks():
    spec = parse_prompt("Create a full song with 8 bars in D minor, 110 bpm, sparse")
    m = generate_sketch(spec)
    assert spec.bars == 8
    assert spec.key == "D"
    assert spec.mode == "minor"
    assert spec.bpm == 110
    assert spec.parts == PARTS
    assert len(m.instruments) == 4
    assert {t.name for t in m.instruments} == {
        "MIDIVOLT | Chords", "MIDIVOLT | Melody",
        "MIDIVOLT | Bass", "MIDIVOLT | Drums",
    }
    assert sum(len(t.notes) for t in m.instruments) > 80
    assert all(n.end > n.start >= 0 and 0 <= n.pitch < 128
               for t in m.instruments for n in t.notes)
    assert m.instruments[3].is_drum
    assert {n.pitch for n in m.instruments[3].notes} == {36, 38, 42}
    assert m.get_end_time() <= 8 * 4 * 60 / 110 + 1e-5
    assert report(spec, m, extended=False)["llm_inference_used"] is False


def test_text_to_chords_only_in_correct_key():
    spec = parse_prompt("Write 8 bars of warm chords in D minor at 96 BPM")
    m = generate_sketch(spec)
    assert spec.parts == ("chords",)
    assert len(m.instruments) == 1
    pcs = {n.pitch % 12 for n in m.instruments[0].notes}
    d_minor = {2, 4, 5, 7, 9, 10, 0}
    assert pcs.issubset(d_minor)


def test_chinese_music_instruction_key_bars_and_parts():
    spec = parse_prompt("請寫8小節 F#小調 旋律 貝斯 100 BPM")
    assert (spec.key, spec.mode, spec.bars, spec.bpm) == ("F#", "minor", 8, 100)
    assert spec.parts == ("melody", "bass")
    m = generate_sketch(spec)
    assert [t.name for t in m.instruments] == [
        "MIDIVOLT | Melody", "MIDIVOLT | Bass",
    ]


def test_prompt_key_flat_and_half_time_drum_pattern():
    spec = parse_prompt("Create 4 bars of half-time drums in Bb major at 92 bpm")
    m = generate_sketch(spec)
    assert spec.key == "Bb"
    assert len(m.instruments) == 1
    assert m.instruments[0].is_drum
    assert sum(note.pitch == 38 for note in m.instruments[0].notes) == 4


def test_melodic_pitches_follow_major_scale():
    spec = parse_prompt("4 bars of rising melody in G major", seed=123)
    track = generate_sketch(spec).instruments[0]
    assert track.notes
    assert {n.pitch % 12 for n in track.notes}.issubset({7, 9, 11, 0, 2, 4, 6})


def test_same_prompt_seed_identical_notes_different_seed_can_vary():
    spec = parse_prompt("Make 4 bars of melody in C major", seed=21)
    assert score(generate_sketch(spec)) == score(generate_sketch(spec))
    other = parse_prompt("Make 4 bars of melody in C major", seed=22)
    assert score(generate_sketch(spec)) != score(generate_sketch(other))


@pytest.mark.parametrize("prompt", ["", "x"*1501])
def test_reject_bad_prompt_length(prompt):
    with pytest.raises(ValueError, match="1..1500"):
        parse_prompt(prompt)


@pytest.mark.parametrize("extra", [
    {"bars": 0}, {"bars": 40}, {"bpm": 0}, {"bpm": 900},
    {"seed": -1}, {"key": "H"}, {"mode": "dorian"},
])
def test_bounded_numeric_and_key_params(extra):
    with pytest.raises(ValueError):
        parse_prompt("4 bars of melody", **extra)


def test_existing_midi_non_destructive_4_4_extension(tmp_path):
    source = pretty_midi.PrettyMIDI(initial_tempo=100)
    locked = pretty_midi.Instrument(program=73, name="Original Flute")
    locked.notes.append(pretty_midi.Note(88, 65, .0, 2.9))
    locked.control_changes.append(pretty_midi.ControlChange(1, 23, time=.4))
    source.instruments.append(locked)
    src = tmp_path / "input.mid"
    write_midi(source, src)
    input_bytes = src.read_bytes()
    output = tmp_path / "extended.mid"
    assert main([
        "--prompt", "Extend with 2 bars of bass and drums in A minor",
        "--input", str(src), "--out", str(output),
    ]) == 0
    result = read_midi(output)
    assert len(result.instruments) == 3
    assert result.instruments[0].name == "Original Flute"
    assert len(result.instruments[0].notes) == 1
    assert result.instruments[0].notes[0].start == pytest.approx(0)
    assert result.instruments[0].control_changes[0].value == 23
    # 100 BPM, last original event at 2.9 seconds -> next bar at 4.8s.
    assert result.instruments[1].notes[0].start == pytest.approx(4.8, abs=.002)
    assert src.read_bytes() == input_bytes


def test_cli_midi_serialization_no_overwrite_and_explicit_variations(tmp_path, capsys):
    dest = tmp_path / "product.mid"
    argv = [
        "--prompt", "8 bars full arrangement in A minor, 128 bpm",
        "--out", str(dest), "--seed", "1234",
    ]
    assert main(argv) == 0
    assert len(read_midi(dest).instruments) == 4
    assert main(argv) == 2
    assert "overwrite" in capsys.readouterr().err.lower()
    assert main(argv + ["--overwrite"]) == 0


def test_extension_rejects_mismatched_explicit_tempo_and_meter(tmp_path):
    original = pretty_midi.PrettyMIDI(initial_tempo=120)
    i = pretty_midi.Instrument(program=0)
    i.notes.append(pretty_midi.Note(85, 60, 0, 1))
    original.instruments.append(i)
    src = tmp_path / "src.mid"
    write_midi(original, src)
    assert main([
        "--prompt", "bassline in C major",
        "--input", str(src), "--out", str(tmp_path/"out.mid"),
        "--bpm", "140",
    ]) == 2
    assert not (tmp_path/"out.mid").exists()
    original.time_signature_changes.append(pretty_midi.TimeSignature(3, 4, 0))
    with pytest.raises(ValueError, match="4/4"):
        generate_sketch(parse_prompt("bassline", bpm=120), source=original)


def test_single_role_and_explicit_parts_override():
    spec = parse_prompt(
        "song in A minor", parts=("bass", "drums"), bars=2, seed=9,
    )
    assert spec.parts == ("bass", "drums")
    assert [x.name for x in generate_sketch(spec).instruments] == [
        "MIDIVOLT | Bass", "MIDIVOLT | Drums",
    ]
