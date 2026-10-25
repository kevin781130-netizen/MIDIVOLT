"""Post-hoc Conservative Hi-hat shape ABLATION on frozen Cut-23 Validation.

This is an attribution diagnostic, NOT a new Validation cohort, hyperparameter
search, confirmation study, or release recommendation. Run both arms on the
identical WAV/MIDI pair. Verify exact old Conservative+shape counts before
reporting. No official TEST content, no pretrained AI, no automatic promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from midivolt.drums import transcribe_drum_wav
from midivolt.drum_ontology import evaluate_common_ontology
from midivolt.hat_validation import PRESETS, _aggregate, validate_validation_manifest
from midivolt.hat_shape import HatShapeGate, FEATURE_VERSION
from midivolt.hat_shape_validation import (
    _assert_fresh_cohort, STUDY_ARMS, study_sha256,
)

CUT23_PLAN_SHA256 = "4a3ddeb8c0e4b75a15a65a06e5e78574afa2352d0a287092f223481b52139d6e"
CUT23_SONG_IDS = frozenset({
    "drummer3/session1/41", "drummer7/session2/100",
    "drummer3/session1/15", "drummer7/session2/46",
    "drummer7/session2/16", "drummer1/session1/7",
})
ABLATON_VERSION = "conservative-shape-causal-ablation-v1"
ARMS = {
    "conservative_unfiltered": (PRESETS["conservative"], None),
    "conservative_shape": (PRESETS["conservative"], HatShapeGate()),
}


def _checksum(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _events(midi) -> set[tuple[int, float, float, int]]:
    return {
        (n.pitch, round(n.start, 7), round(n.end, 7), n.velocity)
        for inst in midi.instruments for n in inst.notes if inst.is_drum
    }


def _counts(section: dict) -> tuple[int, int, int]:
    return tuple(section[k] for k in ("tp", "fp", "fn"))


def run_ablation(
    records: list[dict], selection_plan: dict, previous: dict,
    *,
    plan_sha256: str,
    transcriber=transcribe_drum_wav,
) -> dict:
    if plan_sha256 != CUT23_PLAN_SHA256:
        raise ValueError("Old Cut-23 plan byte hash mismatch; not the frozen cohort")
    provenance = _assert_fresh_cohort(selection_plan, records)
    if {r["song_id"] for r in records} != CUT23_SONG_IDS:
        raise ValueError("Replay must use the exact six Cut-23 performance IDs")
    if (
        previous.get("study_version") != "hat-shape-validation-r1-frozen"
        or previous.get("preset_sha256") != study_sha256()
        or previous.get("feature_version") != FEATURE_VERSION
        or previous.get("upstream_partition") != "validation"
        or previous.get("sample_count") != len(records)
        or set(previous.get("summary_by_arm", {})) != set(STUDY_ARMS)
    ):
        raise ValueError("Invalid historical Cut-23 results or changed feature revision")
    all_scores = {arm: [] for arm in ARMS}
    negative_controls: list[str] = []
    event_changes = []
    for rec in records:
        ident = rec["song_id"]
        has_hat = any(
            n.pitch == 42 for inst in rec["truth"].instruments for n in inst.notes
        )
        if not has_hat:
            negative_controls.append(ident)
        midi_by_arm = {}
        for arm, (hat_config, shape_config) in ARMS.items():
            start = time.perf_counter()
            prediction, info = transcriber(
                rec["wav"], hat_config=hat_config, hat_shape_gate=shape_config,
            )
            scores = evaluate_common_ontology(
                rec["truth"], prediction, prediction_namespace="gm"
            )
            all_scores[arm].append({
                "song_id": ident, "seconds": time.perf_counter()-start,
                "result": scores,
            })
            midi_by_arm[arm] = prediction
        ungated = _events(midi_by_arm["conservative_unfiltered"])
        gated = _events(midi_by_arm["conservative_shape"])
        removed = ungated - gated
        added = gated - ungated
        if added:
            raise ValueError("Opt-in gate added or altered MIDI notes; expected filter only")
        if any(note[0] != 42 for note in removed):
            raise ValueError("Shape gate altered Kick/Snare/non-GM42 MIDI notes")
        event_changes.append({
            "source_song_id": ident, "reference_contains_gm42": has_hat,
            "unfiltered_gm42_events": sum(event[0] == 42 for event in ungated),
            "shape_gm42_events": sum(event[0] == 42 for event in gated),
            "shape_removed_gm42_events": len(removed),
            "changed_other_instrument_events": False,
            "unfiltered_gm42_tp_fp_fn": _counts(all_scores["conservative_unfiltered"][-1]["result"]["per_class"].get("42", {"tp":0,"fp":0,"fn":0})),
            "shape_gm42_tp_fp_fn": _counts(all_scores["conservative_shape"][-1]["result"]["per_class"].get("42", {"tp":0,"fp":0,"fn":0})),
        })

    summaries = {arm: _aggregate(group) for arm, group in all_scores.items()}
    original = previous["summary_by_arm"]["conservative_shape"]
    for key in ("total", "closed_hi_hat"):
        if _counts(original[key]) != _counts(summaries["conservative_shape"][key]):
            raise ValueError("Conservative+shape score drift: cannot attribute ablation safely")
    if not negative_controls:
        raise ValueError("No reference-zero-Hi-hat negative-control songs")
    def summed(arm: str) -> dict:
        selected = all_scores[arm]
        return {
            "false_gm42_on_negative_controls": sum(
                item["result"]["per_class"].get("42", {}).get("fp", 0)
                for item in selected if item["song_id"] in negative_controls
            ),
        }
    original_hat = summaries["conservative_unfiltered"]["closed_hi_hat"]
    new_hat = summaries["conservative_shape"]["closed_hi_hat"]
    delta = {
        "hat_tp": new_hat["tp"] - original_hat["tp"],
        "hat_fp": new_hat["fp"] - original_hat["fp"],
        "hat_fn": new_hat["fn"] - original_hat["fn"],
        "hat_recall": round(new_hat["recall"] - original_hat["recall"], 6),
        "hat_precision": round(new_hat["precision"] - original_hat["precision"], 6),
        "hat_f1": round(new_hat["f1"] - original_hat["f1"], 6),
        "other_instrument_changes": 0,
        "hat_events_removed": sum(r["shape_removed_gm42_events"] for r in event_changes),
    }
    if delta["hat_tp"] == delta["hat_fp"] == delta["hat_fn"] == 0 and not delta["hat_events_removed"]:
        interpretation = "no_observed_effect_of_shape_feature_on_this_cohort"
    elif delta["hat_tp"] <= 0 and delta["hat_fp"] <= 0:
        interpretation = "filter_removed_hat_candidates_check_tp_fp_tradeoff"
    else:
        interpretation = "unexpected_difference_review_before_claim"
    return {
        "schema_version": "1",
        "study": ABLATON_VERSION,
        "dataset": "E-GMD v1.0.0",
        "partition": "validation_only_reused_Cut23_cohort",
        "original_selection_plan_sha256": plan_sha256,
        "original_study_digest": study_sha256(),
        "cohort_proof": provenance,
        "reference_hat_event_count": (
            new_hat["tp"] + new_hat["fn"]
        ),
        "negative_control_song_ids": sorted(negative_controls),
        "summaries": summaries,
        "negative_controls": {arm: summed(arm) for arm in ARMS},
        "shape_minus_unfiltered": delta,
        "per_song_differences": event_changes,
        "interpretation": interpretation,
        "prior_conservative_shape_scores_exactly_reproduced": True,
        "independent_confirmation": False,
        "candidate_promotion_allowed": False,
        "production_default_unchanged": True,
        "note": "Retrospective same-data ablation; NOT independent proof of superiority or Test accuracy.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--selection-plan", type=Path, required=True)
    parser.add_argument("--original-metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        records = validate_validation_manifest(args.manifest)
        report = run_ablation(
            records,
            json.loads(args.selection_plan.read_text(encoding="utf-8")),
            json.loads(args.original_metrics.read_text(encoding="utf-8")),
            plan_sha256=_checksum(args.selection_plan),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, PermissionError) as exc:
        parser.exit(1, f"ABLATED COMPARISON BLOCKED: {exc}\n")
    print(json.dumps({
        "interpretation": report["interpretation"],
        "shape_minus_unfiltered": report["shape_minus_unfiltered"],
        "report": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
