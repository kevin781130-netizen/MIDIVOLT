"""No-network acceptance tests for reviewable arrangement proposals."""
from copy import deepcopy
import json

import pretty_midi
import pytest

from midivolt.review_engine import (
    apply_proposal, check_proposal, create_proposal, inspect_arrangement,
)
from midivolt.review_cli import main
from midivolt.io import read_midi, write_midi


def source_midi(tmp_path):
    path = tmp_path / "original.mid"
    midi = pretty_midi.PrettyMIDI(initial_tempo=70)
    flute = pretty_midi.Instrument(program=73, name="Keep flute melody")
    flute.notes.extend([
        pretty_midi.Note(90, 65, 0, 0.5),
        pretty_midi.Note(91, 69, 0.5, 1.0),
    ])
    flute.control_changes.append(
        pretty_midi.ControlChange(number=1, value=30, time=0)
    )
    midi.instruments.append(flute)
    write_midi(midi, path)
    return path


def candidate_with_new_tracks(tmp_path, input_path):
    output = tmp_path / "candidate.mid"
    midi = deepcopy(read_midi(input_path))
    chord = pretty_midi.Instrument(program=0, name="Proposed piano")
    chord.notes.append(pretty_midi.Note(70, 60, 0, 1))
    bass = pretty_midi.Instrument(program=32, name="Proposed bass")
    bass.notes.append(pretty_midi.Note(80, 41, 0, 1))
    midi.instruments.extend((chord, bass))
    write_midi(midi, output)
    return output


def test_full_review_and_explicit_approval(tmp_path):
    src = source_midi(tmp_path)
    can = candidate_with_new_tracks(tmp_path, src)
    manifest = tmp_path / "proposal.json"
    original = src.read_bytes()
    proposed = create_proposal(src, can, manifest, locked_tracks=[0])
    assert proposed["review"]["notes_added"] == 2
    assert proposed["review"]["notes_removed"] == 0
    assert len(proposed["review"]["tracks_changed"]) == 2
    assert src.read_bytes() == original

    _, before = check_proposal(manifest)
    assert before["locked_tracks"] == [0]
    with pytest.raises(PermissionError):
        apply_proposal(manifest, tmp_path / "approved.mid", approved=False)
    result = apply_proposal(
        manifest, tmp_path / "approved.mid", approved=True
    )
    assert result["approved"] is True
    output = read_midi(result["output"])
    assert len(output.instruments) == 3
    assert src.read_bytes() == original
    assert len(read_midi(src).instruments) == 1
    with pytest.raises(FileExistsError):
        apply_proposal(manifest, tmp_path / "approved.mid", approved=True)


def test_changed_locked_pitch_is_rejected(tmp_path):
    src = source_midi(tmp_path)
    can = tmp_path / "modified.mid"
    midi = read_midi(src)
    midi.instruments[0].notes[0].pitch += 1
    write_midi(midi, can)
    with pytest.raises(ValueError, match="Locked track"):
        create_proposal(src, can, tmp_path / "proposal.json", locked_tracks=[0])


def test_locked_controls_and_track_identity_are_protected(tmp_path):
    src = source_midi(tmp_path)
    midi = read_midi(src)
    midi.instruments[0].control_changes[0].value += 1
    with pytest.raises(ValueError, match="Locked track"):
        inspect_arrangement(read_midi(src), midi, [0])
    midi = read_midi(src)
    midi.instruments[0].program = 2
    with pytest.raises(ValueError, match="Locked track"):
        inspect_arrangement(read_midi(src), midi, [0])


def test_tempo_change_is_rejected_even_if_melody_same(tmp_path):
    src = source_midi(tmp_path)
    midi = read_midi(src)
    midi._tick_scales[0] = (0, 60.0 / 120 / midi.resolution)
    with pytest.raises(ValueError, match="tempo"):
        inspect_arrangement(read_midi(src), midi, [0])


def test_locked_track_indices_validated(tmp_path):
    src = source_midi(tmp_path)
    midi = read_midi(src)
    for lock in ([], [0, 0], [1], [-1]):
        with pytest.raises(ValueError):
            inspect_arrangement(midi, midi, lock)


def test_source_and_candidate_hash_guard(tmp_path):
    src = source_midi(tmp_path)
    can = candidate_with_new_tracks(tmp_path, src)
    man = tmp_path / "plan.json"
    create_proposal(src, can, man, locked_tracks=[0])
    with can.open("ab") as stream:
        stream.write(b"additional bytes after review")
    with pytest.raises(ValueError, match="changed since proposal"):
        check_proposal(man)


def test_modifying_source_after_proposal_rejected(tmp_path):
    src = source_midi(tmp_path)
    can = candidate_with_new_tracks(tmp_path, src)
    man = tmp_path / "plan.json"
    create_proposal(src, can, man, locked_tracks=[0])
    src.write_bytes(src.read_bytes() + b"extra")
    with pytest.raises(ValueError, match="changed since proposal"):
        apply_proposal(man, tmp_path / "approved.mid", approved=True)


def test_no_in_place_or_reuse_of_manifest(tmp_path):
    src = source_midi(tmp_path)
    with pytest.raises(ValueError):
        create_proposal(src, src, tmp_path / "plan.json", locked_tracks=[0])
    can = candidate_with_new_tracks(tmp_path, src)
    man = tmp_path / "plan.json"
    create_proposal(src, can, man, locked_tracks=[0])
    with pytest.raises(FileExistsError):
        create_proposal(src, can, man, locked_tracks=[0])
    with pytest.raises(ValueError):
        apply_proposal(man, src, approved=True)
    with pytest.raises(ValueError):
        apply_proposal(man, can, approved=True)


def test_cli_propose_preview_apply(tmp_path, capsys):
    src = source_midi(tmp_path)
    can = candidate_with_new_tracks(tmp_path, src)
    plan = tmp_path / "plan.json"
    out = tmp_path / "ok.mid"
    assert main(["propose", "--input", str(src), "--candidate",
                 str(can), "--manifest", str(plan), "--lock", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["notes_added"] == 2
    assert main(["preview", "--manifest", str(plan)]) == 0
    assert main(["apply", "--manifest", str(plan), "--out", str(out)]) == 2
    assert not out.exists()
    assert main(["apply", "--manifest", str(plan), "--out",
                 str(out), "--approve"]) == 0
    assert len(read_midi(out).instruments) == 3
