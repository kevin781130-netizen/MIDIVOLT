"""K9 self-reported model evidence audit tests. No pretrained model or GUI is run."""
from __future__ import annotations

from hashlib import sha256
import json

import mido
import pretty_midi
import pytest

from midivolt.composition_audit import audit_composition_acceptance
from midivolt.composition_audit_cli import main
from midivolt.harmony_quality import prepare_harmonic_context, evaluate_part_harmony
from midivolt.io import read_midi, write_midi
from midivolt.part_quality import evaluate_part_structure
from midivolt.review_engine import create_proposal


def fixture(tmp_path, *, with_harmony=False):
    src = tmp_path / "source.mid"
    candidate = tmp_path / "candidate.mid"
    manifest = tmp_path / "proposal.json"
    acceptance = tmp_path / "acceptance.json"
    original = pretty_midi.PrettyMIDI(initial_tempo=60)
    lead = pretty_midi.Instrument(73, name="Locked melody")
    lead.notes.append(pretty_midi.Note(90, 72, 0, 1))
    original.instruments.append(lead)
    write_midi(original, src)

    merged = pretty_midi.PrettyMIDI(initial_tempo=60)
    merged.instruments.append(lead)
    for index, (name, program, note) in enumerate(
        (("Piano", 0, 60), ("Violin", 40, 67))
    ):
        part = pretty_midi.Instrument(program, name=f"MIDIVOLT AI | {index+1:02d} {name}")
        part.notes.append(pretty_midi.Note(88, note, index, index + 1))
        merged.instruments.append(part)
    write_midi(merged, candidate)
    proposal = create_proposal(src, candidate, manifest, locked_tracks=[0])
    src_midi, new_midi = read_midi(src), read_midi(candidate)
    context = prepare_harmonic_context(key="C major") if with_harmony else None
    attempts = []
    for role, track in zip(("piano", "violin"), new_midi.instruments[1:]):
        attempts.append({
            "role": role, "attempt": 1, "seed": 41 if role == "piano" else 43,
            "accepted": True,
            "metrics": evaluate_part_structure(src_midi, track, role),
            "harmony_metrics": (evaluate_part_harmony(
                src_midi, track, role, context, reference_tracks=(0,)
            ) if context else None),
            "reason": None,
        })
    record = {
        "schema_version": 1, "model": "text2midi",
        "real_inference_completed": True,
        "inference_mode": "trusted_external_checkpoint_only",
        "elapsed_seconds": 24.0,
        "upstream_commit": "a"*40,
        "requirements_sha256": "b"*64,
        "checkpoint_sha256": "c"*64, "vocab_sha256": "d"*64,
        "source_sha256": proposal["source_sha256"],
        "candidate_sha256": proposal["candidate_sha256"],
        "source": str(src), "candidate": str(candidate), "manifest": str(manifest),
        "tracks": 3, "new_notes": 2, "locked_tracks": [0],
        "quality_policy": {
            "minimum_structure_score": 0.75, "quality_retries": 1,
            "harmony_key": "C major" if context else None,
            "harmony_chords": [], "beats_per_chord": 4 if context else None,
            "minimum_harmony_score": None, "harmony_gating_enabled": False,
        },
        "quality_attempts": attempts,
        "review": proposal["review"],
        "approved_for_use": False,
        "commercial_release_ready": False,
    }
    acceptance.write_text(json.dumps(record), encoding="utf-8")
    return src, candidate, manifest, acceptance, record


def test_valid_k8_report_is_recomputed_and_not_upgraded_to_real_model_proof(tmp_path):
    src, midi, manifest, report, record = fixture(tmp_path)
    before = [p.read_bytes() for p in (src, midi, manifest, report)]
    audit = audit_composition_acceptance(report, output_path=tmp_path / "audit.json")
    assert audit["accepted_roles"] == 2
    assert audit["generated_notes"] == 2
    assert audit["model_attempts_reported"] == 2
    assert audit["reported_seconds_per_generated_note"] == 12.0
    assert audit["candidate_sha256"] == sha256(midi.read_bytes()).hexdigest()
    assert [x["program"] for x in audit["roles"]] == [0, 40]
    assert audit["midi_type_1_verified"]
    assert audit["acceptance_files_verified"]
    assert audit["independent_real_model_execution_proven"] is False
    assert audit["actual_cubase_gui_operation_verified"] is False
    assert audit["commercial_release_ready"] is False
    assert audit["cubase_roundtrip"]["status"] == "not_provided"
    assert [p.read_bytes() for p in (src, midi, manifest, report)] == before
    assert json.loads((tmp_path / "audit.json").read_text()) == audit


def test_report_with_harmony_metrics_replays(tmp_path):
    _, _, _, report, _ = fixture(tmp_path, with_harmony=True)
    result = audit_composition_acceptance(report, output_path=tmp_path / "audit.json")
    assert [x["harmony_score"] for x in result["roles"]] == [1.0, 1.0]


def test_returned_file_identical_events_never_claims_cubase_execution(tmp_path):
    _, candidate, _, report, _ = fixture(tmp_path)
    returned = tmp_path / "returned.mid"
    returned.write_bytes(candidate.read_bytes())
    result = audit_composition_acceptance(
        report, output_path=tmp_path / "audit.json", cubase_return=returned)
    assert result["cubase_roundtrip"]["exact_event_match"] is True
    assert result["cubase_roundtrip"]["cubase_application_import_verified"] is False
    assert result["actual_cubase_gui_operation_verified"] is False


def test_returned_file_drift_is_reported_not_forged_as_pass(tmp_path):
    _, candidate, _, report, _ = fixture(tmp_path)
    returned = tmp_path / "returned.mid"
    midi = mido.MidiFile(candidate)
    for track in midi.tracks:
        first = next((e for e in track if e.type == "note_on" and e.velocity > 0), None)
        if first:
            first.note += 1
            break
    midi.save(returned)
    result = audit_composition_acceptance(
        report, output_path=tmp_path / "audit.json", cubase_return=returned)
    assert result["cubase_roundtrip"]["exact_event_match"] is False
    assert result["cubase_roundtrip"]["missing_events"] >= 1
    assert result["actual_cubase_gui_operation_verified"] is False


def test_modified_candidate_refuses_report_publication(tmp_path):
    _, candidate, _, report, _ = fixture(tmp_path)
    midi = mido.MidiFile(candidate)
    for track in midi.tracks:
        note = next((x for x in track if x.type == "note_on" and x.velocity > 0), None)
        if note:
            note.note += 1
            break
    midi.save(candidate)
    out = tmp_path / "audit.json"
    with pytest.raises(ValueError, match="changed since proposal"):
        audit_composition_acceptance(report, output_path=out)
    assert not out.exists()


@pytest.mark.parametrize("field,value", [
    ("real_inference_completed", False),
    ("model", "fixture"), ("checkpoint_sha256", "wrong"),
    ("elapsed_seconds", float("nan")), ("new_notes", 500),
])
def test_forged_or_malformed_report_refused(tmp_path, field, value):
    _, _, _, report, record = fixture(tmp_path)
    record[field] = value
    report.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError):
        audit_composition_acceptance(report, output_path=tmp_path / "audit.json")
    assert not (tmp_path / "audit.json").exists()


def test_altered_acceptance_held_structure_metrics_rejected(tmp_path):
    _, _, _, report, record = fixture(tmp_path)
    record["quality_attempts"][0]["metrics"]["score"] = 0.1
    report.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="diagnostics fail replay"):
        audit_composition_acceptance(report, output_path=tmp_path / "audit.json")


def test_repeat_or_duplicate_role_claims_fail(tmp_path):
    _, _, _, report, record = fixture(tmp_path)
    record["quality_attempts"].append(record["quality_attempts"][0].copy())
    report.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="continue after an accepted part"):
        audit_composition_acceptance(report, output_path=tmp_path / "audit.json")


def test_altered_gm_program_rejected_even_with_new_valid_manifest(tmp_path):
    src, candidate, manifest, report, record = fixture(tmp_path)
    # Rewrite candidate with a plausible but wrong violin GM program, then
    # *also* regenerate manifest and hashes. Do not trust just the hash match.
    midi = read_midi(candidate)
    midi.instruments[2].program = 41
    candidate.unlink()
    write_midi(midi, candidate)
    manifest.unlink()
    proposal = create_proposal(src, candidate, manifest, locked_tracks=[0])
    record["candidate_sha256"] = proposal["candidate_sha256"]
    record["review"] = proposal["review"]
    report.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="expected GM 40"):
        audit_composition_acceptance(report, output_path=tmp_path / "audit.json")


def test_repeated_audit_output_never_overwritten(tmp_path):
    _, _, _, report, _ = fixture(tmp_path)
    dst = tmp_path / "audit.json"
    audit_composition_acceptance(report, output_path=dst)
    before = dst.read_bytes()
    with pytest.raises(ValueError, match="new file"):
        audit_composition_acceptance(report, output_path=dst)
    assert dst.read_bytes() == before


def test_cli_accepts_good_report_and_exposes_error_on_missing_file(tmp_path, capsys):
    _, _, _, report, _ = fixture(tmp_path)
    out = tmp_path / "audit.json"
    assert main(["--acceptance", str(report), "--out", str(out)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["accepted_roles"] == 2
    assert main(["--acceptance", str(report), "--out", str(out)]) == 2
    assert "must be a separate, new file" in capsys.readouterr().err
