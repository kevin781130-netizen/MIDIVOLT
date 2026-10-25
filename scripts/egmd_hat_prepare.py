"""Prepare independent E-GMD VALIDATION test pairs for DSP hat tuning.

Default: metadata-only selection, no model/large ZIP download.
Optional --extract-range downloads ONLY selected WAV/MIDI ZIP members after
an HTTP-206 Range preflight. It creates a *blocked* manifest: no inference
until a human reviews asset rights and authorizes research evaluation.

This NEVER chooses official TEST or TRAIN performances, and never enables
a changed DSP preset in production.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from midivolt.egmd_import import read_metadata
from midivolt.hat_validation import (
    VALIDATION_DATASET, PRESET_REVISION, choose_validation_metadata, preset_sha256,
    CUT21_VALIDATION_SONG_IDS,
)

SOURCE = "https://magenta.tensorflow.org/datasets/e-gmd"


def prepare(
    csv_path: Path, output: Path, *,
    count: int = 6, fills: int = 2, extract_range: bool = False,
    official_cc_by_research_review: bool = False,
    exclude_plan_path: Path | None = None,
) -> dict:
    exclude_ids: frozenset[str] = frozenset()
    if exclude_plan_path is not None:
        prior = json.loads(Path(exclude_plan_path).read_text(encoding="utf-8"))
        if (
            not isinstance(prior, dict)
            or prior.get("dataset") != VALIDATION_DATASET
            or prior.get("upstream_split") != "validation"
            or not isinstance(prior.get("samples"), list)
            or not prior["samples"]
        ):
            raise ValueError("Excluded selection plan must be the previous E-GMD Validation plan")
        ids = [row.get("id") for row in prior["samples"] if isinstance(row, dict)]
        if (
            len(ids) != len(prior["samples"])
            or any(not isinstance(i, str) or not i for i in ids)
            or len(ids) != len(set(ids))
        ):
            raise ValueError("Prior Validation plan contains duplicate/invalid song identities")
        exclude_ids = frozenset(ids)
        if exclude_ids != CUT21_VALIDATION_SONG_IDS:
            raise ValueError(
                "Previous Validation plan must contain exactly the six "
                "frozen Cut-21 song IDs, not an arbitrary replacement set"
            )
    rows = choose_validation_metadata(
        read_metadata(csv_path),
        count=count, short_fill_count=fills,
        exclude_source_song_ids=exclude_ids,
        seed=(
            "midivolt-hat-shape-independent-v1"
            if exclude_plan_path else "midivolt-hat-validation-selection-v1"
        ),
    )
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema_version": "1",
        "dataset": VALIDATION_DATASET,
        "source": SOURCE,
        "upstream_split": "validation",
        "sampling_method": "metadata_only_deterministic_stratified_before_model_scoring",
        "song_count": len(rows),
        "excluded_previous_validation_source_song_ids": sorted(exclude_ids),
        "excludes_previous_validation_experiments": exclude_plan_path is not None,
        "beats": count - fills,
        "fills": fills,
        "drummer_count": len({row["drummer"] for row in rows}),
        "preset_revision": PRESET_REVISION,
        "preset_sha256": preset_sha256(),
        "samples": [{
            field: row[field] for field in (
                "id", "drummer", "split", "kit_name", "beat_type",
                "style", "bpm", "duration", "audio_filename", "midi_filename"
            )
        } for row in rows],
        "research_rights_status": "pending_review",
        "contains_model_predictions": False,
    }
    (output / "validation_selection_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    if not extract_range:
        return {
            "status": "validation_metadata_plan_created",
            "selection_plan": str(output / "validation_selection_plan.json"),
            "song_count": len(rows),
            "wav_downloaded": False,
        }

    # Extra imports only when explicitly asked to extract selected samples.
    from scripts.egmd_mini_real import ZIP_URL, acquire_selected, preflight_ranges
    zip_bytes = preflight_ranges(ZIP_URL)
    files = acquire_selected(
        ZIP_URL, rows, output / "private_pairs", max_entry_mb=48,
    )
    if len(files) != len(rows):
        raise RuntimeError("E-GMD official validation extraction missing sample pairs")
    research_license_note = (
        "Verified official E-GMD v1.0.0 dataset page states CC BY 4.0 by "
        "Google LLC. Internal validation benchmarking only. Review is "
        "automated source-license verification, NOT independent legal advice "
        "or permission to redistribute model weights or third-party media."
    )
    manifest = {
        "schema_version": "1",
        "dataset": VALIDATION_DATASET,
        "license_verification": {
            "source_url": SOURCE,
            "source_declared_license": "CC BY 4.0",
            "verification_method": (
                "explicit automated source-license verification (not a human legal review)"
                if official_cc_by_research_review else "pending human verification"
            ),
            "research_only": True,
            "prohibited_artifacts": ["wav", "midi", "model_weights"],
            "legal_clearance_for_product_distribution": False,
        },
        "purpose": "Validation-only hi-hat DSP tuning; NOT final Test benchmark",
        "remote_zip_content_length": zip_bytes,
        "samples": [],
    }
    for record in files:
        wav = Path(record["wav"]).resolve()
        mid = Path(record["midi"]).resolve()
        manifest["samples"].append({
            "source_song_id": record["source_song_id"],
            "upstream_split": record["source_split"],
            "audio_domain": "electronic_kit_recording",
            "source_dataset": VALIDATION_DATASET,
            "source_url": SOURCE,
            "audio_path": str(wav.relative_to(output)),
            "reference_midi_path": str(mid.relative_to(output)),
            "wav_sha256": record["wav_sha256"],
            "midi_sha256": record["midi_sha256"],
            "reference_midi_mapping": "roland_td11_to_gm",
            "style": record["style"],
            "kit_name": record["kit_name"],
            "bpm": record["bpm"],
            "rights": {
                "status": "approved" if official_cc_by_research_review else "pending",
                "research_evaluation_allowed": bool(official_cc_by_research_review),
                "commercial_benchmark_allowed": False,
                "audio_license": "CC BY 4.0 (Google Magenta declaration; individual rights review pending)",
                "midi_license": "CC BY 4.0 (Google Magenta declaration; individual rights review pending)",
                "evidence_url": SOURCE,
                "reviewer": (
                    "automated official dataset license/source verification"
                    if official_cc_by_research_review else "unassigned"
                ),
                "review_method": (
                    "CC BY 4.0 internal evaluation grant; automated verification, not legal review"
                    if official_cc_by_research_review else "pending independent review"
                ),
                "attribution": (
                    "Google LLC, Expanded Groove MIDI Dataset v1.0.0, CC BY 4.0; "
                    "Callender, Hawthorne and Engel (2020)"
                ),
            },
        })
    path = output / (
        "validation_manifest_SOURCE_LICENSE_REVIEWED.json"
        if official_cc_by_research_review
        else "validation_manifest_PENDING_REVIEW.json"
    )
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return {
        "status": "validation_wav_midi_extracted_pending_rights_approval",
        "manifest": str(path),
        "song_count": len(files),
        "wav_midi_pairs_extracted": len(files),
        "benchmark_execution_allowed": bool(official_cc_by_research_review),
        "independent_legal_clearance": False,
        "license_source": SOURCE,
        "rights_review_mode": (
            "automated_official_source_license_verification"
            if official_cc_by_research_review else "human_review_pending"
        ),
        "large_zip_full_downloaded": False,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True, help="official E-GMD metadata CSV")
    ap.add_argument("--output", type=Path, required=True, help="private workspace folder")
    ap.add_argument("--count", type=int, default=6)
    ap.add_argument("--fills", type=int, default=2)
    ap.add_argument(
        "--exclude-plan", type=Path,
        help="required to select a NEW cohort for shape experiments: previous Validation selection_plan.json"
    )
    ap.add_argument("--extract-range", action="store_true")
    ap.add_argument(
        "--official-cc-by-research-review", action="store_true",
        help="Record an explicit automated CC BY 4.0 source verification for internal "
             "research only. Never authorizes release/redistribution; no human legal review."
    )
    args = ap.parse_args(argv)
    try:
        result = prepare(
            args.csv, args.output, count=args.count, fills=args.fills,
            extract_range=args.extract_range,
            official_cc_by_research_review=args.official_cc_by_research_review,
            exclude_plan_path=args.exclude_plan,
        )
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        ap.exit(1, f"E-GMD validation preparation blocked: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
