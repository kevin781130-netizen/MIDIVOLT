"""Fit a local research-only Hi-hat candidate ranker on TRAIN recordings.

Usage:
  python -m scripts.train_hat_ranker --manifest /private/train_manifest.json \
      --output /private/hat_ranker_train_only.json

The manifest must contain user-authorized and individually SHA-verified
official TRAIN WAV/MIDI pairs. Validation/Test are REJECTED. The trained
weights are written ONLY to the requested private path, never to GitHub
or automatically into MIDIVOLT defaults.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pretty_midi

from midivolt.drum_suite import _normalize_reference
from midivolt.hat_ranker_training import read_train_manifest, source_features
from midivolt.hat_candidate_ranker import fit_ranker, json_sha256


def train(manifest: Path, output: Path) -> dict:
    source, manifest_digest = read_train_manifest(manifest)
    candidates = []
    per_song = []
    for rec in source:
        truth = _normalize_reference(
            pretty_midi.PrettyMIDI(str(rec["midi"])), "roland_td11_to_gm"
        )
        examples = source_features(
            rec["wav"], truth, source_song_id=rec["source_song_id"],
        )
        per_song.append({
            "source_song_id": rec["source_song_id"],
            "examples": len(examples),
            "positive": sum(x["label"] for x in examples),
            "negative": len(examples)-sum(x["label"] for x in examples),
        })
        candidates.extend(examples)
    model = fit_ranker(candidates, manifest_sha256=manifest_digest)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = model.to_dict()
    payload["training_source"] = {
        "dataset": "E-GMD v1.0.0", "split": "train",
        "manifest_sha256": manifest_digest,
        "performance_count": len(source),
        "candidate_count": len(candidates),
        "per_song_counts_sha256": json_sha256({"counts": per_song}),
        "reference_annotation_mapping": "roland_td11_to_gm",
        "training_only": True,
        "independent_validation_completed": False,
    }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return {
        "model_path": str(output),
        "train_songs": len(source), "train_candidates": len(candidates),
        "positives": model.positive_examples,
        "negatives": model.negative_examples,
        "manifest_sha256": manifest_digest,
        "independent_validation_completed": False,
        "product_or_beta_approved": False,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        summary = train(args.manifest, args.output)
    except (OSError, RuntimeError, ValueError, PermissionError) as exc:
        ap.exit(1, f"TRAIN-only ranker blocked: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
