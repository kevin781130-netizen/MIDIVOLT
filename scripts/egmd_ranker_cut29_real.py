"""One controlled E-GMD official TRAIN-only 24-vs-72 model scaling replay.

Select 72 Train fit sequences, nested 24-song small fit, and 24-song
drummer-disjoint Train-internal holdout from official public metadata
BEFORE opening any sound or reference MIDI. Nothing from Validation
or Test is downloaded. Model weights/media are private runner files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pretty_midi

from midivolt.egmd_import import read_metadata
from midivolt.drum_suite import _normalize_reference
from midivolt.hat_ranker_training import read_train_manifest, source_features
from midivolt.hat_candidate_ranker import fit_ranker, HatRankerModel
from midivolt.hat_ranker_cut29_group_holdout import (
    REVISION, choose_metadata_partition, compare_models, study_digest,
    FIT_SONGS, SMALL_SONGS, GROUP_HOLDOUT_SONGS,
)
from scripts.egmd_hat_ranker_real import pair_manifest
from scripts.egmd_mini_real import (
    ZIP_URL, acquire_selected, get_small_csv, preflight_ranges,
)


def _plan_rows(rows):
    names = ("id", "split", "drummer", "session", "style",
             "beat_type", "bpm", "duration", "kit_name",
             "audio_filename", "midi_filename")
    return [{k: row[k] for k in names} for row in rows]


def _fit(records: list[dict], *, name: str) -> tuple[HatRankerModel, list[dict]]:
    labels = []
    provenance = []
    for rec in records:
        reference = _normalize_reference(
            pretty_midi.PrettyMIDI(str(rec["midi"])), "roland_td11_to_gm",
        )
        examples = source_features(
            rec["wav"], reference, source_song_id=rec["source_song_id"],
        )
        positives = sum(x["label"] for x in examples)
        provenance.append({
            "source_song_id": rec["source_song_id"],
            "new_candidates": len(examples),
            "new_correct_hits": positives,
            "new_false_hits": len(examples)-positives,
        })
        labels.extend(examples)
    return labels, provenance


def run(output: Path) -> dict:
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    csv, csv_sha = get_small_csv(root / "official_e_gmd_metadata.csv")
    plan = choose_metadata_partition(read_metadata(csv))
    output_plan = {
        "dataset": plan["dataset"], "upstream_split": "train",
        "revision": REVISION, "protocol_digest": study_digest(),
        "csv_sha256": csv_sha,
        "metadata_selection_before_waveform_and_reference": True,
        "heldout_drummers": plan["heldout_drummers"],
        "fit": _plan_rows(plan["fit"]),
        "small": _plan_rows(plan["small"]),
        "holdout": _plan_rows(plan["holdout"]),
    }
    (root / "source_selection_plan.json").write_text(
        json.dumps(output_plan, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )
    # Private media access begins ONLY after immutable metadata selection.
    preflight_ranges(ZIP_URL)
    fit_files = acquire_selected(
        ZIP_URL, plan["fit"], root / "private_fit", max_entry_mb=75,
    )
    if len(fit_files) != FIT_SONGS:
        raise RuntimeError("Original TRAIN fitting assets missing")

    fit_manifest = pair_manifest(root, fit_files, split="train")
    fit_manifest = fit_manifest.rename(root / "private_fit72_manifest.json")
    fit_records, fit_sha = read_train_manifest(fit_manifest)
    if [x["source_song_id"] for x in fit_records] != [x["id"] for x in plan["fit"]]:
        raise RuntimeError("TRAIN source identities drifted before feature extraction")

    by_identity = {r["source_song_id"]: r for r in fit_records}
    small_ids = [x["id"] for x in plan["small"]]
    small_samples = [by_identity[x] for x in small_ids]
    # The explicit small manifest contains only its actual 24 TRAIN
    # recordings, not all 72 the expanded model will use.
    full_json = json.loads(fit_manifest.read_text(encoding="utf-8"))
    selected = {x["source_song_id"]: x for x in full_json["samples"]}
    small_manifest = root / "private_small24_train_manifest.json"
    small_json = {
        **full_json,
        "samples": [selected[x] for x in small_ids],
    }
    small_manifest.write_text(
        json.dumps(small_json, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )
    small_verified, small_sha = read_train_manifest(small_manifest)
    if [x["source_song_id"] for x in small_verified] != small_ids:
        raise RuntimeError("Small model source population drift")

    # Single extraction + single feature measurement per 72-song fit source.
    by_song_examples: dict[str, list[dict]] = {}
    per_song_training = []
    for rec in fit_records:
        truth = _normalize_reference(
            pretty_midi.PrettyMIDI(str(rec["midi"])), "roland_td11_to_gm"
        )
        new = source_features(
            rec["wav"], truth, source_song_id=rec["source_song_id"],
        )
        by_song_examples[rec["source_song_id"]] = new
        per_song_training.append({
            "source_song_id": rec["source_song_id"],
            "new_candidate_count": len(new),
            "positive_count": sum(x["label"] for x in new),
            "negative_count": len(new)-sum(x["label"] for x in new),
        })
    small_labels = [v for sid in small_ids for v in by_song_examples[sid]]
    full_labels = [v for r in fit_records
                   for v in by_song_examples[r["source_song_id"]]]
    model_small = fit_ranker(small_labels, manifest_sha256=small_sha)
    model_large = fit_ranker(full_labels, manifest_sha256=fit_sha)
    models = {"small_24_ranker": model_small, "expanded_72_ranker": model_large}
    # Keep model JSON only in private CI runner; no weight artifacts.
    model_sha = {}
    for key, model in models.items():
        file = root / f"PRIVATE_DO_NOT_UPLOAD_{key}.json"
        file.write_text(json.dumps(model.to_dict(), indent=2)+"\n", encoding="utf-8")
        model_sha[key] = hashlib.sha256(file.read_bytes()).hexdigest()
        models[key] = HatRankerModel.from_dict(json.loads(file.read_text()))

    test_files = acquire_selected(
        ZIP_URL, plan["holdout"], root / "private_holdout", max_entry_mb=75,
    )
    if len(test_files) != GROUP_HOLDOUT_SONGS:
        raise RuntimeError("Original TRAIN internal holdout assets missing")
    holdout_manifest = pair_manifest(root, test_files, split="train")
    holdout_manifest = holdout_manifest.rename(root / "private_holdout24_manifest.json")
    test_records, holdout_sha = read_train_manifest(holdout_manifest)
    if [x["source_song_id"] for x in test_records] != [x["id"] for x in plan["holdout"]]:
        raise RuntimeError("TRAIN holdout source identities changed")
    holdout_evaluation = []
    for r in test_records:
        truth = _normalize_reference(
            pretty_midi.PrettyMIDI(str(r["midi"])), "roland_td11_to_gm"
        )
        holdout_evaluation.append({
            "song_id": r["source_song_id"],
            "wav": r["wav"], "truth": truth,
        })
    result = compare_models(
        holdout_evaluation, plan,
        models["small_24_ranker"], models["expanded_72_ranker"],
    )
    result.update({
        "train_data": {
            "train72_manifest_sha256": fit_sha,
            "train24_manifest_sha256": small_sha,
            "holdout24_manifest_sha256": holdout_sha,
            "all_features_from_train_only": True,
            "train_song_candidate_counts": per_song_training,
            "train24_candidate_count": len(small_labels),
            "train72_candidate_count": len(full_labels),
        },
        "private_model_file_sha256": model_sha,
        "source_csv_sha256": csv_sha,
        "source_pair_hashes": [
            {"song_id": s["source_song_id"], "wav_sha256": s["wav_sha256"],
             "midi_sha256": s["midi_sha256"], "split": s["source_split"]}
            for s in fit_files + test_files
        ],
        "source_attribution": (
            "Google LLC, E-GMD v1.0.0, CC BY 4.0; "
            "Callender, Hawthorne and Engel (2020)."
        ),
    })
    p = root / "train_group_holdout_results.json"
    p.write_text(
        json.dumps(result, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )
    return {
        "result_path": str(p),
        "train24_candidates": len(small_labels),
        "train72_candidates": len(full_labels),
        "train24_contributing": models["small_24_ranker"].source_songs,
        "train72_contributing": models["expanded_72_ranker"].source_songs,
        "holdout_drummer_count": len(plan["heldout_drummers"]),
        "holdout_reference_gm42": result["holdout"]["reference_gm42"],
        "group_holdout_only": True,
        "research_decision": result["decision"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        response = run(args.output)
    except (OSError, RuntimeError, ValueError, PermissionError) as err:
        parser.exit(1, f"CUT29 TRAIN GROUP-HOLDOUT BLOCKED: {err}\n")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
