"""K13: opt-in, finite real-model benchmark with honest failure accounting.

Uses K8's real external provider only. Unit tests may stub that function;
those fixtures never count as pretrained inference evidence.
"""
from __future__ import annotations

from collections import Counter
import json
from math import ceil, isfinite
from pathlib import Path
from statistics import mean, median
import time

from .composition_acceptance import run_composition_acceptance
from .composition_planner import make_composition_plan
from .harmony_quality import prepare_harmonic_context
from .io import read_midi
from .part_orchestrator import _expected_programs
from .review_engine import _save_new_json

_ALLOWED = frozenset({
    "id", "prompt", "seed", "programs", "harmonic_key",
    "harmonic_chords", "minimum_structure_score", "minimum_harmony_score",
})
_MAX_CASES = 8
_MAX_TOTAL_CALLS = 96


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def _percentile_p95(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[max(0, ceil(len(values) * 0.95) - 1)], 6)


def load_benchmark_suite(
    suite_path: str | Path, *, source: str | Path,
    locked_tracks: tuple[int, ...], retries: int,
) -> list[dict]:
    """Validate all cases before running an external model or creating output."""
    if type(retries) is not int or not 0 <= retries <= 3:
        raise ValueError("Benchmark retries must be in 0..3.")
    path = Path(suite_path).expanduser().resolve(strict=True)
    if path.suffix.lower() != ".json" or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Benchmark suite must be a small .json file.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid benchmark suite JSON.") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "cases"} or raw["schema_version"] != 1:
        raise ValueError("Benchmark suite must use schema_version 1 and cases.")
    cases = raw["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= _MAX_CASES:
        raise ValueError("Benchmark suite requires 1..8 test cases.")
    src = read_midi(source)
    ids = set()
    validated = []
    budget = 0
    for row in cases:
        if not isinstance(row, dict) or set(row) - _ALLOWED or not {"id", "prompt", "seed"} <= set(row):
            raise ValueError("Invalid benchmark case fields.")
        key = row["id"]
        if not isinstance(key, str) or not 1 <= len(key) <= 32 or not key[0].isascii() or not key[0].isalnum() or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in key):
            raise ValueError("Benchmark case id must be lowercase ASCII and filesystem-safe.")
        if key in ids:
            raise ValueError("Duplicate benchmark case id.")
        ids.add(key)
        seed = row["seed"]
        if type(seed) is not int or not 0 <= seed < 2**31:
            raise ValueError("Benchmark seed must be a 31-bit nonnegative integer.")
        plan = make_composition_plan(
            row["prompt"], source_track_count=len(src.instruments),
            locked_tracks=locked_tracks,
        )
        assignments = row.get("programs", {})
        _expected_programs(plan["parts"], assignments)
        role_count = len(plan["parts"])
        if seed + role_count * (retries + 1) - 1 >= 2**31:
            raise ValueError("Benchmark generated role seeds exceed 31-bit range.")
        budget += role_count * (retries + 1)
        for threshold in ("minimum_structure_score", "minimum_harmony_score"):
            value = row.get(threshold)
            if value is not None and (type(value) not in (float, int) or
                                      not isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"{threshold} must be finite in 0..1.")
        key_text = row.get("harmonic_key")
        chords = row.get("harmonic_chords")
        context = prepare_harmonic_context(key=key_text, chords=chords)
        if row.get("minimum_harmony_score") is not None and context is None:
            raise ValueError("Harmony gate requires explicit chord/key context.")
        validated.append({
            "id": key, "prompt": row["prompt"], "seed": seed,
            "programs": dict(assignments), "roles": [p["role"] for p in plan["parts"]],
            "harmonic_key": key_text, "harmonic_chords": chords,
            "minimum_structure_score": row.get("minimum_structure_score", 0.75),
            "minimum_harmony_score": row.get("minimum_harmony_score"),
        })
    if budget > _MAX_TOTAL_CALLS:
        raise ValueError("Benchmark exceeds worst-case 96 provider calls.")
    return validated


def run_composition_benchmark(
    *,
    confirm_inference: bool = False, suite, output_dir, source, locked_tracks,
    environment, checkout, checkpoint, checkpoint_sha256, vocab, vocab_sha256,
    t5_dir, quality_retries: int = 0, timeout: float = 1800.0,
    temperature: float = 0.9, max_tokens: int = 2000,
    max_total_notes: int = 20000,
    fail_fast: bool = False,
) -> dict:
    """Run 1..8 bounded cases; persist honest failures and per-call timings.

    All successful cases must independently satisfy K8 review. Failures have
    no successful K8 acceptance report, even if intermediate files remain.
    A benchmark report cannot authorize public or commercial release.
    """
    if not confirm_inference:
        raise PermissionError("Benchmark requires --confirm-inference for trusted external model code.")
    if type(locked_tracks) not in (tuple, list) or not locked_tracks:
        raise ValueError("Benchmark requires source track locks.")
    if type(timeout) not in (int, float) or not isfinite(timeout) or not 1 <= timeout <= 7200:
        raise ValueError("Benchmark per-call timeout must be finite in 1..7200 seconds.")
    if type(max_tokens) is not int or not 32 <= max_tokens <= 4096:
        raise ValueError("Benchmark max_tokens must be in 32..4096.")
    if type(max_total_notes) is not int or not 1 <= max_total_notes <= 100000:
        raise ValueError("Benchmark note budget must be in 1..100000.")
    if type(temperature) not in (float, int) or not isfinite(temperature) or not 0.1 <= temperature <= 2:
        raise ValueError("Benchmark temperature must be in 0.1..2.")
    cases = load_benchmark_suite(
        suite, source=source, locked_tracks=tuple(locked_tracks), retries=quality_retries
    )
    root = Path(output_dir).expanduser().resolve()
    if not root.parent.is_dir() or root.exists() or root.is_symlink():
        raise FileExistsError("Benchmark output directory must be NEW with an existing parent.")
    root.mkdir(mode=0o700)

    records = []
    begun = time.monotonic()
    for scenario in cases:
        label = scenario["id"]
        observations = []
        start = time.monotonic()
        entry = {
            "id": label, "seed": scenario["seed"],
            "requested_roles": scenario["roles"],
            "status": "failed", "success": False,
        }
        try:
            accepted = run_composition_acceptance(
                confirm_inference=True,
                environment=environment, checkout=checkout,
                checkpoint=checkpoint, checkpoint_sha256=checkpoint_sha256,
                vocab=vocab, vocab_sha256=vocab_sha256, t5_dir=t5_dir,
                source=source, candidate=root / (label + ".mid"),
                manifest=root / (label + ".proposal.json"),
                report=root / (label + ".acceptance.json"),
                prompt=scenario["prompt"], locked_tracks=list(locked_tracks),
                program_assignments=scenario["programs"],
                seed=scenario["seed"], timeout=timeout, temperature=temperature,
                max_tokens=max_tokens, max_total_notes=max_total_notes,
                quality_retries=quality_retries,
                minimum_structure_score=scenario["minimum_structure_score"],
                harmonic_key=scenario["harmonic_key"],
                harmonic_chords=scenario["harmonic_chords"],
                minimum_harmony_score=scenario["minimum_harmony_score"],
                generation_observer=observations.append,
            )
            attempts = accepted["quality_attempts"]
            if len(observations) != len(attempts) or not attempts:
                raise ValueError("Provider call count disagrees with recorded role attempts.")
            # Each role attempt gets a unique 31-bit seed, so match by seed.
            by_seed = {obs["seed"]: obs for obs in observations}
            parts = []
            for attempt in attempts:
                obs = by_seed.get(attempt["seed"])
                if obs is None or obs["status"] != "returned":
                    raise ValueError("Missing successful provider observation for role attempt.")
                parts.append({
                    "role": attempt["role"], "attempt": attempt["attempt"],
                    "seed": attempt["seed"], "accepted": attempt["accepted"],
                    "model_call_seconds": obs["elapsed_seconds"],
                    "model_output_notes": obs["notes_returned"],
                    "structure_score": attempt["metrics"]["score"] if attempt["metrics"] else None,
                    "harmony_score": attempt["harmony_metrics"]["score"] if attempt["harmony_metrics"] else None,
                    "rejection_reason": attempt["reason"],
                })
            entry.update({
                "status": "passed", "success": True,
                "generated_notes": accepted["new_notes"],
                "inference_seconds_reported_by_k8": accepted["elapsed_seconds"],
                "source_sha256": accepted["source_sha256"],
                "candidate_sha256": accepted["candidate_sha256"],
                "candidate": str(root / (label + ".mid")),
                "manifest": str(root / (label + ".proposal.json")),
                "acceptance_report": str(root / (label + ".acceptance.json")),
                "role_attempts": parts,
                "accepted_role_count": len({x["role"] for x in parts if x["accepted"]}),
            })
        except (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError) as exc:
            # Do not persist raw model stderr or prompts; classification only.
            error_type = type(exc).__name__
            stage = ("external_model_or_adapter" if any(
                x["status"] == "error" for x in observations
            ) else "preflight_or_midi_quality")
            entry.update({
                "error_type": error_type, "failure_stage": stage,
                "partial_output_may_exist": True,
                "model_failure_details_suppressed": True,
                "accepted_role_count": 0,
            })
        entry["case_wall_seconds"] = round(time.monotonic() - start, 6)
        entry["model_calls"] = observations
        records.append(entry)
        if fail_fast and not entry["success"]:
            break

    successful = [r for r in records if r["success"]]
    calls = [c for r in records for c in r["model_calls"]]
    durations = [c["elapsed_seconds"] for c in calls]
    passed_calls = sum(c["status"] == "returned" for c in calls)
    scores = [a["structure_score"] for r in successful
              for a in r["role_attempts"] if a["accepted"] and a["structure_score"] is not None]
    harmonic = [a["harmony_score"] for r in successful
                for a in r["role_attempts"] if a["accepted"] and a["harmony_score"] is not None]
    attempted_roles = sum(len(r["requested_roles"]) for r in records)
    successes = len(successful)
    result = {
        "schema_version": 1, "type": "midivolt_k13_text2midi_benchmark",
        "suite_cases_declared": len(cases), "cases_executed": len(records),
        "execution_stopped_early": len(records) < len(cases),
        "cases_passed": successes, "cases_failed": len(records) - successes,
        "whole_case_success_rate": _ratio(successes, len(records)),
        "complete_case_role_pass_rate": _ratio(
            sum(r["accepted_role_count"] for r in successful), attempted_roles),
        "model_calls_observed": len(calls), "model_calls_returned": passed_calls,
        "model_call_return_rate": _ratio(passed_calls, len(calls)),
        "model_call_duration_mean_seconds": round(mean(durations), 6) if durations else None,
        "model_call_duration_median_seconds": round(median(durations), 6) if durations else None,
        "model_call_duration_p95_seconds": _percentile_p95(durations),
        "successful_case_structure_score_mean": round(mean(scores), 4) if scores else None,
        "successful_case_harmony_score_mean": round(mean(harmonic), 4) if harmonic else None,
        "total_wall_seconds": round(time.monotonic() - begun, 6),
        "failure_types": dict(sorted(Counter(
            r["error_type"] for r in records if not r["success"]
        ).items())),
        "cases": records,
        "real_model_execution_requested_by_operator": True,
        "model_execution_independently_attested": False,
        "hardware_or_gpu_benchmark_certified": False,
        "musical_accuracy_ground_truth_verified": False,
        "commercial_release_ready": False,
    }
    _save_new_json(root / "benchmark.json", result)
    return result
