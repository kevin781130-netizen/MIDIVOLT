"""Independent E-GMD Validation-only audit for NEW Hi-hat candidate confidence.

Compare baseline, raw candidate generator, and the SAME generator with a
frozen, deterministic rejection-only classifier. 24 independent recordings
must not overlap ANY of the 36 earlier E-GMD Validation recordings.
No official Test or training-on-evaluation; no automatic production changes.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import time

from midivolt.drums import transcribe_drum_wav
from midivolt.hat_subband import HatSubbandConfig
from midivolt.hat_candidate_confidence import HatCandidateConfidence, VERSION
from midivolt.hat_validation import _aggregate
from midivolt.hat_subband_validation import EXCLUDED_PREVIOUS_SONG_IDS
from midivolt.drum_ontology import evaluate_common_ontology

REVISION = "candidate-confidence-independent-24-v1"
OLD_CUT25_PLAN_SHA256 = "ebbda038cbc8b4902ff2d05e8ac5bbc8288be179cad38a00246aa01df71e6fb7"
CUT25_SONG_IDS = frozenset((
    "drummer1/session1/196", "drummer1/session1/2",
    "drummer1/session1/257", "drummer1/session1/38",
    "drummer1/session1/62", "drummer1/session2/150",
    "drummer1/session2/79", "drummer3/session1/37",
    "drummer3/session1/7", "drummer3/session2/25",
    "drummer3/session2/5", "drummer4/session1/2",
    "drummer4/session1/5", "drummer6/session1/4",
    "drummer6/session3/1", "drummer7/session1/14",
    "drummer7/session2/113", "drummer7/session2/14",
    "drummer7/session2/70", "drummer7/session2/82",
    "drummer7/session2/91", "drummer7/session2/96",
    "drummer7/session3/22", "drummer7/session3/88",
))
EXCLUSIONS = EXCLUDED_PREVIOUS_SONG_IDS | CUT25_SONG_IDS
TOTAL_SONGS = 24
MIN_DRUMMERS = 4
MIN_HAT_EVENTS = 100
MIN_HAT_POSITIVE_SONGS = 3
MIN_NO_HAT_CONTROLS = 2
MIN_RECALL_GAIN = .03
MIN_NEW_EVENT_PRECISION = .60
MIN_OVERALL_HAT_PRECISION = .60
MAX_HAT_PRECISION_DROP = .10
MAX_ALL_PRECISION_DROP = .04

ARMS = {
    "baseline": (None, None),
    "raw_subband": (HatSubbandConfig(), None),
    "confidence_subband": (HatSubbandConfig(), HatCandidateConfidence()),
}


def settings_digest() -> str:
    payload = json.dumps({
        "revision": REVISION,
        "cut25_sha256": OLD_CUT25_PLAN_SHA256,
        "excluded_ids": sorted(EXCLUSIONS),
        "arms": [[name, asdict(c) if c else None, asdict(g) if g else None]
                 for name, (c, g) in ARMS.items()],
        "thresholds": {
            "min_drummer": MIN_DRUMMERS, "min_hat_events": MIN_HAT_EVENTS,
            "min_positive_songs": MIN_HAT_POSITIVE_SONGS,
            "min_negative_songs": MIN_NO_HAT_CONTROLS,
            "min_recall_gain": MIN_RECALL_GAIN,
            "min_new_event_precision": MIN_NEW_EVENT_PRECISION,
            "min_hat_precision": MIN_OVERALL_HAT_PRECISION,
            "max_hat_drop": MAX_HAT_PRECISION_DROP,
            "max_total_drop": MAX_ALL_PRECISION_DROP,
        }
    }, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _verified_cohort(records: list[dict], plan: dict) -> dict:
    if not isinstance(plan, dict) or plan.get("dataset") != "E-GMD v1.0.0":
        raise ValueError("Expected official E-GMD v1.0.0 selection plan")
    if plan.get("upstream_split") != "validation":
        raise ValueError("Only Validation allowed; no Train or Test")
    if plan.get("study_revision") != REVISION or plan.get("settings_digest") != settings_digest():
        raise ValueError("Study version/settings not frozen")
    if plan.get("original_cut25_selection_sha256") != OLD_CUT25_PLAN_SHA256:
        raise ValueError("Previous selection evidence not pinned")
    excluded = plan.get("excluded_previous_song_ids")
    if (not isinstance(excluded, list) or len(excluded) != 36
            or set(excluded) != EXCLUSIONS):
        raise ValueError("Must exclude all 36 previously used Validation performances")
    selected = plan.get("selected")
    if not isinstance(selected, list) or len(selected) != TOTAL_SONGS or len(records) != TOTAL_SONGS:
        raise ValueError("Need exactly 24 new official Validation songs")
    ids = [x.get("id") for x in selected]
    if (ids != [x.get("song_id") for x in records]
            or len(set(ids)) != len(ids) or set(ids) & EXCLUSIONS):
        raise ValueError("Source-song identity mismatch or repeated Validation performances")
    if any(x.get("split") != "validation" or x.get("kit_name") != "Acoustic Kit" for x in selected):
        raise ValueError("Unapproved dataset split or electronic drum kit")
    drummers = {x.get("drummer") for x in selected}
    if len(drummers) < MIN_DRUMMERS or any(not x for x in drummers):
        raise ValueError("Insufficient independent drummers")
    return {"songs": len(records), "drummers": len(drummers), "past_songs_excluded": len(EXCLUSIONS),
            "partition": "official_validation", "electronic_kit_not_live_mic": True}


def _note_events(midi) -> set[tuple[int, float, float]]:
    return {
        (n.pitch, round(n.start, 7), round(n.end, 7))
        for track in midi.instruments if track.is_drum for n in track.notes
    }


def evaluate_confidence_study(records: list[dict], plan: dict, *, transcriber=transcribe_drum_wav) -> dict:
    provenance = _verified_cohort(records, plan)
    results = {key: [] for key in ARMS}
    per_song = []
    for rec in records:
        row = {
            "song_id": rec["song_id"],
            "reference_gm42": sum(
                n.pitch == 42 for inst in rec["truth"].instruments if inst.is_drum for n in inst.notes
            ),
        }
        sounds = {}
        for name, (config, confidence) in ARMS.items():
            started = time.perf_counter()
            pred, detail = transcriber(
                rec["wav"],
                hat_subband_config=config,
                hat_candidate_confidence=confidence,
            )
            scored = evaluate_common_ontology(rec["truth"], pred, prediction_namespace="gm")
            results[name].append({
                "song_id": rec["song_id"], "seconds": time.perf_counter()-started,
                "result": scored,
            })
            sounds[name] = pred
            hat = scored["per_class"].get("42", {})
            row[name] = {
                key: hat.get(key, 0) for key in ("tp", "fp", "fn")
            }
            row[name]["new_candidates"] = (
                detail.get("subband_candidates", {}).get("new_candidates", 0)
            )
            row[name]["confidence_rejected"] = (
                detail.get("subband_candidates", {}).get("candidate_confidence", {}).get("rejected", 0)
            )

        a = _note_events(sounds["baseline"])
        b = _note_events(sounds["raw_subband"])
        c = _note_events(sounds["confidence_subband"])
        if not a.issubset(c) or not c.issubset(b) or not a.issubset(b):
            raise ValueError("Confidence must retain baseline and only filter newly generated notes")
        if any(pitch != 42 for pitch, _, _ in b-a):
            raise ValueError("Candidate confidence study changed non-GM42 note events")
        row["raw_added_notes"] = len(b-a)
        row["confidence_kept_notes"] = len(c-a)
        row["confidence_removed_notes"] = len(b-c)
        per_song.append(row)

    summaries = {name: _aggregate(group) for name, group in results.items()}
    positives = [r for r in per_song if r["reference_gm42"]]
    controls = [r for r in per_song if not r["reference_gm42"]]
    annotated = sum(r["reference_gm42"] for r in per_song)
    control_false = {
        name: sum(r[name]["fp"] for r in controls) for name in ARMS
    }
    baseline = summaries["baseline"]
    confident = summaries["confidence_subband"]
    raw = summaries["raw_subband"]
    added_tp = confident["closed_hi_hat"]["tp"] - baseline["closed_hi_hat"]["tp"]
    added_fp = confident["closed_hi_hat"]["fp"] - baseline["closed_hi_hat"]["fp"]
    if added_tp < 0 or added_fp < 0:
        raise ValueError("New-candidate-only logic changed baseline TP/FP totals")
    added_precision = (added_tp/(added_tp+added_fp) if added_tp+added_fp else 0.0)
    recall_gain = confident["closed_hi_hat"]["recall"] - baseline["closed_hi_hat"]["recall"]

    blockers = []
    if len(positives) < MIN_HAT_POSITIVE_SONGS or len(controls) < MIN_NO_HAT_CONTROLS or annotated < MIN_HAT_EVENTS:
        blockers.append("insufficient_hihat_ground_truth_or_negative_control_coverage")
    if recall_gain < MIN_RECALL_GAIN:
        blockers.append("insufficient_recall_improvement")
    if added_precision < MIN_NEW_EVENT_PRECISION:
        blockers.append("poor_marginal_precision_of_new_notes")
    if confident["closed_hi_hat"]["precision"] < max(
        MIN_OVERALL_HAT_PRECISION,
        baseline["closed_hi_hat"]["precision"] - MAX_HAT_PRECISION_DROP,
    ):
        blockers.append("overall_closed_hat_precision_guard")
    if confident["total"]["precision"] < baseline["total"]["precision"] - MAX_ALL_PRECISION_DROP:
        blockers.append("all_drum_precision_guard")
    if control_false["confidence_subband"] > control_false["baseline"]:
        blockers.append("new_false_closed_hats_in_negative_controls")

    return {
        "schema_version": "1",
        "study_revision": REVISION,
        "feature_version": VERSION,
        "settings_digest": settings_digest(),
        "dataset": "E-GMD v1.0.0",
        "partition": "validation_only",
        "provenance": provenance,
        "reference_closed_hat_count": annotated,
        "closed_hat_positive_tracks": len(positives),
        "no_hat_control_tracks": len(controls),
        "negative_control_false_hats": control_false,
        "all_drum_summary_by_arm": summaries,
        "raw_vs_filtered_hat": {
            "raw_new_true_hits": raw["closed_hi_hat"]["tp"]-baseline["closed_hi_hat"]["tp"],
            "raw_new_false_hits": raw["closed_hi_hat"]["fp"]-baseline["closed_hi_hat"]["fp"],
            "confident_new_true_hits": added_tp,
            "confident_new_false_hits": added_fp,
            "confident_new_note_precision": round(added_precision, 6),
            "confident_recall_delta": round(recall_gain, 6),
            "candidates_rejected": sum(r["confidence_removed_notes"] for r in per_song),
        },
        "per_song": per_song,
        "decision": {
            "status": ("validation_candidate_not_production"
                       if not blockers else "retain_original_DSP_baseline"),
            "blocked_by": blockers,
            "current_release_unmodified": True,
            "historical_test_scores_unmodified": True,
        },
        "commercial_beta_ready": False,
        "note": "No Test scoring, no automatic promotion, no trained model weights.",
    }
