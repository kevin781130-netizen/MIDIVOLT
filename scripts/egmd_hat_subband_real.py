"""One opt-in, CPU-only E-GMD v1.0.0 VALIDATION subband-candidate study.

Selects 24 source-song IDs by public metadata BEFORE downloading any sound
or looking at annotation events. Excludes ALL twelve previous Validation
performances. Runs only baseline DSP and opt-in candidate generator.

Research source is official Google E-GMD CC BY 4.0; no model weights, samples,
annotation MIDI or raw predictions are uploaded by the CI workflow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from midivolt.egmd_import import read_metadata
from midivolt.hat_validation import (
    CUT21_VALIDATION_SONG_IDS, choose_validation_metadata,
    validate_validation_manifest,
)
from midivolt.hat_shape_ablation import CUT23_SONG_IDS
from midivolt.hat_subband_validation import (
    STUDY_REVISION, PRE_REGISTERED_SAMPLE_COUNT,
    EXCLUDED_PREVIOUS_SONG_IDS,
    settings_digest, evaluate_candidate_generator,
)
from scripts.egmd_mini_real import (
    ZIP_URL, acquire_selected, get_small_csv, preflight_ranges,
)


def execute(output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if EXCLUDED_PREVIOUS_SONG_IDS != (
        CUT21_VALIDATION_SONG_IDS | CUT23_SONG_IDS
    ) or len(EXCLUDED_PREVIOUS_SONG_IDS) != 12:
        raise RuntimeError("Historical Validation exclusion set changed")

    metadata_path, metadata_sha = get_small_csv(output / "official_metadata.csv")
    rows = choose_validation_metadata(
        read_metadata(metadata_path),
        count=PRE_REGISTERED_SAMPLE_COUNT,
        short_fill_count=8,
        max_duration_s=35,
        kit_name="Acoustic Kit",
        seed="midivolt-dual-subband-fresh24-fixed-selection-v1",
        exclude_source_song_ids=EXCLUDED_PREVIOUS_SONG_IDS,
    )
    plan = {
        "dataset": "E-GMD v1.0.0",
        "upstream_split": "validation",
        "study_revision": STUDY_REVISION,
        "settings_digest": settings_digest(),
        "metadata_sha256": metadata_sha,
        "excluded_previous_song_ids": sorted(EXCLUDED_PREVIOUS_SONG_IDS),
        "selection_method": "metadata_only_before_loading_audio_or_MIDI",
        "selection_seed": "midivolt-dual-subband-fresh24-fixed-selection-v1",
        "selected": [
            {key: row[key] for key in (
                "id", "drummer", "session", "split", "style", "bpm",
                "beat_type", "duration", "kit_name", "audio_filename",
                "midi_filename",
            )} for row in rows
        ],
        "beat_count": 16,
        "fill_count": 8,
        "contains_model_outputs": False,
    }
    plan_file = output / "validation_selection_plan.json"
    plan_file.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if (len(rows) != 24 or len({x["id"] for x in rows}) != 24
            or any(x["split"] != "validation" for x in rows)):
        raise RuntimeError("Selected nonunique/non-Validation source performances")

    # Crucial order: source ID selection and frozen plan precede ZIP access.
    length = preflight_ranges(ZIP_URL)
    files = acquire_selected(
        ZIP_URL, rows, output / "private_pairs", max_entry_mb=48
    )
    if len(files) != len(rows):
        raise RuntimeError("Incomplete Validation extraction")
    manifest = {
        "schema_version": "1",
        "dataset": "E-GMD v1.0.0",
        "source": "https://magenta.withgoogle.com/datasets/e-gmd",
        "license_verification": {
            "official_source_license": "CC BY 4.0",
            "research_use_only": True,
            "human_legal_review": False,
            "model_or_media_redistribution_approved": False,
        },
        "official_remote_zip_bytes": length,
        "samples": [],
    }
    for rec in files:
        if rec["source_split"] != "validation":
            raise RuntimeError("Train/Test sample detected after extraction")
        wav = Path(rec["wav"])
        midi = Path(rec["midi"])
        manifest["samples"].append({
            "source_song_id": rec["source_song_id"],
            "upstream_split": "validation",
            "audio_domain": "electronic_kit_recording",
            "source_dataset": "E-GMD v1.0.0",
            "audio_path": str(wav.relative_to(output)),
            "reference_midi_path": str(midi.relative_to(output)),
            "wav_sha256": rec["wav_sha256"],
            "midi_sha256": rec["midi_sha256"],
            "reference_midi_mapping": "roland_td11_to_gm",
            "rights": {
                "status": "approved",
                "research_evaluation_allowed": True,
                "commercial_benchmark_allowed": False,
                "audio_license": "CC BY 4.0 (official Google E-GMD)",
                "midi_license": "CC BY 4.0 (official Google E-GMD)",
                "evidence_url": "https://magenta.withgoogle.com/datasets/e-gmd",
                "reviewer": "automated official source-license verification, not legal counsel",
            },
        })
    # Private, not part of the GitHub artifact.
    manifest_file = output / "private_validation_manifest.json"
    manifest_file.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    verified = validate_validation_manifest(manifest_file)
    if [x["song_id"] for x in verified] != [x["id"] for x in rows]:
        raise RuntimeError("Downloaded/verified files differ from metadata plan")

    result = evaluate_candidate_generator(verified, plan)
    result["metadata_sha256"] = metadata_sha
    result["selected_pair_provenance"] = [
        {
            "source_song_id": x["source_song_id"],
            "drummer": x["drummer"],
            "style": x["style"],
            "bpm": x["bpm"],
            "wav_sha256": x["wav_sha256"],
            "reference_midi_sha256": x["midi_sha256"],
        } for x in files
    ]
    result["official_dataset_attribution"] = (
        "Google LLC, E-GMD v1.0.0, CC BY 4.0; "
        "Callender, Hawthorne and Engel (2020)."
    )
    report = output / "subband_validation_results.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "results_file": str(report),
        "sample_count": len(verified),
        "reference_gm42": result["reference_gm42_count"],
        "decision": result["decision"],
        "summary_by_arm": result["summary_by_arm"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = execute(args.output)
    except (OSError, ValueError, RuntimeError, PermissionError) as exc:
        parser.exit(1, f"NEW HI-HAT SUBBAND VALIDATION BLOCKED: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
