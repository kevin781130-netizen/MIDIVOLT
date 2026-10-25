"""Validation-only DSP Closed Hi-hat recall study; no Test-set tuning.

Official TEST data must NEVER be supplied here. All sensitivity candidates
are predefined below and frozen before reviewing real Validation metrics.
The baseline production DSP parameters are untouched until an independent
decision is made after this experiment.

Use aligned, local E-GMD WAV + GM/Roland MIDI pairs from the official
VALIDATION split, pinned by separate SHA-256 hashes. No model weights,
dataset downloads, or GitHub Actions are needed.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pretty_midi

from midivolt.drums import HatDetectionConfig, transcribe_drum_wav
from midivolt.drum_ontology import evaluate_common_ontology
from midivolt.drum_suite import _normalize_reference

PRESET_REVISION = "hat-validation-presets-v1-locked"
VALIDATION_DATASET = "E-GMD v1.0.0"
# All candidate definitions are set in source. NO optimization against TEST data.
PRESETS = {
    "baseline": HatDetectionConfig(),
    "conservative": HatDetectionConfig(
        peak_fraction_scale=0.85, flux_noise_multiplier=2.65,
        min_high_power_share=0.11, min_high_to_mid_ratio=2.2,
    ),
    "moderate": HatDetectionConfig(
        peak_fraction_scale=0.70, flux_noise_multiplier=2.25,
        min_high_power_share=0.09, min_high_to_mid_ratio=1.9,
    ),
    "aggressive": HatDetectionConfig(
        peak_fraction_scale=0.55, flux_noise_multiplier=1.75,
        min_high_power_share=0.07, min_high_to_mid_ratio=1.5,
    ),
}
HAT_CLASS = "42"
# Predeclare precision guardrails before looking at validation scores.
MAX_HAT_PRECISION_DROP = 0.12
MAX_ALL_PRECISION_DROP = 0.05
MIN_HAT_RECALL_GAIN = 0.02
MIN_HAT_PRECISION_ABSOLUTE = 0.60



def choose_validation_metadata(
    rows: list[dict],
    *,
    count: int = 6,
    short_fill_count: int = 2,
    max_duration_s: float = 35.0,
    kit_name: str = "Acoustic Kit",
    seed: str = "midivolt-hat-validation-selection-v1",
) -> list[dict]:
    """Choose independent official VALIDATION performances, before WAV reading.

    Do not apply test-set selection logic or use any inferred drum events.
    Requesting unavailable beat/fill strata fails rather than borrowing
    official TEST or TRAIN examples.
    """
    if not 2 <= count <= 24 or not 0 <= short_fill_count < count:
        raise ValueError("Invalid requested Validation beat/fill selection sizes")
    if not math.isfinite(max_duration_s) or not 1 <= max_duration_s <= 180:
        raise ValueError("Invalid maximum Validation excerpt duration")
    previous = {}
    selected = {"beat": [], "fill": []}
    for row in rows:
        identity = row.get("id")
        split = row.get("split")
        if not isinstance(identity, str) or not identity:
            continue
        if identity in previous and previous[identity] != split:
            raise ValueError("Original E-GMD song ID spans train/test/validation")
        previous[identity] = split
        if split != "validation" or row.get("kit_name") != kit_name:
            continue
        typ = row.get("beat_type")
        if typ not in selected:
            continue
        try:
            duration = float(row.get("duration", ""))
            bpm = float(row.get("bpm", ""))
        except (ValueError, TypeError):
            continue
        if not (math.isfinite(duration) and 1 <= duration <= max_duration_s):
            continue
        if not (math.isfinite(bpm) and 30 <= bpm <= 400):
            continue
        if not row.get("style") or not row.get("drummer"):
            continue
        selected[typ].append(row)

    take = {"beat": count - short_fill_count, "fill": short_fill_count}
    result = []
    for typ in ("beat", "fill"):
        unique = {}
        for row in selected[typ]:
            key = row["id"]
            if key in unique and unique[key]["audio_filename"] != row["audio_filename"]:
                raise ValueError("Duplicate validation performance with conflicting WAV")
            unique[key] = row
        if len(unique) < take[typ]:
            raise ValueError(f"Only {len(unique)} official Validation {typ} performances; "
                             f"requested {take[typ]}")
        pool = list(unique.values())
        genres = Counter()
        drummers = Counter()
        for _ in range(take[typ]):
            def priority(r):
                genre = r["style"].split("/")[0]
                random_hash = hashlib.sha256((seed + "|" + r["id"]).encode()).hexdigest()
                return (drummers[r["drummer"]] * 20 + genres[genre] * 8,
                        random_hash, r["id"])
            pick = min(pool, key=priority)
            result.append(pick)
            drummers[pick["drummer"]] += 1
            genres[pick["style"].split("/")[0]] += 1
            pool.remove(pick)
    if len({x["id"] for x in result}) != len(result):
        raise RuntimeError("Cross-stratum validation song duplication")
    return result

def preset_sha256() -> str:
    from dataclasses import asdict
    payload = [[name, asdict(settings)] for name, settings in PRESETS.items()]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    from midivolt.drum_suite import _within_folder
    return _within_folder(root, relative)


def validate_validation_manifest(path: Path) -> list[dict]:
    """Enforce source Test isolation, pair identity, bytes and rights declaration."""
    manifest = Path(path).resolve()
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "1" or raw.get("dataset") != VALIDATION_DATASET:
        raise ValueError("Require E-GMD v1.0.0 validation manifest schema v1")
    entries = raw.get("samples")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Validation set must include at least one WAV/MIDI pair")
    records = []
    identities = set()
    song_splits = set()
    for i, rec in enumerate(entries):
        if not isinstance(rec, dict):
            raise ValueError("Every sample must be an object")
        if rec.get("upstream_split") != "validation":
            raise ValueError("Held-out TEST/train data forbidden in hat parameter experiments")
        if rec.get("audio_domain") != "electronic_kit_recording":
            raise ValueError("Only E-GMD electronic-kit audio allowed in this experiment")
        if rec.get("reference_midi_mapping") != "roland_td11_to_gm":
            raise ValueError("Must explicitly declare Roland reference mapping")
        rights = rec.get("rights")
        if (not isinstance(rights, dict)
                or rights.get("status") != "approved"
                or rights.get("research_evaluation_allowed") is not True):
            raise PermissionError("E-GMD audio/MIDI rights approval required per pair")
        for field in ("audio_license", "midi_license", "evidence_url", "reviewer"):
            if not isinstance(rights.get(field), str) or not rights[field].strip():
                raise PermissionError("Missing separate audio/MIDI permissions: " + field)
        song = rec.get("source_song_id")
        if not isinstance(song, str) or not song or song in identities:
            raise ValueError("Duplicate/missing source song ID; use one kit per performance")
        identities.add(song)
        song_splits.add(rec.get("upstream_split"))
        for key in ("audio_path", "reference_midi_path", "wav_sha256", "midi_sha256"):
            if not isinstance(rec.get(key), str) or not rec[key]:
                raise ValueError(f"Missing {key} in sample {i}")
        wav = _safe_path(manifest.parent, rec["audio_path"])
        midi = _safe_path(manifest.parent, rec["reference_midi_path"])
        if wav.suffix.lower() != ".wav" or midi.suffix.lower() not in (".mid", ".midi"):
            raise ValueError("Expected WAV and MIDI pair")
        for file_path, field in ((wav, "wav_sha256"), (midi, "midi_sha256")):
            expected = rec[field]
            if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
                raise ValueError("Invalid file checksum: " + field)
            if _digest(file_path) != expected:
                raise ValueError("WAV/MIDI SHA-256 mismatch: " + field)
        truth = _normalize_reference(
            pretty_midi.PrettyMIDI(str(midi)), "roland_td11_to_gm"
        )
        if not any(ins.notes for ins in truth.instruments):
            raise ValueError("Empty drum reference sample")
        records.append({"song_id": song, "wav": wav, "midi": midi, "truth": truth})
    return records


def _aggregate(scores: list[dict]) -> dict:
    """Micro-score derived from summed note counts, not mean F1 values."""
    if not scores:
        raise ValueError("No Validation results")
    totals = Counter()
    hat_totals = Counter()
    per_song = {}
    for item in scores:
        micro = item["result"]["micro"]
        hat = item["result"]["per_class"].get(HAT_CLASS, {})
        for key in ("tp", "fp", "fn"):
            totals[key] += micro[key]
            hat_totals[key] += hat.get(key, 0)
        per_song[item["song_id"]] = micro
    def metric(c: Counter) -> dict:
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        p = tp / (tp + fp) if tp + fp else (1.0 if fn == 0 else 0.0)
        r = tp / (tp + fn) if tp + fn else (1.0 if fp == 0 else 0.0)
        f = 2 * p * r / (p + r) if p + r else 0.0
        return {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 6), "recall": round(r, 6), "f1": round(f, 6),
        }
    return {
        "song_count": len(per_song),
        "total": metric(totals),
        "closed_hi_hat": metric(hat_totals),
        "song_macro_f1": round(statistics.mean(float(x["f1"]) for x in per_song.values()), 6),
        "median_dsp_runtime_seconds": round(statistics.median(item["seconds"] for item in scores), 5),
    }


def _recommend(summaries: dict) -> dict:
    """Recommend only if pre-registered recall gain AND precision gates pass."""
    baseline = summaries["baseline"]
    if baseline["closed_hi_hat"]["tp"] + baseline["closed_hi_hat"]["fn"] < 1:
        return {"status": "no_eligible_preset", "reason": "No annotated Closed Hi-hat hits"}
    candidates = []
    for name in PRESETS:
        if name == "baseline":
            continue
        value = summaries[name]
        gain = value["closed_hi_hat"]["recall"] - baseline["closed_hi_hat"]["recall"]
        hat_precision = value["closed_hi_hat"]["precision"]
        all_precision = value["total"]["precision"]
        eligible = (
            gain >= MIN_HAT_RECALL_GAIN
            and hat_precision >= max(MIN_HAT_PRECISION_ABSOLUTE,
                                    baseline["closed_hi_hat"]["precision"] - MAX_HAT_PRECISION_DROP)
            and all_precision >= baseline["total"]["precision"] - MAX_ALL_PRECISION_DROP
        )
        candidates.append({
            "preset": name, "hat_recall_delta": round(gain, 6),
            "hat_precision": hat_precision,
            "overall_precision": all_precision,
            "eligible": eligible,
            "blocked_by": [] if eligible else [
                reason for test, reason in (
                    (gain >= MIN_HAT_RECALL_GAIN, "insufficient_hat_recall_gain"),
                    (hat_precision >= max(MIN_HAT_PRECISION_ABSOLUTE,
                        baseline["closed_hi_hat"]["precision"] - MAX_HAT_PRECISION_DROP),
                     "hat_precision_guard"),
                    (all_precision >= baseline["total"]["precision"] - MAX_ALL_PRECISION_DROP,
                     "overall_precision_guard"),
                ) if not test
            ],
        })
    qualified = [c for c in candidates if c["eligible"]]
    if not qualified:
        return {
            "status": "retain_baseline",
            "reason": "No sensitivity preset passes all fixed validation-only gates",
            "candidates": candidates,
        }
    # Primary objective recall; tie-break by F1 and least-aggressive preset.
    order = list(PRESETS)
    best = max(qualified, key=lambda c: (
        c["hat_recall_delta"], summaries[c["preset"]]["closed_hi_hat"]["f1"],
        -order.index(c["preset"]),
    ))
    return {
        "status": "validation_candidate_only",
        "preset": best["preset"],
        "reason": "Candidate for future independent confirmation; NOT auto-applied",
        "candidates": candidates,
    }


def evaluate_validation_pairs(
    records: list[dict],
    *,
    transcriber=transcribe_drum_wav,
) -> dict:
    if not records:
        raise ValueError("Validation requires one or more paired recordings")
    results = {name: [] for name in PRESETS}
    for rec in records:
        if not rec.get("song_id") or "truth" not in rec or "wav" not in rec:
            raise ValueError("Incomplete input validation record")
        for name, config in PRESETS.items():
            started = time.perf_counter()
            midi, _ = transcriber(rec["wav"], hat_config=config)
            elapsed = time.perf_counter() - started
            scores = evaluate_common_ontology(
                rec["truth"], midi, prediction_namespace="gm"
            )
            results[name].append({
                "song_id": rec["song_id"], "seconds": elapsed, "result": scores
            })
    summaries = {name: _aggregate(rows) for name, rows in results.items()}
    return {
        "schema_version": "1",
        "evaluation_partition": "official_upstream_validation_only",
        "dataset": VALIDATION_DATASET,
        "audio_domain": "electronic_kit_recording",
        "preset_revision": PRESET_REVISION,
        "preset_sha256": preset_sha256(),
        "pre_registered_gates": {
            "min_hi_hat_recall_gain": MIN_HAT_RECALL_GAIN,
            "max_hat_precision_drop": MAX_HAT_PRECISION_DROP,
            "max_overall_precision_drop": MAX_ALL_PRECISION_DROP,
            "min_hat_precision": MIN_HAT_PRECISION_ABSOLUTE,
        },
        "summary_by_preset": summaries,
        "recommendation": _recommend(summaries),
        "production_default_unchanged": True,
        "heldout_test_scores_unaffected": True,
        "warning": "Validation-only parameter selection; independent Test evaluation not performed.",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        records = validate_validation_manifest(args.manifest)
        report = evaluate_validation_pairs(records)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({
            "samples": len(records), "recommendation": report["recommendation"],
            "output": str(args.output),
        }, ensure_ascii=False, indent=2))
    except (ValueError, OSError, EOFError, PermissionError, RuntimeError) as exc:
        parser.exit(1, f"VALIDATION BENCHMARK BLOCKED: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
