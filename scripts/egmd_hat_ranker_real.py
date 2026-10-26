"""Single CPU-only E-GMD Cut28: fit TRAIN, score disjoint Validation.

Never touches official TEST, old 60 Validation songs or external model
weights. Both selections use official CSV metadata BEFORE examining
new WAVs, reference MIDI labels or any scores. The private fitted model
and media remain ONLY in local runner storage; CI uploads scores/provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from collections import Counter

import pretty_midi

from midivolt.egmd_import import read_metadata
from midivolt.drum_suite import _normalize_reference
from midivolt.hat_validation import choose_validation_metadata, validate_validation_manifest
from midivolt.hat_ranker_training import read_train_manifest, source_features
from midivolt.hat_candidate_ranker import fit_ranker, HatRankerModel
from midivolt.hat_ranker_independent_eval import (
    REVISION, CUT26_PLAN_SHA256, CUT26_SOURCE_SONG_IDS, PREVIOUS_VAL_IDS,
    TRAIN_COUNT, VALIDATION_COUNT, protocol_digest, evaluate_unseen,
)
from scripts.egmd_mini_real import (
    ZIP_URL, get_small_csv, preflight_ranges, acquire_selected,
)

OFFICIAL_URL = "https://magenta.withgoogle.com/datasets/e-gmd"
SEED_TRAIN = "midivolt-cut28-train-source-selection-r1"
SEED_VALIDATION = "midivolt-cut28-unseen-validation-source-selection-r1"


def verify_cut26_old_plan(path: Path) -> None:
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != CUT26_PLAN_SHA256:
        raise ValueError("Authentic Cut26 plan SHA-256 mismatch")
    previous = json.loads(data)
    if (
        previous.get("dataset") != "E-GMD v1.0.0"
        or previous.get("upstream_split") != "validation"
        or not isinstance(previous.get("selected"), list)
        or len(previous["selected"]) != 24
        or {x["id"] for x in previous["selected"]} != CUT26_SOURCE_SONG_IDS
    ):
        raise ValueError("Cut26 previously scored source IDs failed authenticity checks")


def select_train_metadata(rows: list[dict]) -> list[dict]:
    """Stratified, order-independent TRAIN-only selection, no MIDI peeking."""
    by_group = {"beat": {}, "fill": {}}
    identity_splits = {}
    for x in rows:
        key = x["id"]
        if key in identity_splits and identity_splits[key] != x["split"]:
            raise ValueError("Official E-GMD source appears in multiple original splits")
        identity_splits[key] = x["split"]
        if (x["split"] != "train" or x["kit_name"] != "Acoustic Kit"
                or x["beat_type"] not in by_group):
            continue
        try:
            duration = float(x["duration"])
        except (TypeError, ValueError):
            continue
        if not 0 < duration <= 180:
            continue
        bucket = by_group[x["beat_type"]]
        if key in bucket and bucket[key]["audio_filename"] != x["audio_filename"]:
            raise ValueError("Conflicting Acoustic Kit renders for same TRAIN performance")
        bucket[key] = x

    chosen = []
    for kind, count in (("beat", 16), ("fill", 8)):
        pool = list(by_group[kind].values())
        if len(pool) < count:
            raise ValueError(f"Not enough official TRAIN Acoustic Kit {kind} recordings")
        style_used = Counter()
        drummer_used = Counter()
        for _ in range(count):
            best = min(pool, key=lambda x: (
                drummer_used[x["drummer"]]*25 + style_used[x["style"].split("/")[0]]*7,
                hashlib.sha256((SEED_TRAIN + "|" + x["id"]).encode()).hexdigest(),
                x["id"],
            ))
            chosen.append(best)
            drummer_used[best["drummer"]] += 1
            style_used[best["style"].split("/")[0]] += 1
            pool.remove(best)
    if len(chosen) != TRAIN_COUNT or len({x["id"] for x in chosen}) != TRAIN_COUNT:
        raise ValueError("TRAIN source song duplication")
    if len({x["drummer"] for x in chosen}) < 4:
        raise ValueError("Insufficient independent TRAIN drummers")
    return chosen


def select_validation_metadata(rows: list[dict]) -> list[dict]:
    selected = choose_validation_metadata(
        rows, count=VALIDATION_COUNT, short_fill_count=8,
        max_duration_s=180, kit_name="Acoustic Kit",
        exclude_source_song_ids=PREVIOUS_VAL_IDS,
        seed=SEED_VALIDATION,
    )
    if (len(selected) != VALIDATION_COUNT
            or len({x["id"] for x in selected}) != VALIDATION_COUNT
            or len({x["drummer"] for x in selected}) < 3
            or any(x["split"] != "validation" for x in selected)):
        raise ValueError("Unseen official Validation diversity/split requirement failed")
    return selected


def pair_manifest(folder: Path, pairs: list[dict], *, split: str) -> Path:
    """Record actual WAV/MIDI source hashes and explicit E-GMD research rights."""
    file = {
        "schema_version": "1", "dataset": "E-GMD v1.0.0",
        "split": split,
        "upstream_split": split,
        "original_csv_source": OFFICIAL_URL,
        "license": "Google LLC CC BY 4.0",
        "independent_human_legal_clearance": False,
        "commercial_distribution_approved": False,
        "samples": [],
    }
    for x in pairs:
        if x["source_split"] != split:
            raise ValueError("Downloaded source split differs from official metadata selection")
        wav = Path(x["wav"]).resolve()
        midi = Path(x["midi"]).resolve()
        file["samples"].append({
            "source_song_id": x["source_song_id"],
            "upstream_split": split,
            "audio_path": str(wav.relative_to(folder.resolve())),
            "reference_midi_path": str(midi.relative_to(folder.resolve())),
            "wav_sha256": x["wav_sha256"], "midi_sha256": x["midi_sha256"],
            "reference_midi_mapping": "roland_td11_to_gm",
            "audio_domain": "electronic_kit_recording",
            "rights": {
                "status": "approved",
                "research_evaluation_allowed": True,
                "commercial_benchmark_allowed": False,
                "audio_license": "Google LLC E-GMD v1.0.0 CC BY 4.0",
                "midi_license": "Google LLC E-GMD v1.0.0 CC BY 4.0",
                "evidence_url": OFFICIAL_URL,
                "reviewer": "automated publisher-source license verification; no legal sign-off",
            },
        })
    result = folder / f"private_{split}_manifest.json"
    result.write_text(json.dumps(file, indent=2, ensure_ascii=False)+"\n")
    return result


def official_rows(rows):
    return [{
        name: row[name] for name in (
            "id", "drummer", "session", "split", "style", "beat_type",
            "bpm", "duration", "kit_name", "audio_filename", "midi_filename",
        )
    } for row in rows]


def execute(folder: Path, original_cut26_plan: Path) -> dict:
    verify_cut26_old_plan(original_cut26_plan)
    if len(PREVIOUS_VAL_IDS) != 60:
        raise RuntimeError("Sixty previously-scored Validation IDs not frozen")
    root = Path(folder).resolve()
    root.mkdir(parents=True, exist_ok=True)
    csv, csv_hash = get_small_csv(root / "official_e_gmd.csv")
    source = read_metadata(csv)
    train_selection = select_train_metadata(source)
    val_selection = select_validation_metadata(source)

    # Both plans are selected BEFORE network audio requests and training.
    train_ids = [r["id"] for r in train_selection]
    val_ids = [r["id"] for r in val_selection]
    if (set(train_ids) & set(val_ids)
            or set(val_ids) & PREVIOUS_VAL_IDS):
        raise RuntimeError("TRAIN/Validation source identity leakage")
    raw_plan = {
        "revision": REVISION, "protocol_digest": protocol_digest(),
        "dataset": "E-GMD v1.0.0", "source_csv_sha256": csv_hash,
        "cut26_selection_sha256": CUT26_PLAN_SHA256,
        "excluded_previous_val_ids": sorted(PREVIOUS_VAL_IDS),
        "train_sample_seed": SEED_TRAIN, "validation_sample_seed": SEED_VALIDATION,
        "selection_before_audio_or_model": True,
        "train_selected": official_rows(train_selection),
        "validation_selected": official_rows(val_selection),
    }
    (root / "source_selection_plan.json").write_text(
        json.dumps(raw_plan, ensure_ascii=False, indent=2)+"\n",
    )
    preflight_ranges(ZIP_URL)
    train_files = acquire_selected(
        ZIP_URL, train_selection, root / "private_train", max_entry_mb=70,
    )
    train_manifest = pair_manifest(root, train_files, split="train")
    train_records, train_sha = read_train_manifest(train_manifest)
    if [r["source_song_id"] for r in train_records] != train_ids:
        raise RuntimeError("Actual TRAIN WAV IDs do not match the frozen source plan")

    examples = []
    training_stats = []
    for rec in train_records:
        truth = _normalize_reference(
            pretty_midi.PrettyMIDI(str(rec["midi"])), "roland_td11_to_gm",
        )
        rows = source_features(rec["wav"], truth, source_song_id=rec["source_song_id"])
        npos = sum(x["label"] for x in rows)
        training_stats.append({
            "source_song_id": rec["source_song_id"],
            "new_raw_candidates": len(rows), "true_new_hits": npos,
        })
        examples.extend(rows)
    # Strict TRAIN-only fit; fail closed if insufficient independent labels.
    model = fit_ranker(examples, manifest_sha256=train_sha)
    # Private weights are NEVER uploaded to Actions artifacts.
    private_model = root / "PRIVATE_DO_NOT_UPLOAD_train_only_model.json"
    private_model.write_text(json.dumps(model.to_dict(), indent=2)+"\n")
    model = HatRankerModel.from_dict(json.loads(private_model.read_text()))

    val_files = acquire_selected(
        ZIP_URL, val_selection, root / "private_validation", max_entry_mb=70,
    )
    val_manifest = pair_manifest(root, val_files, split="validation")
    val_records = validate_validation_manifest(val_manifest)
    if [r["song_id"] for r in val_records] != val_ids:
        raise RuntimeError("Actual unseen Validation pairs differ from frozen metadata")
    validation_plan = {
        "revision": REVISION, "dataset": "E-GMD v1.0.0",
        "upstream_split": "validation", "protocol_digest": protocol_digest(),
        "excluded_previous_val_ids": sorted(PREVIOUS_VAL_IDS),
        "selected": official_rows(val_selection),
        "train_source_song_ids": train_ids, "train_source_count": TRAIN_COUNT,
        "train_contributing_songs": model.source_songs,
        "train_manifest_sha256": train_sha,
    }
    validated = evaluate_unseen(val_records, validation_plan, model)
    validated["training_summary"] = {
        "source_songs": TRAIN_COUNT,
        "source_songs_with_candidates": model.source_songs,
        "candidate_examples": len(examples),
        "positive_new_hat_examples": model.positive_examples,
        "negative_new_hat_examples": model.negative_examples,
        "training_per_song_counts": training_stats,
        "training_manifest_sha256": train_sha,
        "trained_model_sha256": validated["train_model_sha256"],
        "independent_validation_selected_after_training": False,
        "model_not_redistributed": True,
    }
    validated["source_csv_sha256"] = csv_hash
    validated["selected_file_hashes"] = [
        {"id": p["source_song_id"], "split": p["source_split"],
         "wav_sha256": p["wav_sha256"], "midi_sha256": p["midi_sha256"]}
        for p in train_files + val_files
    ]
    validated["source_license"] = (
        "Google LLC, E-GMD v1.0.0 CC BY 4.0; "
        "Callender, Hawthorne and Engel (2020)."
    )
    output = root / "train_ranker_validation_results.json"
    output.write_text(json.dumps(validated, ensure_ascii=False, indent=2)+"\n")
    return {
        "output": str(output),
        "train_sources": len(train_ids), "validation_sources": len(val_ids),
        "training_new_hat_examples": len(examples),
        "positive_training_candidates": model.positive_examples,
        "validation_hat_reference": validated["cohort"]["reference_gm42"],
        "marginal_precision": validated["new_event_metrics"]["ranker_marginal_precision"],
        "decision": validated["decision"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cut26-plan", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        print(json.dumps(execute(args.output, args.cut26_plan), ensure_ascii=False, indent=2))
    except (RuntimeError, ValueError, PermissionError, OSError) as exc:
        ap.exit(1, f"TRAIN/VALIDATION RANKER BLOCKED: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
