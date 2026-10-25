"""K14 independent offline replay of K13 suite results and successful K8 MIDI.

This checks JSON/statistical consistency and replays K9's actual MIDI
integrity/quality inspections. It is NOT attestation that trained model
weights ran, a musical judgement, or a commercial-license clearance.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from math import ceil, isfinite
from pathlib import Path
from statistics import mean, median

from .composition_audit import audit_composition_acceptance
from .review_engine import _save_new_json


def _load(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("Benchmark and doctor reports must be JSON objects.")
    return obj


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def _same(label: str, actual, expected) -> None:
    if type(actual) is not type(expected) or actual != expected:
        raise ValueError("K13 benchmark aggregation mismatch: " + label)


def _rate(a: int, b: int):
    return round(a / b, 4) if b else None


def _average(values: list[float], places: int):
    return round(mean(values), places) if values else None


def _p95(values):
    return round(sorted(values)[ceil(len(values) * .95) - 1], 6) if values else None


def verify_benchmark_evidence(
    benchmark_report: str | Path, *, output_dir: str | Path,
    doctor_report: str | Path | None = None,
) -> dict:
    """Recalculate K13 metrics and run K9 audit for each passing case.

    No model is called; existing K8/K13 assets remain unmodified. A fresh
    directory is created; the final verification.json is written only if all
    relevant file/summary checks pass. Failed real-model cases remain failed.
    """
    benchmark_path = Path(benchmark_report).expanduser().resolve(strict=True)
    report = _load(benchmark_path)
    if report.get("schema_version") != 1 or report.get("type") != "midivolt_k13_text2midi_benchmark":
        raise ValueError("Requires an existing K13 Text2midi benchmark.json report.")
    if report.get("real_model_execution_requested_by_operator") is not True:
        raise ValueError("K13 report does not claim explicit operator consent.")
    if report.get("model_execution_independently_attested") is not False:
        raise ValueError("K13 report must not claim independent real-model attestation.")
    if report.get("commercial_release_ready") is not False:
        raise ValueError("K13 report cannot clear commercial rights.")
    cases = report.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 8:
        raise ValueError("K13 report must contain 1..8 executed cases.")
    if type(report.get("suite_cases_declared")) is not int or not len(cases) <= report["suite_cases_declared"] <= 8:
        raise ValueError("Invalid declared suite case count.")
    _same("executed count", report.get("cases_executed"), len(cases))
    _same("stopped early", report.get("execution_stopped_early"),
          len(cases) < report["suite_cases_declared"])
    output = Path(output_dir).expanduser().resolve()
    if not output.parent.is_dir() or output.exists() or output.is_symlink():
        raise FileExistsError("K14 output directory must be NEW under an existing parent.")
    if output == benchmark_path.parent or benchmark_path.is_relative_to(output):
        raise ValueError("K14 output must be separate from the input reports.")

    doctor = None
    doctor_path = None
    if doctor_report is not None:
        doctor_path = Path(doctor_report).expanduser().resolve(strict=True)
        if doctor_path == benchmark_path:
            raise ValueError("Doctor and benchmark must be different files.")
        doctor = _load(doctor_path)
        if doctor.get("kind") != "midivolt_k12_text2midi_preinference_doctor":
            raise ValueError("Supplied doctor report is not a K12 preflight record.")
        if doctor.get("ready_for_inference_attempt") is not True or doctor.get("commercial_release_ready") is not False:
            raise ValueError("K12 doctor has not cleared the runtime preflight.")
        if doctor.get("runtime", {}).get("third_party_packages_imported") is not True:
            raise ValueError("K12 package imports were not actually verified.")

    seen = set()
    calls = []
    passed = []
    rejected = []
    accepted_role_count = 0
    requested_role_count = 0
    structural_scores = []
    harmonic_scores = []
    failure_types = Counter()
    source_sha = None
    checkpoint_sha = None
    vocabulary_sha = None
    upstream_commit = None
    requirements_sha = None
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Malformed K13 case entry.")
        label = case.get("id")
        if (not isinstance(label, str) or not 1 <= len(label) <= 32 or
                label[0] not in "abcdefghijklmnopqrstuvwxyz0123456789" or
                any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in label) or
                label in seen):
            raise ValueError("Unsafe or duplicate benchmark case id.")
        seen.add(label)
        if type(case.get("seed")) is not int or not 0 <= case["seed"] < 2**31:
            raise ValueError("Malformed K13 case seed.")
        roles = case.get("requested_roles")
        if not isinstance(roles, list) or not roles or any(type(x) is not str for x in roles) or len(set(roles)) != len(roles):
            raise ValueError("Malformed requested role list.")
        requested_role_count += len(roles)
        logs = case.get("model_calls")
        if not isinstance(logs, list) or len(logs) > 96:
            raise ValueError("Invalid per-case provider event log.")
        for obs in logs:
            if not isinstance(obs, dict) or obs.get("status") not in ("returned", "error"):
                raise ValueError("Malformed model call event.")
            t = obs.get("elapsed_seconds")
            if type(t) not in (float, int) or not isfinite(t) or t < 0:
                raise ValueError("Invalid model call duration.")
            if obs["status"] == "returned":
                if (type(obs.get("notes_returned")) is not int or obs["notes_returned"] < 0
                        or type(obs.get("tracks_returned")) is not int or obs["tracks_returned"] < 0):
                    raise ValueError("Malformed returned MIDI event counters.")
            calls.append(obs)
        if case.get("success") is True and case.get("status") == "passed":
            if case.get("error_type") is not None:
                raise ValueError("Successful K13 case contains an exception.")
            path = benchmark_path.parent / (label + ".acceptance.json")
            declared = case.get("acceptance_report")
            if not isinstance(declared, str) or Path(declared).resolve() != path.resolve():
                raise ValueError("K13 acceptance report path differs from fixed case artifact.")
            if not path.is_file():
                raise FileNotFoundError("Successful K13 case lacks an acceptance report.")
            verified = _load(path)
            for field, previous in (
                ("source_sha256", source_sha),
                ("checkpoint_sha256", checkpoint_sha),
                ("vocab_sha256", vocabulary_sha),
                ("upstream_commit", upstream_commit),
                ("requirements_sha256", requirements_sha),
            ):
                present = verified.get(field)
                if not isinstance(present, str) or not present:
                    raise ValueError("K8 acceptance lacks provenance: " + field)
                if previous is not None and present != previous:
                    raise ValueError("Successful benchmark cases use different model/source assets.")
            source_sha = verified["source_sha256"]
            checkpoint_sha = verified["checkpoint_sha256"]
            vocabulary_sha = verified["vocab_sha256"]
            upstream_commit = verified["upstream_commit"]
            requirements_sha = verified["requirements_sha256"]
            if doctor is not None:
                for field, expected in (("checkpoint_sha256", checkpoint_sha),
                                        ("vocab_sha256", vocabulary_sha),
                                        ("upstream_commit", upstream_commit),
                                        ("requirements_sha256", requirements_sha)):
                    if doctor.get(field) != expected:
                        raise ValueError("K12/K8 model provenance mismatch: " + field)
            passed.append((case, path))
        elif case.get("success") is False and case.get("status") == "failed":
            if type(case.get("error_type")) is not str or not case["error_type"]:
                raise ValueError("Failed case must record an exception class.")
            if case.get("accepted_role_count") != 0:
                raise ValueError("Failed case cannot claim accepted output roles.")
            if (benchmark_path.parent / (label + ".acceptance.json")).is_file():
                raise ValueError("Failed case has an unexpected successful K8 acceptance record.")
            failure_types[case["error_type"]] += 1
            rejected.append({"id": label, "error_type": case["error_type"]})
        else:
            raise ValueError("K13 case success/status flags disagree.")

    if len(calls) > 96:
        raise ValueError("K13 provider call count exceeds suite budget.")
    _same("cases passed", report.get("cases_passed"), len(passed))
    _same("cases failed", report.get("cases_failed"), len(rejected))
    _same("whole-case success rate", report.get("whole_case_success_rate"), _rate(len(passed), len(cases)))
    _same("observed call count", report.get("model_calls_observed"), len(calls))
    returned = sum(obs["status"] == "returned" for obs in calls)
    _same("returned call count", report.get("model_calls_returned"), returned)
    _same("model call return rate", report.get("model_call_return_rate"), _rate(returned, len(calls)))
    _same("failure classification", report.get("failure_types"), dict(sorted(failure_types.items())))
    durations = [c["elapsed_seconds"] for c in calls]
    _same("call mean", report.get("model_call_duration_mean_seconds"), _average(durations, 6))
    _same("call median", report.get("model_call_duration_median_seconds"),
          round(median(durations), 6) if durations else None)
    _same("call p95", report.get("model_call_duration_p95_seconds"), _p95(durations))

    # Only now create the output; all summary-only errors fail before any new files.
    output.mkdir(mode=0o700)
    per_case = []
    for case, path in passed:
        label = case["id"]
        audit = audit_composition_acceptance(path, output_path=output / (label + ".audit.json"))
        expected_roles = [r["role"] for r in audit["roles"]]
        if expected_roles != case["requested_roles"] or audit["accepted_roles"] != case.get("accepted_role_count"):
            raise ValueError("K8/K9 role metadata does not match K13 benchmark.")
        if (audit["candidate_sha256"] != case.get("candidate_sha256")
                or audit["source_sha256"] != case.get("source_sha256")
                or audit["generated_notes"] != case.get("generated_notes")):
            raise ValueError("K8/K9 note counts or MIDI hashes disagree with K13 benchmark.")
        if Path(case.get("candidate", "")).resolve() != benchmark_path.parent / (label + ".mid"):
            raise ValueError("K13 candidate path does not match the case artifact.")
        if Path(case.get("manifest", "")).resolve() != benchmark_path.parent / (label + ".proposal.json"):
            raise ValueError("K13 manifest path does not match the case artifact.")
        parts = case.get("role_attempts")
        if not isinstance(parts, list) or len(parts) != len(audit["roles"]) + sum(
                not a.get("accepted") for a in parts if isinstance(a, dict)):
            raise ValueError("Malformed K13 role attempt list.")
        accepted_roles = [a for a in parts if isinstance(a, dict) and a.get("accepted") is True]
        if [a.get("role") for a in accepted_roles] != expected_roles:
            raise ValueError("K13 accepted role ordering differs from MIDI audit.")
        original_attempts = _load(path).get("quality_attempts")
        if len(original_attempts) != len(parts):
            raise ValueError("K13/K8 model retry count differs.")
        for idx, item in enumerate(parts):
            k8 = original_attempts[idx]
            if (item.get("role") != k8["role"] or item.get("seed") != k8["seed"]
                    or item.get("attempt") != k8["attempt"] or item.get("accepted") is not k8["accepted"]
                    or item.get("rejection_reason") != k8["reason"] or
                    item.get("structure_score") != (k8["metrics"]["score"] if k8["metrics"] else None) or
                    item.get("harmony_score") != (k8["harmony_metrics"]["score"] if k8["harmony_metrics"] else None)):
                raise ValueError("K13 role attempt diagnostics differ from K8.")
            if item.get("model_call_seconds") is None or not any(
                event.get("seed") == item["seed"] and event.get("status") == "returned"
                and event.get("elapsed_seconds") == item["model_call_seconds"]
                for event in case["model_calls"]
            ):
                raise ValueError("K13 role timings differ from observed provider events.")
        accepted_role_count += audit["accepted_roles"]
        structural_scores.extend(x["structural_score"] for x in audit["roles"])
        harmonic_scores.extend(x["harmony_score"] for x in audit["roles"]
                               if x["harmony_score"] is not None)
        per_case.append({
            "id": label, "candidate_sha256": audit["candidate_sha256"],
            "notes": audit["generated_notes"], "roles": expected_roles,
            "audit": str(output / (label + ".audit.json")),
            "independent_midi_replay_completed": True,
        })
    _same("complete-case role pass rate", report.get("complete_case_role_pass_rate"),
          _rate(accepted_role_count, requested_role_count))
    _same("accepted structural score mean", report.get("successful_case_structure_score_mean"),
          _average(structural_scores, 4))
    _same("accepted harmony score mean", report.get("successful_case_harmony_score_mean"),
          _average(harmonic_scores, 4))

    result = {
        "schema_version": 1,
        "kind": "midivolt_k14_replayed_k13_benchmark",
        "k13_benchmark_sha256": _digest(benchmark_path),
        "k12_doctor_sha256": _digest(doctor_path) if doctor_path else None,
        "cases_declared": report["suite_cases_declared"],
        "cases_checked": len(cases),
        "cases_accepted": len(passed),
        "cases_rejected": len(rejected),
        "full_suite_completed": len(cases) == report["suite_cases_declared"],
        "all_cases_accepted": len(rejected) == 0 and len(cases) == report["suite_cases_declared"],
        "file_and_metric_replay_consistent": True,
        "accepted_cases": per_case,
        "rejected_cases": rejected,
        "k12_model_runtime_bound": doctor is not None,
        "external_model_execution_independently_verified": False,
        "cubase_application_verified": False,
        "human_listening_verified": False,
        "commercial_rights_cleared": False,
        "commercial_release_ready": False,
    }
    _save_new_json(output / "verification.json", result)
    return result
