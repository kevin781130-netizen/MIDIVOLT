"""Frozen Train-fitted Hi-hat ranker versus raw proposals on NEW Validation.

Separate performance IDs across 24 official TRAIN sequences and 12
Validation sequences not present in any previous Cut21/23/25/26 study.
All three arms see identical WAVs/true MIDI for event-level 50ms scoring.
No hyperparameter/threshold selection on Validation; no Test access.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import time

from midivolt.drums import transcribe_drum_wav
from midivolt.hat_candidate_ranker import HatRankerModel
from midivolt.hat_subband import HatSubbandConfig
from midivolt.hat_candidate_confidence_validation import EXCLUSIONS as PAST_36
from midivolt.drum_ontology import evaluate_common_ontology
from midivolt.hat_validation import _aggregate

REVISION = "cut28-train-ranker-independent-validation-v1"
CUT26_PLAN_SHA256 = "7ca54be3db2a48f54f7bf71c6791327f5bec7a9aeeeeeb396d8e0fe87d5bfcd9"
CUT26_SOURCE_SONG_IDS = frozenset((
    "drummer5/session1/11", "drummer8/session1/18",
    "drummer6/session3/4", "drummer7/session3/11",
    "drummer1/session2/142", "drummer1/session3/15",
    "drummer5/session2/22", "drummer7/session2/27",
    "drummer6/session3/5", "drummer5/session2/15",
    "drummer1/session1/126", "drummer7/session1/13",
    "drummer7/session3/155", "drummer1/session1/41",
    "drummer1/session2/25", "drummer7/session2/73",
    "drummer1/session2/185", "drummer7/session3/70",
    "drummer1/session1/59", "drummer7/session1/33",
    "drummer1/session2/57", "drummer7/session2/62",
    "drummer1/session2/134", "drummer7/session2/10",
))
PREVIOUS_VAL_IDS = PAST_36 | CUT26_SOURCE_SONG_IDS
TRAIN_COUNT = 24
VALIDATION_COUNT = 12
MIN_POSITIVE_TRAIN_CANDIDATES = 10
MIN_GM42_TRUTH = 100
MIN_GM42_POSITIVE_SONGS = 3
MIN_ZERO_GM42_CONTROL_SONGS = 2
MIN_GM42_RECALL_GAIN = 0.03
MIN_NEW_EVENT_PRECISION = 0.60
MIN_ALL_GM42_PRECISION = 0.60
MAX_HAT_PRECISION_DROP = 0.10
MAX_ALL_PRECISION_DROP = 0.04


def protocol_digest() -> str:
    return hashlib.sha256(json.dumps({
        "revision": REVISION,
        "cut26_sha256": CUT26_PLAN_SHA256,
        "previous_val_songs": sorted(PREVIOUS_VAL_IDS),
        "train_count": TRAIN_COUNT,
        "validation_count": VALIDATION_COUNT,
        "ranker_training_threshold": 0.80,
        "minimums": [
            MIN_GM42_TRUTH, MIN_GM42_POSITIVE_SONGS, MIN_ZERO_GM42_CONTROL_SONGS,
            MIN_GM42_RECALL_GAIN, MIN_NEW_EVENT_PRECISION,
            MIN_ALL_GM42_PRECISION, MAX_HAT_PRECISION_DROP, MAX_ALL_PRECISION_DROP,
        ],
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _note_events(midi):
    return {
        (n.pitch, round(n.start, 7), round(n.end, 7))
        for tr in midi.instruments if tr.is_drum for n in tr.notes
    }


def evaluate_unseen(
    records: list[dict], plan: dict, model: HatRankerModel,
    *, transcriber=transcribe_drum_wav,
) -> dict:
    if not isinstance(model, HatRankerModel) or model.training_split != "train":
        raise ValueError("Only TRAIN-fitted verified ranker is permitted")
    if (not isinstance(plan, dict)
            or plan.get("dataset") != "E-GMD v1.0.0"
            or plan.get("upstream_split") != "validation"
            or plan.get("protocol_digest") != protocol_digest()
            or plan.get("revision") != REVISION):
        raise ValueError("Independent Validation protocol or dataset changed")
    if (plan.get("excluded_previous_val_ids") != sorted(PREVIOUS_VAL_IDS)
            or len(PREVIOUS_VAL_IDS) != 60):
        raise ValueError("Must exclude all 60 previously evaluated Validation source songs")
    selected = plan.get("selected")
    if (not isinstance(selected, list) or len(selected) != VALIDATION_COUNT
            or len(records) != VALIDATION_COUNT
            or [r.get("id") for r in selected] != [r.get("song_id") for r in records]):
        raise ValueError("Validation source identities/count mismatch")
    identities = [row["id"] for row in selected]
    if len(set(identities)) != VALIDATION_COUNT or set(identities) & PREVIOUS_VAL_IDS:
        raise ValueError("Old/duplicated Validation performance reused")
    if any(row.get("split") != "validation"
           or row.get("kit_name") != "Acoustic Kit" for row in selected):
        raise ValueError("Only official Validation Acoustic Kit recordings allowed")
    if len({row.get("drummer") for row in selected}) < 3:
        raise ValueError("Too few independent drummers in validation")
    if (plan.get("train_manifest_sha256") != model.training_manifest_sha256
            or plan.get("train_contributing_songs") != model.source_songs
            or plan.get("train_source_count") != TRAIN_COUNT):
        raise ValueError("Train model was not fitted to declared TRAIN source manifest")
    source_songs = plan.get("train_source_song_ids")
    if (not isinstance(source_songs, list) or len(source_songs) != TRAIN_COUNT
            or len(set(source_songs)) != TRAIN_COUNT or set(source_songs) & set(identities)):
        raise ValueError("Train/Validation source-song leakage")
    if not 4 <= model.source_songs <= TRAIN_COUNT:
        raise ValueError("TRAIN contributing performances outside valid source count")

    arms = {
        "baseline": {"hat_subband_config": None, "hat_ranker_model": None},
        "raw_subband": {"hat_subband_config": HatSubbandConfig(), "hat_ranker_model": None},
        "trained_ranker": {"hat_subband_config": HatSubbandConfig(), "hat_ranker_model": model},
    }
    results = {name: [] for name in arms}
    per_song = []
    for record in records:
        row = {
            "source_song_id": record["song_id"],
            "reference_gm42": sum(
                n.pitch == 42 for t in record["truth"].instruments
                if t.is_drum for n in t.notes
            ),
        }
        predictions = {}
        for name, opts in arms.items():
            start = time.perf_counter()
            predicted, info = transcriber(record["wav"], **opts)
            scored = evaluate_common_ontology(
                record["truth"], predicted, prediction_namespace="gm",
            )
            results[name].append({
                "song_id": record["song_id"], "seconds": time.perf_counter()-start,
                "result": scored,
            })
            predictions[name] = predicted
            hat = scored["per_class"].get("42", {})
            row[name] = {k: hat.get(k, 0) for k in ("tp", "fp", "fn")}
            row[name]["new_candidates"] = (
                info.get("subband_candidates", {}).get("new_candidates", 0)
                if isinstance(info, dict) else 0
            )
        baseline_events = _note_events(predictions["baseline"])
        raw_events = _note_events(predictions["raw_subband"])
        ranker_events = _note_events(predictions["trained_ranker"])
        if (not baseline_events.issubset(ranker_events)
                or not ranker_events.issubset(raw_events)
                or not baseline_events.issubset(raw_events)):
            raise ValueError("Trained ranker must retain baseline and filter only raw new candidates")
        if any(event[0] != 42 for event in raw_events-baseline_events):
            raise ValueError("Raw generator altered non-GM42 MIDI notes")
        row["raw_added_events"] = len(raw_events-baseline_events)
        row["ranker_kept_added_events"] = len(ranker_events-baseline_events)
        per_song.append(row)

    summary = {name: _aggregate(scores) for name, scores in results.items()}
    truth_count = sum(row["reference_gm42"] for row in per_song)
    positive_tracks = sum(row["reference_gm42"] > 0 for row in per_song)
    negative_tracks = sum(row["reference_gm42"] == 0 for row in per_song)
    control_false = {
        name: sum(row[name]["fp"] for row in per_song
                  if row["reference_gm42"] == 0)
        for name in arms
    }
    original = summary["baseline"]
    improved = summary["trained_ranker"]
    raw = summary["raw_subband"]
    tp_delta = improved["closed_hi_hat"]["tp"]-original["closed_hi_hat"]["tp"]
    fp_delta = improved["closed_hi_hat"]["fp"]-original["closed_hi_hat"]["fp"]
    if tp_delta < 0 or fp_delta < 0:
        raise ValueError("Incremental proposal unexpectedly degraded baseline TP/FP")
    marginal_precision = tp_delta/(tp_delta+fp_delta) if tp_delta+fp_delta else 0.0
    recall_gain = improved["closed_hi_hat"]["recall"]-original["closed_hi_hat"]["recall"]
    blocked = []
    if truth_count < MIN_GM42_TRUTH or positive_tracks < MIN_GM42_POSITIVE_SONGS or negative_tracks < MIN_ZERO_GM42_CONTROL_SONGS:
        blocked.append("insufficient_reference_or_negative_control_coverage")
    if recall_gain < MIN_GM42_RECALL_GAIN:
        blocked.append("insufficient_recall_gain")
    if marginal_precision < MIN_NEW_EVENT_PRECISION:
        blocked.append("marginal_new_event_precision_below_60_percent")
    if improved["closed_hi_hat"]["precision"] < max(
        MIN_ALL_GM42_PRECISION, original["closed_hi_hat"]["precision"] - MAX_HAT_PRECISION_DROP,
    ):
        blocked.append("hat_precision_guard")
    if improved["total"]["precision"] < original["total"]["precision"] - MAX_ALL_PRECISION_DROP:
        blocked.append("all_drum_precision_guard")
    if control_false["trained_ranker"] > control_false["baseline"]:
        blocked.append("new_false_hat_on_zero_reference_control")
    return {
        "schema_version": "1",
        "revision": REVISION,
        "protocol_digest": protocol_digest(),
        "train_model_sha256": hashlib.sha256(json.dumps(
            model.to_dict(), sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest(),
        "train_manifest_sha256": model.training_manifest_sha256,
        "dataset": "E-GMD v1.0.0",
        "partition": "official_unseen_validation_only",
        "cohort": {
            "val_songs": len(records), "train_songs": len(source_songs),
            "excluded_old_val_songs": len(PREVIOUS_VAL_IDS),
            "drummers": len({row["drummer"] for row in selected}),
            "reference_gm42": truth_count,
            "gm42_positive_songs": positive_tracks,
            "zero_gm42_control_songs": negative_tracks,
            "source_domain": "Roland-electronic-rendered drums, not live acoustic mics",
        },
        "scores": summary,
        "zero_hat_control_false_positives": control_false,
        "new_event_metrics": {
            "raw_tp_gain": raw["closed_hi_hat"]["tp"]-original["closed_hi_hat"]["tp"],
            "raw_fp_gain": raw["closed_hi_hat"]["fp"]-original["closed_hi_hat"]["fp"],
            "ranker_tp_gain": tp_delta, "ranker_fp_gain": fp_delta,
            "ranker_marginal_precision": round(marginal_precision, 6),
            "ranker_absolute_recall_gain": round(recall_gain, 6),
            "raw_candidates_added": sum(r["raw_added_events"] for r in per_song),
            "ranker_candidates_kept": sum(r["ranker_kept_added_events"] for r in per_song),
        },
        "per_song": per_song,
        "decision": {
            "status": "research_candidate_only_NOT_beta" if not blocked else "retain_production_baseline",
            "blocked_by": blocked,
            "production_default_modified": False,
            "official_test_scored": False,
        },
        "commercial_distribution_approved": False,
    }
