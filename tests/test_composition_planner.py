"""Offline contract tests for explicit natural-language track planning."""

import json

import pretty_midi
import pytest

from midivolt.composition_planner import make_composition_plan
from midivolt.io import write_midi
from midivolt.plan_cli import main


def plan(prompt, count=2, locks=(0,)):
    return make_composition_plan(
        prompt, source_track_count=count, locked_tracks=locks
    )


def test_traditional_chinese_four_tracks_with_exclusion():
    result = plan("請加鼓、貝斯、鋼琴與弦樂，不要吉他；保留主旋律")
    assert [p["role"] for p in result["parts"]] == [
        "drums", "bass", "piano", "strings"
    ]
    assert result["excluded_roles"] == ["guitar"]
    assert result["needs_program_selection"] == ["bass"]
    assert result["locked_tracks"] == [0]
    assert result["requires_human_approval"] is True
    assert result["generated_midi"] is False
    assert [p["gm_program_hint"] for p in result["parts"]] == [None, None, 0, 48]


def test_named_string_and_woodwind_parts_prevent_family_duplicates():
    result = plan("弦樂：小提琴、中提琴、大提琴；木管：長笛和單簧管")
    assert [p["role"] for p in result["parts"]] == [
        "violin", "viola", "cello", "flute", "clarinet"
    ]
    assert [p["gm_program_hint"] for p in result["parts"]] == [40, 41, 42, 73, 71]


def test_simplified_and_english_request():
    assert [p["role"] for p in plan("鼓组、贝斯、钢琴")["parts"]] == [
        "drums", "bass", "piano"
    ]
    assert [p["role"] for p in plan(
        "Please write drums, bass guitar, piano, violin, and cello"
    )["parts"]] == ["drums", "bass", "piano", "violin", "cello"]


def test_negation_list_propagates_but_next_clause_is_positive():
    result = plan("Without drums and bass, add piano and cello.")
    assert [p["role"] for p in result["parts"]] == ["piano", "cello"]
    assert result["excluded_roles"] == ["drums", "bass"]
    zh = plan("不要鼓和貝斯，只要鋼琴")
    assert [p["role"] for p in zh["parts"]] == ["piano"]
    assert zh["excluded_roles"] == ["drums", "bass"]


def test_no_substring_false_classification():
    result = plan("bassoon and piano in an embassy")
    assert [p["role"] for p in result["parts"]] == ["piano", "bassoon"]


@pytest.mark.parametrize("phrase", [
    "Add drums, but no drums",
    "不要鼓但是請加鼓",
    "Without strings, add violin",
    "不要木管、加長笛",
])
def test_conflicting_requests_fail_closed(phrase):
    with pytest.raises(ValueError):
        plan(phrase)


@pytest.mark.parametrize("phrase", [
    "", "cinematic", "embassy score", "不要鼓", "Make it orchestral",
])
def test_no_positive_instrument_refuses_to_guess(phrase):
    with pytest.raises(ValueError):
        plan(phrase)


@pytest.mark.parametrize("count,locks", [
    (0, (0,)), (2, ()), (2, (2,)), (2, (-1,)), (2, (0, 0)),
    (2, (False,)), (2, (0, 1, 1)),
])
def test_source_and_lock_safety(count, locks):
    with pytest.raises(ValueError):
        plan("piano", count=count, locks=locks)


def test_cli_emits_json_and_refuses_overwrite(tmp_path, capsys):
    src = tmp_path / "source.mid"
    midi = pretty_midi.PrettyMIDI(initial_tempo=138)
    track = pretty_midi.Instrument(73, name="Original melody")
    track.notes.append(pretty_midi.Note(82, 67, 0, 1))
    midi.instruments.append(track)
    write_midi(midi, src)
    source_bytes = src.read_bytes()
    out = tmp_path / "plan.json"
    argv = ["--source", str(src), "--prompt", "鼓、貝斯、鋼琴、弦樂",
            "--lock", "0", "--out", str(out)]
    assert main(argv) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [p["role"] for p in payload["parts"]] == ["drums", "bass", "piano", "strings"]
    assert src.read_bytes() == source_bytes
    assert main(argv) == 2
    assert json.loads(out.read_text(encoding="utf-8")) == payload
    assert main(argv[:-2]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["parts"] == payload["parts"]


def test_cli_out_of_bounds_track_does_not_create_plan(tmp_path):
    src = tmp_path / "song.mid"
    midi = pretty_midi.PrettyMIDI()
    melody = pretty_midi.Instrument(0)
    melody.notes.append(pretty_midi.Note(90, 60, 0, 1))
    midi.instruments.append(melody)
    write_midi(midi, src)
    out = tmp_path / "nope.json"
    assert main(["--source", str(src), "--prompt", "piano",
                 "--lock", "9", "--out", str(out)]) == 2
    assert not out.exists()
