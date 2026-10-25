"""Independent official E-GMD Validation only: candidate-GENERATING hi-hat lane.

No Test/Train use, model weights, or automatic MIDIVOLT baseline promotion.
The candidate generation parameters, min-coverage and precision guards are
fixed before the new twenty-four song Validation comparison is run.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from collections import Counter
import time

from midivolt.drums import transcribe_drum_wav
from midivolt.hat_subband import HatSubbandConfig, VERSION as SUBBAND_VERSION
from midivolt.hat_validation import _aggregate, CUT21_VALIDATION_SONG_IDS
from midivolt.hat_shape_ablation import CUT23_SONG_IDS
from midivolt.drum_ontology import evaluate_common_ontology

STUDY_REVISION = "dual-subband-candidate-validation-24-v2-metadata-duration"
EXCLUDED_PREVIOUS_SONG_IDS = CUT21_VALIDATION_SONG_IDS | CUT23_SONG_IDS
PRE_REGISTERED_SAMPLE_COUNT = 24
MIN_GM42_EVENTS = 100
MIN_POSITIVE_SONGS = 3
MIN_ZERO_HAT_CONTROLS = 2
MIN_DRUMMERS = 4
MIN_RECALL_DELTA = .03
MIN_GM42_PRECISION = .60
MAX_GM42_PRECISION_DROP = .10
MAX_ALL_PRECISION_DROP = .04

ARMS = {
    "baseline": None,
    "dual_subband": HatSubbandConfig(),
}


def settings_digest() -> str:
    return hashlib.sha256(json.dumps(
        {
            "study_revision": STUDY_REVISION,
            "arm_names": list(ARMS),
            "subband_parameters": asdict(ARMS["dual_subband"]),
            "minimum_reference_gm42_hits": MIN_GM42_EVENTS,
            "minimum_positive_tracks": MIN_POSITIVE_SONGS,
            "negative_control_tracks": MIN_ZERO_HAT_CONTROLS,
            "min_gain": MIN_RECALL_DELTA,
            "precision_floor": MIN_GM42_PRECISION,
            "max_hat_precision_drop": MAX_GM42_PRECISION_DROP,
            "max_all_precision_drop": MAX_ALL_PRECISION_DROP,
            "previous_song_ids": sorted(EXCLUDED_PREVIOUS_SONG_IDS),
        }, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def _validate_cohort(records: list[dict], selection_plan: dict) -> dict:
    if not isinstance(selection_plan, dict):
        raise ValueError("Frozen Validation selection JSON required")
    if selection_plan.get("dataset") != "E-GMD v1.0.0":
        raise ValueError("Expected official E-GMD v1.0.0 metadata")
    if selection_plan.get("upstream_split") != "validation":
        raise ValueError("Cannot score Train or held-out Test on Validation lane")
    if selection_plan.get("study_revision") != STUDY_REVISION:
        raise ValueError("Selection plan study revision not pinned")
    if selection_plan.get("settings_digest") != settings_digest():
        raise ValueError("Subband study settings drifted")
    excluded = selection_plan.get("excluded_previous_song_ids")
    if not isinstance(excluded, list) or set(excluded) != EXCLUDED_PREVIOUS_SONG_IDS or len(excluded) != 12:
        raise ValueError("Must exclude all 12 previously evaluated Validation source songs")
    items = selection_plan.get("selected")
    if not isinstance(items, list) or len(items) != PRE_REGISTERED_SAMPLE_COUNT:
        raise ValueError("Exactly 24 metadata-selected Validation performances required")
    song_ids = [r.get("id") for r in items]
    actual = [r.get("song_id") for r in records]
    if (song_ids != actual or len(set(song_ids)) != len(song_ids)
            or set(song_ids).intersection(EXCLUDED_PREVIOUS_SONG_IDS)):
        raise ValueError("Validation source identities/order changed or old song reused")
    if any(row.get("split") != "validation" for row in items):
        raise ValueError("No Test or Train source may enter this research study")
    drummers = {row.get("drummer") for row in items}
    if len(drummers) < MIN_DRUMMERS:
        raise ValueError("Too few independent drummers")
    if any(row.get("kit_name") != "Acoustic Kit" for row in items):
        raise ValueError("Only pre-registered Acoustic Kit rendering allowed")
    return {
        "songs": len(records),
        "drummers": len(drummers),
        "excluded_prior_validation_source_songs": len(EXCLUDED_PREVIOUS_SONG_IDS),
        "audio_domain": "electronic_kit_recording_NOT_live_acoustic_mics",
        "no_test_leakage": True,
    }


def _note_keys(midi):
    return {
        (n.pitch, round(n.start, 6), round(n.end, 6))
        for inst in midi.instruments if inst.is_drum for n in inst.notes
    }


def evaluate_candidate_generator(
    records: list[dict], selection_plan: dict, *, transcriber=transcribe_drum_wav,
) -> dict:
    provenance = _validate_cohort(records, selection_plan)
    results = {name: [] for name in ARMS}
    per_song = []
    for record in records:
        track = {
            "song_id": record["song_id"],
            "reference_gm42": sum(
                n.pitch == 42 for ins in record["truth"].instruments
                for n in ins.notes if ins.is_drum
            ),
        }
        predictions = {}
        for name, settings in ARMS.items():
            started = time.perf_counter()
            midi, info = transcriber(
                record["wav"], hat_subband_config=settings
            )
            elapsed = time.perf_counter() - started
            score = evaluate_common_ontology(
                record["truth"], midi, prediction_namespace="gm",
            )
            predictions[name] = midi
            results[name].append({
                "song_id": record["song_id"], "seconds": elapsed,
                "result": score,
            })
            hat = score["per_class"].get("42", {})
            track[name] = {
                "tp": hat.get("tp", 0),
                "fp": hat.get("fp", 0),
                "fn": hat.get("fn", 0),
                "new_candidates": (
                    info.get("subband_candidates", {}).get("new_candidates", 0)
                    if name == "dual_subband" else 0
                ),
            }
        original = _note_keys(predictions["baseline"])
        enhanced = _note_keys(predictions["dual_subband"])
        if not original.issubset(enhanced):
            raise ValueError("Subband research lane removed/moved baseline MIDI notes")
        if any(pitch != 42 for pitch, _, _ in enhanced-original):
            raise ValueError("Subband research lane changed non-GM42 note events")
        track["added_unique_gm42_notes"] = len(enhanced-original)
        per_song.append(track)

    summaries = {k: _aggregate(v) for k,v in results.items()}
    controls = [row for row in per_song if row["reference_gm42"] == 0]
    positive = [row for row in per_song if row["reference_gm42"] > 0]
    annotated = sum(row["reference_gm42"] for row in per_song)
    negative_fps = {
        arm: sum(row[arm]["fp"] for row in controls) for arm in ARMS
    }
    coverage_ok = (
        len(controls) >= MIN_ZERO_HAT_CONTROLS
        and len(positive) >= MIN_POSITIVE_SONGS
        and annotated >= MIN_GM42_EVENTS
    )
    baseline = summaries["baseline"]
    candidate = summaries["dual_subband"]
    recall_gain = round(
        candidate["closed_hi_hat"]["recall"] -
        baseline["closed_hi_hat"]["recall"], 6
    )
    blocked = []
    if not coverage_ok:
        blocked.append("insufficient_pre_registered_positive_and_negative_control_coverage")
    if recall_gain < MIN_RECALL_DELTA:
        blocked.append("insufficient_closed_hi_hat_recall_gain")
    if candidate["closed_hi_hat"]["precision"] < max(
        MIN_GM42_PRECISION,
        baseline["closed_hi_hat"]["precision"] - MAX_GM42_PRECISION_DROP,
    ):
        blocked.append("closed_hat_precision_below_guardrail")
    if candidate["total"]["precision"] < (
        baseline["total"]["precision"] - MAX_ALL_PRECISION_DROP
    ):
        blocked.append("total_precision_below_guardrail")
    if negative_fps["dual_subband"] > negative_fps["baseline"]:
        blocked.append("new_false_gm42_on_zero_hat_negative_controls")
    decision = {
        "status": (
            "validation_only_candidate_NOT_production"
            if not blocked else "retain_production_baseline"
        ),
        "blocked_by": blocked,
        "hat_recall_absolute_delta": recall_gain,
        "original_dsp_preset_modified": False,
        "official_test_scores_untouched": True,
    }
    return {
        "schema_version": "1",
        "study_revision": STUDY_REVISION,
        "feature_version": SUBBAND_VERSION,
        "settings_digest": settings_digest(),
        "dataset": "E-GMD v1.0.0",
        "partition": "official_validation_only",
        "provenance": provenance,
        "reference_gm42_count": annotated,
        "positive_song_count": len(positive),
        "zero_hat_control_song_count": len(controls),
        "zero_hat_false_predictions_by_arm": negative_fps,
        "summary_by_arm": summaries,
        "per_song": per_song,
        "decision": decision,
        "commercial_ready": False,
        "production_dsp_default_unchanged": True,
        "interpretation": (
            "Candidate-generating arm can recover missed hats but must also "
            "pass independent Precision and no-hat negative-control gates."
        ),
    }
