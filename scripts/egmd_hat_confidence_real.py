"""One-off weight-free CPU-only NEW validation of candidate confidence.

24 fresh official E-GMD Validation performances, metadata selected before
reading any waveform/annotations. Excludes the 36 source IDs already
studied in Cuts 21/23/25. Fails closed if original Cut-25 plan hash changes.
Never shares audio, original MIDI, prediction MIDI or model weights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from midivolt.egmd_import import read_metadata
from midivolt.hat_validation import choose_validation_metadata, validate_validation_manifest
from midivolt.hat_candidate_confidence_validation import (
    REVISION, OLD_CUT25_PLAN_SHA256, CUT25_SONG_IDS, EXCLUSIONS,
    TOTAL_SONGS, settings_digest, evaluate_confidence_study,
)
from scripts.egmd_mini_real import (
    ZIP_URL, acquire_selected, get_small_csv, preflight_ranges,
)

SOURCE = "https://magenta.withgoogle.com/datasets/e-gmd"


def _original_plan_ok(path: Path) -> None:
    binary = Path(path).read_bytes()
    if hashlib.sha256(binary).hexdigest() != OLD_CUT25_PLAN_SHA256:
        raise ValueError("Original Cut-25 selection plan SHA-256 changed")
    old = json.loads(binary)
    if (old.get("dataset") != "E-GMD v1.0.0"
            or old.get("upstream_split") != "validation"
            or {x["id"] for x in old.get("selected", [])} != CUT25_SONG_IDS
            or len(old["selected"]) != 24):
        raise ValueError("Original Cut-25 song list invalid")


def execute(output: Path, cut25_plan: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    _original_plan_ok(cut25_plan)

    csv_path, csv_sha = get_small_csv(output / "official_e_gmd_metadata.csv")
    rows = choose_validation_metadata(
        read_metadata(csv_path),
        count=TOTAL_SONGS,
        short_fill_count=12,
        max_duration_s=180,
        kit_name="Acoustic Kit",
        seed="midivolt-confidence-24-split-independent-r1",
        exclude_source_song_ids=EXCLUSIONS,
    )
    if len(rows) != 24 or any(row["split"] != "validation" for row in rows):
        raise RuntimeError("Wrong official Validation source selection")
    plan = {
        "dataset": "E-GMD v1.0.0",
        "upstream_split": "validation",
        "study_revision": REVISION,
        "settings_digest": settings_digest(),
        "original_cut25_selection_sha256": OLD_CUT25_PLAN_SHA256,
        "metadata_sha256": csv_sha,
        "excluded_previous_song_ids": sorted(EXCLUSIONS),
        "sampling_seed": "midivolt-confidence-24-split-independent-r1",
        "sampling_method": "metadata_only_pre_inference",
        "beats": 12, "fills": 12, "max_seconds_per_song": 180,
        "selected": [{
            k: row[k] for k in (
                "id", "drummer", "session", "split",
                "style", "beat_type", "bpm", "duration",
                "kit_name", "audio_filename", "midi_filename",
            )
        } for row in rows],
    }
    (output / "selection_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    # SOURCE metadata and prior frozen plan are verified before WAV access.
    remote_total = preflight_ranges(ZIP_URL)
    recordings = acquire_selected(
        ZIP_URL, rows, output / "private_audio_midi", max_entry_mb=60
    )
    if len(recordings) != TOTAL_SONGS:
        raise RuntimeError("Incomplete 24-song WAV/MIDI extraction")
    metadata = {
        "schema_version": "1", "dataset": "E-GMD v1.0.0",
        "license_provenance": {
            "official_release": "CC BY 4.0 (Google LLC, E-GMD v1.0.0)",
            "research_only": True,
            "independent_legal_clearance": False,
            "product_bundling_rights": False,
        },
        "official_archive_total_bytes": remote_total,
        "samples": [],
    }
    for sample in recordings:
        if sample["source_split"] != "validation":
            raise RuntimeError("Source leakage, only Validation is allowed")
        wav = Path(sample["wav"])
        mid = Path(sample["midi"])
        metadata["samples"].append({
            "source_song_id": sample["source_song_id"],
            "upstream_split": "validation",
            "audio_domain": "electronic_kit_recording",
            "reference_midi_mapping": "roland_td11_to_gm",
            "audio_path": str(wav.relative_to(output)),
            "reference_midi_path": str(mid.relative_to(output)),
            "wav_sha256": sample["wav_sha256"],
            "midi_sha256": sample["midi_sha256"],
            "rights": {
                "status": "approved",
                "research_evaluation_allowed": True,
                "commercial_benchmark_allowed": False,
                "audio_license": "CC BY 4.0 - official Google E-GMD v1.0.0",
                "midi_license": "CC BY 4.0 - official Google E-GMD v1.0.0",
                "evidence_url": SOURCE,
                "reviewer": "automated official source license review; not independent legal counsel",
            },
        })
    local_manifest = output / "private_validation_manifest.json"
    local_manifest.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    verified = validate_validation_manifest(local_manifest)
    if [r["song_id"] for r in verified] != [r["id"] for r in rows]:
        raise RuntimeError("Extracted source identities differ from locked metadata plan")

    result = evaluate_confidence_study(verified, plan)
    result["source_csv_sha256"] = csv_sha
    result["source_file_checksums"] = [
        {
            "source_song_id": x["source_song_id"],
            "wav_sha256": x["wav_sha256"],
            "reference_midi_sha256": x["midi_sha256"],
        }
        for x in recordings
    ]
    result["attribution"] = (
        "Google LLC, E-GMD v1.0.0, CC BY 4.0; Callender, Hawthorne and Engel (2020)."
    )
    dest = output / "candidate_confidence_results.json"
    dest.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return {
        "report": str(dest),
        "independent_song_count": len(rows),
        "hat_truth_events": result["reference_closed_hat_count"],
        "marginal_precision": result["raw_vs_filtered_hat"]["confident_new_note_precision"],
        "decision": result["decision"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cut25-plan", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = execute(args.output, args.cut25_plan)
    except (OSError, ValueError, RuntimeError, PermissionError) as exc:
        parser.exit(1, f"INDEPENDENT HI-HAT CONFIDENCE VALIDATION BLOCKED: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
