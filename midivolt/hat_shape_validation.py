"""Frozen DSP Hi-hat spectral-shape A/B on NEW E-GMD Validation songs.

This experiment is deliberately separate from the six Validation recordings
used by the prior threshold-only study. Supply a manifest prepared with
--exclude-plan pointing to that historical selection plan. Nothing auto-promotes
to production; the official Test partition and historical scores are untouched.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

from midivolt.drums import HatDetectionConfig, transcribe_drum_wav
from midivolt.hat_shape import HatShapeGate, FEATURE_VERSION
from midivolt.drum_ontology import evaluate_common_ontology
from midivolt.hat_validation import (
    _aggregate, validate_validation_manifest, PRESETS,
    MIN_HAT_RECALL_GAIN, MIN_HAT_PRECISION_ABSOLUTE,
    MAX_HAT_PRECISION_DROP, MAX_ALL_PRECISION_DROP,
)

SHAPE_STUDY_VERSION = "hat-shape-validation-r1-frozen"
STUDY_ARMS = {
    "baseline": (PRESETS["baseline"], None),
    "moderate_unfiltered": (PRESETS["moderate"], None),
    "moderate_shape": (PRESETS["moderate"], HatShapeGate()),
    "conservative_shape": (PRESETS["conservative"], HatShapeGate()),
}
MIN_SONG_COUNT = 6


def study_sha256() -> str:
    src = json.dumps(
        [
            [name, asdict(hat), asdict(shape) if shape else None]
            for name, (hat, shape) in STUDY_ARMS.items()
        ],
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(src).hexdigest()


def _assert_fresh_cohort(selection_plan: dict, records: list[dict]) -> dict:
    if not isinstance(selection_plan, dict):
        raise ValueError("Missing official Validation shape-study selection plan")
    if (selection_plan.get("dataset") != "E-GMD v1.0.0"
            or selection_plan.get("upstream_split") != "validation"
            or selection_plan.get("excludes_previous_validation_experiments") is not True):
        raise ValueError("New cohort must exclude previous Validation performances")
    excluded = selection_plan.get("excluded_previous_validation_source_song_ids")
    selected = selection_plan.get("samples")
    if not isinstance(excluded, list) or not excluded or not isinstance(selected, list):
        raise ValueError("No frozen historical exclusions or new selection list")
    if len(excluded) != len(set(excluded)):
        raise ValueError("Invalid duplicate exclusions in selection plan")
    identities = {item.get("id") for item in selected}
    seen = {r.get("song_id") for r in records}
    if identities != seen or len(selected) != len(records) or len(seen) != len(records):
        raise ValueError("Manifest WAV/MIDI does not match frozen source-song selection plan")
    if identities.intersection(excluded):
        raise ValueError("Reused previous Validation performance; refuse post-hoc feature fitting")
    if len(records) < MIN_SONG_COUNT:
        raise ValueError("At least six new independent Validation recordings required")
    return {
        "new_song_count": len(records),
        "previous_validation_songs_excluded": len(excluded),
        "zero_previous_songs_reused": True,
    }


def _recommend(scores: dict, controls: dict) -> dict:
    base = scores["baseline"]
    prior_recall = base["closed_hi_hat"]["recall"]
    prior_hat_precision = base["closed_hi_hat"]["precision"]
    prior_total_precision = base["total"]["precision"]
    if base["closed_hi_hat"]["tp"] + base["closed_hi_hat"]["fn"] == 0:
        return {"status": "blocked_missing_closed_hat_ground_truth"}
    if controls["song_count"] == 0:
        return {"status": "blocked_missing_no_hat_negative_control"}

    evaluations = []
    for name in STUDY_ARMS:
        if name == "baseline":
            continue
        current = scores[name]
        gain = current["closed_hi_hat"]["recall"] - prior_recall
        hat_precision = current["closed_hi_hat"]["precision"]
        total_precision = current["total"]["precision"]
        additional_control_fp = (
            controls["false_gm42_by_arm"][name]
            - controls["false_gm42_by_arm"]["baseline"]
        )
        reasons = []
        if gain < MIN_HAT_RECALL_GAIN:
            reasons.append("hat_recall_gain_below_pre_registered_minimum")
        if hat_precision < max(MIN_HAT_PRECISION_ABSOLUTE,
                               prior_hat_precision - MAX_HAT_PRECISION_DROP):
            reasons.append("hat_precision_below_guardrail")
        if total_precision < prior_total_precision - MAX_ALL_PRECISION_DROP:
            reasons.append("overall_precision_below_guardrail")
        if additional_control_fp > 0:
            reasons.append("new_false_closed_hat_on_negative_controls")
        evaluations.append({
            "name": name,
            "absolute_hat_recall_delta": round(gain, 6),
            "false_hat_negative_control_delta": additional_control_fp,
            "passes": not reasons,
            "blocked_by": reasons,
        })
    eligible = [x for x in evaluations if x["passes"] and x["name"].endswith("_shape")]
    if not eligible:
        return {
            "status": "retain_production_baseline",
            "reason": "No spectral-shape candidate passes all predeclared limits",
            "comparisons": evaluations,
        }
    rank = list(STUDY_ARMS)
    best = max(eligible, key=lambda x: (
        x["absolute_hat_recall_delta"],
        scores[x["name"]]["closed_hi_hat"]["f1"],
        -rank.index(x["name"]),
    ))
    return {
        "status": "validation_only_candidate_not_auto_applied",
        "candidate": best["name"],
        "comparisons": evaluations,
    }


def evaluate_shape_study(
    records: list[dict],
    *,
    selection_plan: dict,
    transcriber=transcribe_drum_wav,
) -> dict:
    provenance = _assert_fresh_cohort(selection_plan, records)
    results = {key: [] for key in STUDY_ARMS}
    control_songs = sorted(
        rec["song_id"] for rec in records
        if not any(
            n.pitch == 42
            for ins in rec["truth"].instruments for n in ins.notes
        )
    )
    for rec in records:
        for name, (hat, shape) in STUDY_ARMS.items():
            started = time.perf_counter()
            prediction, details = transcriber(
                rec["wav"], hat_config=hat, hat_shape_gate=shape,
            )
            elapsed = time.perf_counter() - started
            result = evaluate_common_ontology(
                rec["truth"], prediction, prediction_namespace="gm"
            )
            results[name].append({
                "song_id": rec["song_id"],
                "seconds": elapsed,
                "result": result,
                "shape_candidate_rejected": (
                    details.get("shape_gate", {}).get("rejected_candidates")
                    if isinstance(details, dict) else None
                ),
            })
    summary = {name: _aggregate(items) for name, items in results.items()}
    negatives = {
        "song_ids": control_songs,
        "song_count": len(control_songs),
        "false_gm42_by_arm": {
            name: sum(
                x["result"]["per_class"].get("42", {}).get("fp", 0)
                for x in samples if x["song_id"] in control_songs
            )
            for name, samples in results.items()
        },
    }
    # Most tracks do contain Hi-hat; never invent a negative-control result.
    decision = _recommend(summary, negatives)
    return {
        "schema_version": "1",
        "study_version": SHAPE_STUDY_VERSION,
        "feature_version": FEATURE_VERSION,
        "preset_sha256": study_sha256(),
        "dataset": "E-GMD v1.0.0",
        "upstream_partition": "validation",
        "audio_domain": "electronic_kit_recording",
        "new_cohort_proof": provenance,
        "sample_count": len(records),
        "pre_registered_min_hat_recall_gain": MIN_HAT_RECALL_GAIN,
        "pre_registered_max_hat_precision_drop": MAX_HAT_PRECISION_DROP,
        "pre_registered_max_total_precision_drop": MAX_ALL_PRECISION_DROP,
        "pre_registered_min_hat_precision": MIN_HAT_PRECISION_ABSOLUTE,
        "summary_by_arm": summary,
        "negative_control": negatives,
        "decision": decision,
        "production_dsp_default_unchanged": True,
        "official_test_partition_not_touched": True,
        "claim": "Validation-only research; no full-GM export or acoustic mic accuracy claim.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--selection-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        records = validate_validation_manifest(args.manifest)
        plan = json.loads(args.selection_plan.read_text(encoding="utf-8"))
        report = evaluate_shape_study(records, selection_plan=plan)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, RuntimeError, PermissionError) as exc:
        parser.exit(1, f"FROZEN HI-HAT SHAPE STUDY BLOCKED: {exc}\n")
    print(json.dumps({
        "decision": report["decision"]["status"],
        "sample_count": report["sample_count"],
        "metrics": str(args.output),
        "production_default_unchanged": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
