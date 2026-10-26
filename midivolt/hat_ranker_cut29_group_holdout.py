"""Cut29: preregistered TRAIN-only, drummer-disjoint scaling experiment.

Compare 24-vs-72 official TRAIN song rankers on exactly the same
24-song TRAIN-internal, HELD-OUT-DRUMMER evaluation set. NEVER describe
these metrics as official E-GMD Validation or TEST performance.
Metadata-only source selection precedes WAV/MIDI access and scoring.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from dataclasses import asdict
import hashlib
import json
import math
import time

from midivolt.drums import transcribe_drum_wav
from midivolt.hat_candidate_ranker import HatRankerModel
from midivolt.hat_ranker_independent_eval import (
    MIN_GM42_TRUTH, MIN_GM42_POSITIVE_SONGS, MIN_ZERO_GM42_CONTROL_SONGS,
    MIN_GM42_RECALL_GAIN, MIN_NEW_EVENT_PRECISION,
    MIN_ALL_GM42_PRECISION, MAX_HAT_PRECISION_DROP, MAX_ALL_PRECISION_DROP,
)
from midivolt.hat_subband import HatSubbandConfig
from midivolt.drum_ontology import evaluate_common_ontology
from midivolt.hat_validation import _aggregate

REVISION = "cut29-train96-drummer-disjoint-scaling-v1"
METADATA_SEED = "midivolt-cut29-drummer-holdout-preselected-v1"
FIT_SONGS = 72
SMALL_SONGS = 24
GROUP_HOLDOUT_SONGS = 24
FIT_BEATS = 48
HOLDOUT_BEATS = 12
HOLDOUT_DRUMMERS = 2
MAX_DURATION_S = 90


def _stable_key(prefix: str, identity: str) -> str:
    return hashlib.sha256((METADATA_SEED + "|" + prefix + "|" + identity).encode()).hexdigest()


def study_digest() -> str:
    return hashlib.sha256(json.dumps({
        "revision": REVISION, "seed": METADATA_SEED,
        "fit_songs": FIT_SONGS, "small_songs": SMALL_SONGS,
        "holdout_songs": GROUP_HOLDOUT_SONGS,
        "fit_beats": FIT_BEATS, "holdout_beats": HOLDOUT_BEATS,
        "holdout_drummers": HOLDOUT_DRUMMERS,
        "max_duration_s": MAX_DURATION_S,
        "model_threshold": .80,
        "metrics": [
            MIN_GM42_TRUTH, MIN_GM42_POSITIVE_SONGS, MIN_ZERO_GM42_CONTROL_SONGS,
            MIN_GM42_RECALL_GAIN, MIN_NEW_EVENT_PRECISION,
            MIN_ALL_GM42_PRECISION, MAX_HAT_PRECISION_DROP, MAX_ALL_PRECISION_DROP
        ],
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _choose(rows: list[dict], count: int, *, prefix: str) -> list[dict]:
    """Select by source-song metadata and drummer/style diversity only."""
    if len(rows) < count:
        raise ValueError(f"Not enough metadata-only {prefix} source recordings")
    pool = list(rows)
    picked = []
    drummer = Counter()
    style = Counter()
    for _ in range(count):
        def key(x):
            genre = x["style"].split("/")[0]
            return (
                drummer[x["drummer"]]*20 + style[genre]*7,
                _stable_key(prefix, x["id"]), x["id"],
            )
        x = min(pool, key=key)
        picked.append(x)
        drummer[x["drummer"]] += 1
        style[x["style"].split("/")[0]] += 1
        pool.remove(x)
    return picked


def choose_metadata_partition(rows: list[dict]) -> dict:
    """One-and-only metadata-only grouping, no candidate or ground truth peek."""
    seen_split = {}
    by_id = {}
    for x in rows:
        identity = x.get("id")
        if not isinstance(identity, str) or not identity:
            continue
        split = x.get("split")
        if identity in seen_split and seen_split[identity] != split:
            raise ValueError("Original song ID belongs to multiple upstream splits")
        seen_split[identity] = split
        if (split != "train" or x.get("kit_name") != "Acoustic Kit"
                or x.get("beat_type") not in ("beat", "fill")):
            continue
        try:
            length = float(x.get("duration", ""))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(length) or not 0 < length <= MAX_DURATION_S:
            continue
        if not x.get("drummer") or not x.get("style"):
            continue
        if identity in by_id and x["audio_filename"] != by_id[identity]["audio_filename"]:
            raise ValueError("Conflicting official Acoustic Kit source recordings")
        by_id[identity] = x
    pool = list(by_id.values())
    groups = {}
    for x in pool:
        groups.setdefault(x["drummer"], []).append(x)
    drummers = sorted(groups)
    eligible = []
    for pair in combinations(drummers, HOLDOUT_DRUMMERS):
        test = [r for d in pair for r in groups[d]]
        fit = [r for r in pool if r["drummer"] not in pair]
        test_type = Counter(x["beat_type"] for x in test)
        fit_type = Counter(x["beat_type"] for x in fit)
        if (test_type["beat"] >= HOLDOUT_BEATS
                and test_type["fill"] >= GROUP_HOLDOUT_SONGS-HOLDOUT_BEATS
                and fit_type["beat"] >= FIT_BEATS
                and fit_type["fill"] >= FIT_SONGS-FIT_BEATS
                and len({x["drummer"] for x in fit}) >= 4):
            eligible.append(pair)
    if not eligible:
        raise ValueError("No drummer-disjoint TRAIN-only metadata groups satisfy both strata")
    withheld = min(eligible, key=lambda pair: (_stable_key("holdout_drummers", "|".join(pair)), pair))
    fit_pool = [x for x in pool if x["drummer"] not in withheld]
    hold_pool = [x for x in pool if x["drummer"] in withheld]
    fit_rows = _choose(
        [x for x in fit_pool if x["beat_type"] == "beat"], FIT_BEATS, prefix="fit-beats",
    ) + _choose(
        [x for x in fit_pool if x["beat_type"] == "fill"], FIT_SONGS-FIT_BEATS, prefix="fit-fills",
    )
    hold_rows = _choose(
        [x for x in hold_pool if x["beat_type"] == "beat"], HOLDOUT_BEATS, prefix="holdout-beats",
    ) + _choose(
        [x for x in hold_pool if x["beat_type"] == "fill"],
        GROUP_HOLDOUT_SONGS-HOLDOUT_BEATS, prefix="holdout-fills",
    )
    # Small subset frozen before training labels; 16 beats + 8 fills.
    small = _choose(
        [x for x in fit_rows if x["beat_type"] == "beat"], 16, prefix="small-beats",
    ) + _choose(
        [x for x in fit_rows if x["beat_type"] == "fill"], 8, prefix="small-fills",
    )
    fit_ids = {x["id"] for x in fit_rows}
    hold_ids = {x["id"] for x in hold_rows}
    if (len(fit_ids) != FIT_SONGS or len(hold_ids) != GROUP_HOLDOUT_SONGS
            or len({x["id"] for x in small}) != SMALL_SONGS
            or not {x["id"] for x in small}.issubset(fit_ids)
            or fit_ids.intersection(hold_ids)
            or {x["drummer"] for x in fit_rows}.intersection(
                {x["drummer"] for x in hold_rows}
            )):
        raise RuntimeError("Source-song/drummer independence failed")
    return {
        "dataset": "E-GMD v1.0.0", "upstream_split": "train",
        "revision": REVISION, "protocol_digest": study_digest(),
        "sample_selection": "public_metadata_only_before_wav_midi_or_model_scores",
        "heldout_drummers": list(withheld),
        "fit": fit_rows, "small": small, "holdout": hold_rows,
    }


def _events(midi):
    return {
        (n.pitch, round(n.start, 7), round(n.end, 7))
        for tr in midi.instruments if tr.is_drum for n in tr.notes
    }


def compare_models(
    records: list[dict], plan: dict,
    small: HatRankerModel, full: HatRankerModel,
    *, transcriber=transcribe_drum_wav,
) -> dict:
    """Drummer-disjoint TRAIN-internal evaluation; not official Validation."""
    if not isinstance(plan, dict) or plan.get("revision") != REVISION or plan.get("protocol_digest") != study_digest():
        raise ValueError("Frozen TRAIN-only study protocol changed")
    if plan.get("upstream_split") != "train":
        raise ValueError("Only original E-GMD TRAIN permitted in group-holdout evaluation")
    fit = plan.get("fit")
    hold = plan.get("holdout")
    subset = plan.get("small")
    if (not all(isinstance(x, list) for x in (fit, hold, subset))
            or (len(fit), len(hold), len(subset)) != (FIT_SONGS, GROUP_HOLDOUT_SONGS, SMALL_SONGS)):
        raise ValueError("Frozen 72/24/24 source-song allocation missing")
    fit_ids = [x["id"] for x in fit]
    hold_ids = [x["id"] for x in hold]
    small_ids = [x["id"] for x in subset]
    if (len(set(fit_ids)) != FIT_SONGS
            or len(set(hold_ids)) != GROUP_HOLDOUT_SONGS
            or not set(small_ids).issubset(fit_ids)
            or len(set(small_ids)) != SMALL_SONGS
            or set(fit_ids) & set(hold_ids)
            or {x["drummer"] for x in fit} & {x["drummer"] for x in hold}
            or set(plan.get("heldout_drummers", [])) != {x["drummer"] for x in hold}):
        raise ValueError("TRAIN fit/holdout has source-song or drummer leakage")
    if (len(records) != GROUP_HOLDOUT_SONGS
            or [r.get("song_id") for r in records] != hold_ids
            or any(x.get("split") != "train" for x in hold)):
        raise ValueError("Internal holdout data changed/incorrect original upstream split")
    if not isinstance(small, HatRankerModel) or not isinstance(full, HatRankerModel):
        raise ValueError("Both models must be fitted from official TRAIN-only examples")
    if not small.source_songs <= SMALL_SONGS or not full.source_songs <= FIT_SONGS:
        raise ValueError("Model source count exceeds declared TRAIN fit population")

    arms = {
        "baseline": {"hat_subband_config": None, "hat_ranker_model": None},
        "raw_subband": {"hat_subband_config": HatSubbandConfig(), "hat_ranker_model": None},
        "small_24_ranker": {"hat_subband_config": HatSubbandConfig(), "hat_ranker_model": small},
        "expanded_72_ranker": {"hat_subband_config": HatSubbandConfig(), "hat_ranker_model": full},
    }
    scores = {name: [] for name in arms}
    detail = []
    for rec in records:
        name = rec["song_id"]
        row = {
            "source_song_id": name,
            "drummer": next(x["drummer"] for x in hold if x["id"] == name),
            "reference_gm42": sum(
                n.pitch == 42 for inst in rec["truth"].instruments
                if inst.is_drum for n in inst.notes
            ),
        }
        prediction_notes = {}
        for key, opts in arms.items():
            start = time.perf_counter()
            pred, _ = transcriber(rec["wav"], **opts)
            metrics = evaluate_common_ontology(
                rec["truth"], pred, prediction_namespace="gm",
            )
            scores[key].append({
                "song_id": name, "seconds": time.perf_counter()-start,
                "result": metrics,
            })
            hits = metrics["per_class"].get("42", {})
            row[key] = {k: hits.get(k, 0) for k in ("tp", "fp", "fn")}
            prediction_notes[key] = _events(pred)
        baseline = prediction_notes["baseline"]
        raw = prediction_notes["raw_subband"]
        if not baseline.issubset(raw):
            raise ValueError("Raw candidate arm modified original notes")
        for learner in ("small_24_ranker", "expanded_72_ranker"):
            output = prediction_notes[learner]
            if not baseline.issubset(output) or not output.issubset(raw):
                raise ValueError("Learned ranker may only filter added GM42 notes")
        if any(pitch != 42 for pitch, _, _ in raw-baseline):
            raise ValueError("Raw subband modified non-GM42 notes")
        detail.append(row)
    summary = {arm: _aggregate(values) for arm, values in scores.items()}
    gm_truth = sum(row["reference_gm42"] for row in detail)
    positive_tracks = sum(x["reference_gm42"] > 0 for x in detail)
    negative_tracks = sum(x["reference_gm42"] == 0 for x in detail)
    base = summary["baseline"]
    def relative(arm):
        arm_score = summary[arm]
        tp = arm_score["closed_hi_hat"]["tp"]-base["closed_hi_hat"]["tp"]
        fp = arm_score["closed_hi_hat"]["fp"]-base["closed_hi_hat"]["fp"]
        if tp < 0 or fp < 0:
            raise ValueError("New-only candidate arm unexpectedly changed base TP/FP")
        prec = tp/(tp+fp) if tp+fp else 0.0
        recall_delta = arm_score["closed_hi_hat"]["recall"]-base["closed_hi_hat"]["recall"]
        controls = [
            x for x in detail if x["reference_gm42"] == 0
        ]
        new_control_fp = sum(x[arm]["fp"]-x["baseline"]["fp"] for x in controls)
        blockers = []
        if (gm_truth < MIN_GM42_TRUTH or positive_tracks < MIN_GM42_POSITIVE_SONGS
                or negative_tracks < MIN_ZERO_GM42_CONTROL_SONGS):
            blockers.append("insufficient_true_hats_or_negative_control_tracks")
        if recall_delta < MIN_GM42_RECALL_GAIN:
            blockers.append("recall_gain_below_predeclared_threshold")
        if prec < MIN_NEW_EVENT_PRECISION:
            blockers.append("new_candidate_precision_below_60_percent")
        if arm_score["closed_hi_hat"]["precision"] < max(
            MIN_ALL_GM42_PRECISION, base["closed_hi_hat"]["precision"]-MAX_HAT_PRECISION_DROP
        ):
            blockers.append("overall_hat_precision_guard")
        if arm_score["total"]["precision"] < base["total"]["precision"]-MAX_ALL_PRECISION_DROP:
            blockers.append("all_drum_precision_guard")
        if new_control_fp > 0:
            blockers.append("new_false_hats_on_zero_hat_negative_controls")
        return {
            "additional_tp": tp, "additional_fp": fp,
            "marginal_precision": round(prec, 6),
            "absolute_recall_gain": round(recall_delta, 6),
            "negative_control_fp_increase": new_control_fp,
            "blocked_by": blockers, "research_criteria_met": not blockers,
        }

    arms_eval = {k: relative(k) for k in arms if k != "baseline"}
    return {
        "schema_version": "1", "revision": REVISION,
        "protocol_digest": study_digest(),
        "source_split": "official_train_internal_holdout_NOT_validation_or_test",
        "not_an_official_validation_result": True,
        "trained_model_threshold": .80,
        "train_sources": {
            "small_selected": SMALL_SONGS, "expanded_selected": FIT_SONGS,
            "small_contributing": small.source_songs,
            "expanded_contributing": full.source_songs,
            "small_positive": small.positive_examples,
            "expanded_positive": full.positive_examples,
            "small_negative": small.negative_examples,
            "expanded_negative": full.negative_examples,
        },
        "holdout": {
            "source_songs": GROUP_HOLDOUT_SONGS,
            "drummers": list(plan["heldout_drummers"]),
            "reference_gm42": gm_truth,
            "positive_songs": positive_tracks,
            "no_hat_control_songs": negative_tracks,
        },
        "score_by_arm": summary, "incremental": arms_eval,
        "per_song": detail,
        "decision": {
            "status": "TRAIN_INTERNAL_RESEARCH_ONLY_not_for_release",
            "expanded_passes_internal_gates": arms_eval["expanded_72_ranker"]["research_criteria_met"],
            "production_dsp_unchanged": True,
            "official_validation_and_test_not_scored": True,
            "no_model_weights_shared": True,
        },
        "commercial_beta_approved": False,
    }
