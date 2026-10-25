"""Offline Knife 4 acceptance: one generated track per explicitly planned role."""

from __future__ import annotations

from copy import deepcopy

import pretty_midi
import pytest

from midivolt.part_orchestrator import compose_strict_parts, parse_program_assignments


_PROGRAMS = {
    "Drum kit": None, "Bass": 32, "Piano": 0, "Violin": 40,
    "Viola": 41, "Cello": 42, "Flute": 73, "Guitar": 24,
}


def source():
    song = pretty_midi.PrettyMIDI(initial_tempo=60)
    melody = pretty_midi.Instrument(program=73, name="Locked melody")
    melody.notes.append(pretty_midi.Note(91, 65, 0, 1))
    melody.control_changes.append(pretty_midi.ControlChange(1, 40, 0))
    song.instruments.append(melody)
    return song


class RoleGenerator:
    name = "offline-mock-role-generator"

    def __init__(self, *, wrong_program=None, drum_mode=None, extra_track=False, drum_pitch=36):
        self.calls = []
        self.wrong_program = wrong_program
        self.drum_mode = drum_mode
        self.extra_track = extra_track
        self.drum_pitch = drum_pitch

    def generate(self, prompt, *, tempo, seed=None):
        self.calls.append((prompt, tempo, seed))
        label = next((name for name in _PROGRAMS if f"one separate {name} MIDI part" in prompt), None)
        if label is None:
            raise ValueError("Role prompt not explicit")
        is_drum = label == "Drum kit" if self.drum_mode is None else self.drum_mode
        program = self.wrong_program if self.wrong_program is not None else (_PROGRAMS[label] or 0)
        midi = pretty_midi.PrettyMIDI(initial_tempo=120)
        track = pretty_midi.Instrument(program=program, name="Model output", is_drum=is_drum)
        track.notes.append(pretty_midi.Note(85, self.drum_pitch if is_drum else 60, 0, 0.5))
        midi.instruments.append(track)
        if self.extra_track:
            clone = deepcopy(track)
            clone.name = "Unrequested second track"
            midi.instruments.append(clone)
        return midi


def test_six_distinct_validated_parts_preserve_source_and_tempo():
    original = source()
    before = deepcopy(original)
    runner = RoleGenerator()
    result, plan, report = compose_strict_parts(
        original,
        "請加入鼓、貝斯、鋼琴、小提琴、中提琴、大提琴，不要吉他",
        runner,
        locked_tracks=(0,),
        program_assignments={"bass": 32},
        seed=12,
    )
    assert [p["role"] for p in plan["parts"]] == [
        "drums", "bass", "piano", "violin", "viola", "cello"
    ]
    assert plan["excluded_roles"] == ["guitar"]
    assert [i.program for i in result.instruments] == [73, 0, 32, 0, 40, 41, 42]
    assert result.instruments[1].is_drum is True
    assert all(not i.is_drum for i in result.instruments[2:])
    assert [i.name for i in result.instruments[1:]] == [
        "MIDIVOLT AI | 01 Drum kit", "MIDIVOLT AI | 02 Bass",
        "MIDIVOLT AI | 03 Piano", "MIDIVOLT AI | 04 Violin",
        "MIDIVOLT AI | 05 Viola", "MIDIVOLT AI | 06 Cello",
    ]
    assert all(i.notes[0].end == pytest.approx(1.0, abs=0.002) for i in result.instruments[1:])
    assert report["notes_added"] == 6 and report["notes_removed"] == 0
    assert report["locked_tracks"] == [0]
    assert len(runner.calls) == 6
    assert [call[2] for call in runner.calls] == [12, 13, 14, 15, 16, 17]
    assert all(call[1] == 60 for call in runner.calls)
    assert len(original.instruments) == 1
    assert original.instruments[0].notes[0].end == before.instruments[0].notes[0].end
    assert original.instruments[0].control_changes[0].value == 40


@pytest.mark.parametrize("overrides", [
    {}, {"bass": 40}, {"piano": 73}, {"drums": 0},
    {"bass": 32, "guitar": 24}, {"bass": True}, {"bass": -1},
])
def test_invalid_program_assignments_fail_before_model_call(overrides):
    runner = RoleGenerator()
    with pytest.raises((ValueError, TypeError)):
        compose_strict_parts(
            source(), "鼓、貝斯、鋼琴", runner,
            locked_tracks=(0,), program_assignments=overrides,
        )
    assert not runner.calls


def test_incorrect_generated_instrument_program_is_not_relabelled():
    runner = RoleGenerator(wrong_program=0)
    with pytest.raises(ValueError, match="expected GM 40"):
        compose_strict_parts(source(), "小提琴", runner, locked_tracks=(0,))
    assert len(runner.calls) == 1


@pytest.mark.parametrize("runner,message", [
    (RoleGenerator(extra_track=True), "number of new tracks"),
    (RoleGenerator(drum_mode=False), "drum-channel classification mismatch"),
    (RoleGenerator(drum_pitch=90), "percussion range"),
])
def test_drum_and_extra_track_validation(runner, message):
    with pytest.raises(ValueError, match=message):
        compose_strict_parts(source(), "鼓", runner, locked_tracks=(0,))


def test_failed_later_role_returns_no_partial_candidate():
    class FailsSecond(RoleGenerator):
        def generate(self, prompt, *, tempo, seed=None):
            if "Piano" in prompt:
                raise RuntimeError("model failed on piano")
            return super().generate(prompt, tempo=tempo, seed=seed)

    original = source()
    with pytest.raises(RuntimeError, match="model failed on piano"):
        compose_strict_parts(original, "鼓、鋼琴", FailsSecond(), locked_tracks=(0,))
    assert len(original.instruments) == 1


def test_parse_repeatable_gm_program_arguments():
    assert parse_program_assignments(["bass=32", "guitar=24"]) == {"bass": 32, "guitar": 24}
    for invalid in (["bass=32", "bass=33"], ["=32"], ["bass=-1"], ["bass=128"],
                    ["bass=x"], ["bass=0x20"], ["bass"], [34]):
        with pytest.raises(ValueError):
            parse_program_assignments(invalid)


def test_limits_reject_before_model():
    runner = RoleGenerator()
    with pytest.raises(ValueError, match="max_new_tracks"):
        compose_strict_parts(source(), "鼓、鋼琴", runner, locked_tracks=(0,), max_new_tracks=1)
    with pytest.raises(ValueError, match="seeds"):
        compose_strict_parts(source(), "鼓、鋼琴", runner, locked_tracks=(0,), seed=2**31-1)
    assert not runner.calls
