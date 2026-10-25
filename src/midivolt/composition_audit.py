"""K9: independent verification of a persisted K8 MIDI acceptance report.

This is a *file/provenance consistency audit*, not independent proof that the
pretrained model or Cubase GUI actually ran. Never elevate JSON self-reports
to external, independently verified evidence.
"""
from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from .composition_planner import ROLES
from .cubase_smf import compare_smf, inspect_smf
from .harmony_quality import evaluate_part_harmony, prepare_harmonic_context
from .io import read_midi
from .part_orchestrator import _PROGRAM_FAMILIES
from .part_quality import evaluate_part_structure
from .review_engine import _save_new_json, check_proposal


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as reader:
        for data in iter(lambda: reader.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Acceptance report must be a JSON object.")
    return data


def _acceptance_file_paths(report_path: Path, record: dict) -> dict[str, Path]:
    found = {"acceptance": report_path}
    for name in ("source", "candidate", "manifest"):
        raw = record.get(name)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"Acceptance report lacks {name}.")
        found[name] = Path(raw).expanduser().resolve()
    if len(set(found.values())) != len(found):
        raise ValueError("Acceptance/source/candidate/manifest paths must be distinct.")
    return found


def _accepted_parts(record: dict) -> tuple[list[dict], list[dict]]:
    attempts = record.get("quality_attempts")
    policy = record.get("quality_policy")
    if not isinstance(attempts, list) or not attempts or not isinstance(policy, dict):
        raise ValueError("Expected K8 per-part quality attempts and quality policy.")
    roles = {r.name: r for r in ROLES}
    accepted = []
    completed = set()
    per_role = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("Invalid quality attempt entry.")
        role = attempt.get("role")
        no = attempt.get("attempt")
        if role not in roles or type(no) is not int or no < 1:
            raise ValueError("Invalid role or attempt number.")
        if role in completed:
            raise ValueError("Attempts continue after an accepted part.")
        if no != per_role.get(role, 0) + 1:
            raise ValueError("Non-sequential or repeated part attempt numbers.")
        per_role[role] = no
        if type(attempt.get("accepted")) is not bool:
            raise ValueError("Part attempt acceptance must be boolean.")
        if attempt["accepted"]:
            if attempt.get("reason") is not None:
                raise ValueError("Accepted part cannot have a rejection reason.")
            if not isinstance(attempt.get("metrics"), dict):
                raise ValueError("Accepted part lacks MIDI structure diagnostics.")
            completed.add(role)
            accepted.append(attempt)
        elif not isinstance(attempt.get("reason"), str) or not attempt["reason"]:
            raise ValueError("Rejected part must have a recorded reason.")
    if set(per_role) != completed or not accepted:
        raise ValueError("Every attempted part must finish with exactly one acceptance.")
    if len(accepted) > 64:
        raise ValueError("Acceptance exceeds the maximum part budget.")
    return accepted, attempts


def audit_composition_acceptance(
    acceptance_report: str | Path,
    *,
    output_path: str | Path,
    cubase_return: str | Path | None = None,
) -> dict:
    """Re-evaluate saved MIDI, lock checks, role metadata and quality metrics.

    Source/candidate/report are read-only. A distinct new JSON audit report
    is written only after all checks pass. Optional returned SMF is compared
    by MIDI events; even an exact match does NOT prove it came from Cubase.
    """
    report_file = Path(acceptance_report).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    record = _read_json(report_file)
    paths = _acceptance_file_paths(report_file, record)
    if output.suffix.lower() != ".json" or not output.parent.is_dir():
        raise ValueError("Audit output must be a .json in an existing directory.")
    if output in paths.values() or output.exists() or output.is_symlink():
        raise ValueError("Audit output must be a separate, new file.")
    if record.get("schema_version") != 1 or record.get("model") != "text2midi":
        raise ValueError("Requires a K8 Text2midi acceptance report.")
    if record.get("real_inference_completed") is not True or record.get("inference_mode") != "trusted_external_checkpoint_only":
        raise ValueError("This K8 report does not claim a completed external inference.")
    for digest_name in ("checkpoint_sha256", "vocab_sha256",
                        "requirements_sha256"):
        val = record.get(digest_name)
        if not isinstance(val, str) or len(val) != 64 or any(x not in "0123456789abcdef" for x in val):
            raise ValueError(f"Missing or invalid {digest_name} in acceptance report.")
    if not isinstance(record.get("upstream_commit"), str) or len(record["upstream_commit"]) != 40 or any(x not in "0123456789abcdef" for x in record["upstream_commit"]):
        raise ValueError("Missing pinned upstream source commit.")
    seconds = record.get("elapsed_seconds")
    if type(seconds) not in (int, float) or not isfinite(seconds) or seconds < 0:
        raise ValueError("Invalid reported inference elapsed seconds.")

    proposal, original_review = check_proposal(paths["manifest"])
    for key, file in (("source_sha256", paths["source"]),
                      ("candidate_sha256", paths["candidate"])):
        if record.get(key) != _digest(file) or proposal.get(key) != record[key]:
            raise ValueError(f"Acceptance report {key} does not match disk.")
    if str(paths["source"]) != str(Path(proposal["source"]).resolve()) or str(paths["candidate"]) != str(Path(proposal["candidate"]).resolve()):
        raise ValueError("Acceptance report and proposal identify different MIDI files.")
    if record.get("review") != original_review:
        raise ValueError("Acceptance report review mismatch.")
    if (record.get("new_notes") != original_review["notes_added"]
            or original_review["notes_added"] <= 0 or original_review["notes_removed"]):
        raise ValueError("Acceptance note counts are inconsistent.")
    locked = record.get("locked_tracks")
    if (not isinstance(locked, list) or not locked
            or any(type(x) is not int for x in locked)
            or locked != original_review["locked_tracks"]):
        raise ValueError("Locked tracks disagree with proposal.")
    source = read_midi(paths["source"])
    candidate = read_midi(paths["candidate"])
    accepted, attempts = _accepted_parts(record)
    if len(candidate.instruments) != len(source.instruments) + len(accepted) or record.get("tracks") != len(candidate.instruments):
        raise ValueError("Candidate track count does not match accepted instrument roles.")
    policy = record["quality_policy"]
    threshold = policy.get("minimum_structure_score")
    if type(threshold) not in (int, float) or not isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Invalid stored structure threshold.")
    harmony = prepare_harmonic_context(
        key=policy.get("harmony_key"),
        chords=(" ".join(policy.get("harmony_chords") or []) or None),
        beats_per_chord=policy.get("beats_per_chord") or 4.0,
    )
    harmony_min = policy.get("minimum_harmony_score")
    if harmony_min is not None and (
        type(harmony_min) not in (float, int) or not isfinite(harmony_min)
        or not 0 <= harmony_min <= 1 or harmony is None
    ):
        raise ValueError("Invalid stored harmony threshold.")

    roles = {role.name: role for role in ROLES}
    roles_detail = []
    for index, attempt in enumerate(accepted):
        role = roles[attempt["role"]]
        track = candidate.instruments[len(source.instruments) + index]
        required_name = f"MIDIVOLT AI | {index+1:02d} {role.label}"
        if track.name != required_name or bool(track.is_drum) != role.drum:
            raise ValueError(f"{role.name}: mismatched MIDI track name or drum flag.")
        if role.drum:
            if any(not 35 <= n.pitch <= 81 for n in track.notes):
                raise ValueError("Drum pitch outside 35..81.")
        elif role.gm_hint is not None:
            if track.program != role.gm_hint:
                raise ValueError(f"{role.name}: expected GM {role.gm_hint}.")
        elif track.program not in _PROGRAM_FAMILIES[role.name]:
            raise ValueError(f"{role.name}: unexpected program {track.program}.")

        recalculated = evaluate_part_structure(source, track, role.name)
        prev_metric = attempt["metrics"]
        if (recalculated != prev_metric or
                recalculated["score"] < threshold):
            raise ValueError(f"{role.name}: stored structure diagnostics fail replay.")
        computed_harmony = None
        if harmony is not None:
            computed_harmony = evaluate_part_harmony(
                source, track, role.name, harmony,
                reference_tracks=tuple(locked),
            )
        if attempt.get("harmony_metrics") != computed_harmony:
            raise ValueError(f"{role.name}: stored harmony diagnostics fail replay.")
        if (harmony_min is not None and computed_harmony["score"] is not None
                and computed_harmony["score"] < harmony_min):
            raise ValueError(f"{role.name}: stored harmony threshold not satisfied.")
        roles_detail.append({
            "role": role.name, "program": int(track.program),
            "is_drum": bool(track.is_drum), "notes": len(track.notes),
            "attempts": attempt["attempt"],
            "structural_score": recalculated["score"],
            "harmony_score": computed_harmony["score"] if computed_harmony else None,
            "metadata_checks_passed": True,
        })
    new_note_total = sum(x["notes"] for x in roles_detail)
    if new_note_total != original_review["notes_added"]:
        raise ValueError("New note count differs from independently decoded MIDI.")

    smf = inspect_smf(paths["candidate"])
    if smf["type"] != 1:
        raise ValueError("Cubase handoff requires Type 1 SMF.")
    daw_comparison = {"status": "not_provided", "exact_event_match": None,
                      "cubase_application_import_verified": False}
    if cubase_return is not None:
        returned = Path(cubase_return).expanduser().resolve()
        if returned in (*paths.values(), output):
            raise ValueError("Cubase returned MIDI must be a distinct file.")
        daw_comparison = compare_smf(paths["candidate"], returned)
        daw_comparison["status"] = "file_event_comparison_only"
        daw_comparison["cubase_application_import_verified"] = False

    summary = {
        "schema_version": 1,
        "audit_type": "midivolt_k9_offline_acceptance_audit",
        "acceptance_report": str(report_file),
        "source_sha256": record["source_sha256"],
        "candidate_sha256": record["candidate_sha256"],
        "report_sha256": _digest(report_file),
        "claimed_real_inference_in_k8_report": True,
        "independent_real_model_execution_proven": False,
        "acceptance_files_verified": True,
        "locked_tracks_verified": locked,
        "midi_type_1_verified": True,
        "inference_elapsed_seconds_reported": seconds,
        "accepted_roles": len(roles_detail),
        "generated_notes": new_note_total,
        "model_attempts_reported": len(attempts),
        "attempt_acceptance_ratio": round(len(roles_detail) / len(attempts), 4),
        "reported_seconds_per_generated_note": round(seconds / new_note_total, 4),
        "roles": roles_detail,
        "smf": smf,
        "cubase_roundtrip": daw_comparison,
        "actual_cubase_gui_operation_verified": False,
        "music_quality_verified_by_human": False,
        "commercial_rights_cleared": False,
        "commercial_release_ready": False,
    }
    _save_new_json(output, summary)
    return summary
