"""Rights-gated multi-song drum benchmark on pre-aligned WAV + GM MIDI.

- Never downloads datasets.
- Reports real and synthetic recordings separately.
- Requires both audio AND annotation rights evidence on each sample.
- Uses exact GM drum note pitches with a 50 ms onset tolerance.
- Keeps individual failures visible, never silently removes hard examples.

This is engineering validation, not independent legal verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import tempfile
import time
import wave
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

import pretty_midi

from midivolt.adt_str import transcribe_adt_str
from midivolt.compare_drums import evaluate_drums, drum_events
from midivolt.drums import transcribe_drum_wav

DOMAINS = ("real_recording", "synthetic_rendered")
ENGINES = ("dsp", "adt_str")
# GM note families are for coverage ONLY; scoring remains exact-pitch.
GM_FAMILIES = {
    "kick": {35, 36},
    "snare": {37, 38, 39, 40},
    "hi_hat": {42, 44, 46},
    "tom": {41, 43, 45, 47, 48, 50},
    "ride": {51, 53, 59},
    "crash": {49, 52, 55, 57},
}
SHA_RE = __import__("re").compile(r"^[0-9a-f]{64}$")


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _within_folder(folder: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Audio and MIDI paths must be non-empty relative paths.")
    base = folder.resolve()
    full = (base / relative).resolve()
    if not full.is_relative_to(base):
        raise ValueError("Dataset paths may not escape the manifest folder.")
    if not full.is_file():
        raise ValueError("Required dataset file is missing: " + relative)
    return full


def _validate_entry(entry: dict, root: Path, allow_synthetic: bool) -> dict:
    required_strings = (
        "sample_id", "source_song_id", "performance_id", "split",
        "audio_domain", "audio_path", "reference_midi_path",
        "audio_sha256", "midi_sha256", "provenance_url",
    )
    if not isinstance(entry, dict):
        raise ValueError("Sample record must be an object.")
    for key in required_strings:
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            raise ValueError(f"Missing or invalid {key} for sample {entry.get('sample_id')}")
    if entry["split"] != "test":
        raise ValueError(f"{entry['sample_id']}: benchmark only accepts held-out test recordings")
    domain = entry["audio_domain"]
    if domain not in DOMAINS:
        raise ValueError(f"{entry['sample_id']}: audio_domain must be one of {DOMAINS}")
    if domain != "real_recording" and not allow_synthetic:
        raise ValueError("Synthetic examples require --include-synthetic and separate reporting")
    rights = entry.get("rights")
    if not isinstance(rights, dict):
        raise ValueError(f"{entry['sample_id']}: missing rights review")
    for field in ("audio_license", "midi_license", "evidence_url", "reviewer", "attribution"):
        if not isinstance(rights.get(field), str) or not rights[field].strip():
            raise ValueError(f"{entry['sample_id']}: rights.{field} is required")
    if rights.get("status") != "approved" or rights.get("commercial_benchmark_allowed") is not True:
        raise ValueError(f"{entry['sample_id']}: missing approved commercial benchmark permission")
    if not str(rights["evidence_url"]).startswith(("https://", "http://")):
        raise ValueError(f"{entry['sample_id']}: rights.evidence_url must be HTTP(S)")
    if not str(entry["provenance_url"]).startswith(("https://", "http://")):
        raise ValueError(f"{entry['sample_id']}: provenance_url must be HTTP(S)")
    if not all(isinstance(x, str) for x in entry.get("technique_tags", [])):
        raise ValueError(f"{entry['sample_id']}: invalid technique_tags")
    path = _within_folder(root, entry["audio_path"])
    reference_path = _within_folder(root, entry["reference_midi_path"])
    for field, file in (("audio_sha256", path), ("midi_sha256", reference_path)):
        checksum = entry[field].lower()
        if not SHA_RE.fullmatch(checksum):
            raise ValueError(f"{entry['sample_id']}: invalid SHA-256 for {field}")
        if _hash_file(file) != checksum:
            raise ValueError(f"{entry['sample_id']}: SHA-256 mismatch for {field}")
    if path.suffix.lower() != ".wav" or reference_path.suffix.lower() not in (".mid", ".midi"):
        raise ValueError(f"{entry['sample_id']}: expected WAV and MIDI files")
    with wave.open(str(path), "rb") as f:
        if f.getcomptype() != "NONE":
            raise ValueError(f"{entry['sample_id']}: compressed WAV not supported")
        duration = f.getnframes() / f.getframerate()
        sr = f.getframerate()
    if duration <= 0:
        raise ValueError(f"{entry['sample_id']}: empty audio")
    truth = pretty_midi.PrettyMIDI(str(reference_path))
    events = drum_events(truth)
    if events and max(n.start for n in events) > duration + 0.1:
        raise ValueError(f"{entry['sample_id']}: MIDI onset beyond WAV duration; check alignment")
    if not events:
        raise ValueError(f"{entry['sample_id']}: no reference drum events")
    return {
        "entry": entry, "wav": path, "reference_path": reference_path,
        "truth": truth, "duration": duration, "sample_rate": sr,
    }


def validate_dataset(manifest_path: Path, *, include_synthetic=False) -> list[dict]:
    manifest_path = Path(manifest_path).resolve()
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != "1":
        raise ValueError("Dataset manifest must be an object with schema_version = '1'")
    records = raw.get("samples")
    if not isinstance(records, list) or not records:
        raise ValueError("No test samples provided: real drum benchmark cannot be claimed")
    validated = []
    sample_ids = set()
    song_splits = {}
    for entry in records:
        checked = _validate_entry(entry, manifest_path.parent, include_synthetic)
        ident = entry["sample_id"]
        if ident in sample_ids:
            raise ValueError("Duplicate sample_id: " + ident)
        sample_ids.add(ident)
        song = entry["source_song_id"]
        if song in song_splits and song_splits[song] != entry["split"]:
            raise ValueError("Song-level train/test split leakage")
        song_splits[song] = entry["split"]
        validated.append(checked)
    return validated


def _score_counts(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else (1.0 if not fn else 0.0)
    recall = tp / (tp + fn) if tp + fn else (1.0 if not fp else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 6),
            "recall": round(recall, 6), "f1": round(f1, 6)}


def _summarize(records: list[dict]) -> dict:
    """Aggregate only one domain and one engine, by song and by drum pitch."""
    if not records:
        return {"sample_count": 0, "song_count": 0}
    per_song = defaultdict(list)
    pitch_count = defaultdict(Counter)
    for r in records:
        per_song[r["song_id"]].append(r)
        for pitch, values in r["scores"]["per_gm_pitch"].items():
            for key in ("tp", "fp", "fn"):
                pitch_count[pitch][key] += values[key]
    songs = {}
    total = Counter()
    for song, samples in sorted(per_song.items()):
        count = Counter()
        for sample in samples:
            for k in ("tp", "fp", "fn"):
                count[k] += sample["scores"]["micro"][k]
        songs[song] = _score_counts(count["tp"], count["fp"], count["fn"])
        total.update(count)
    per_pitch = {
        pitch: _score_counts(data["tp"], data["fp"], data["fn"])
        for pitch, data in sorted(pitch_count.items(), key=lambda p: int(p[0]))
    }
    family_coverage = {
        family: sorted(
            int(pitch) for pitch, values in per_pitch.items()
            if int(pitch) in notes and values["tp"] + values["fn"] > 0
        )
        for family, notes in GM_FAMILIES.items()
    }
    times = sorted(r["seconds"] for r in records)
    realtime_factors = sorted(r["realtime_factor"] for r in records)
    return {
        "sample_count": len(records),
        "song_count": len(songs),
        "failure_count": sum(bool(r.get("failed", False)) for r in records),
        "song_macro_f1": round(statistics.mean(v["f1"] for v in songs.values()), 6),
        "event_micro": _score_counts(total["tp"], total["fp"], total["fn"]),
        "per_song": songs,
        "per_pitch": per_pitch,
        "gm_family_coverage": family_coverage,
        "latency_seconds_median": round(statistics.median(times), 4),
        "latency_seconds_p95_nearest_rank": round(times[math.ceil(0.95 * len(times)) - 1], 4),
        "realtime_factor_median": round(statistics.median(realtime_factors), 4),
        "real_kit_coverage_complete": all(family_coverage.values()),
    }


def run_suite(
    manifest_path: Path,
    *,
    output_dir: Path,
    include_synthetic=False,
    engines=("dsp",),
    research_only=False,
    adt_root: Path | None = None,
    adt_checkpoint: Path | None = None,
    adt_python: str | None = None,
    dsp_predict: Callable | None = None,
    adt_predict: Callable | None = None,
) -> dict:
    if not engines or any(engine not in ENGINES for engine in engines) or len(set(engines)) != len(engines):
        raise ValueError(f"Select one or more unique engines from {ENGINES}")
    if "adt_str" in engines and not research_only:
        raise PermissionError("ADT_STR requires --research-only and is not approved for commercial release")
    # Validate ALL samples, including license evidence and exact bytes, before
    # *any* model runs or output files are produced.
    entries = validate_dataset(manifest_path, include_synthetic=include_synthetic)
    predictions = {"dsp": dsp_predict, "adt_str": adt_predict}
    output = Path(output_dir)
    if output.resolve() in (Path(manifest_path).resolve().parent,):
        raise ValueError("Output must not be the dataset manifest directory.")
    sample_results = []
    for checked in entries:
        entry, wav, reference = checked["entry"], checked["wav"], checked["truth"]
        for engine in engines:
            started = time.perf_counter()
            failed = False
            try:
                if engine == "dsp":
                    if predictions[engine] is not None:
                        midi, diagnostics = predictions[engine](wav)
                    else:
                        midi, diagnostics = transcribe_drum_wav(wav)
                else:
                    if predictions[engine] is not None:
                        midi, diagnostics = predictions[engine](wav)
                    else:
                        midi, diagnostics = transcribe_adt_str(
                            wav, tempo=120, repo_root=adt_root, checkpoint=adt_checkpoint,
                            python_executable=adt_python, research_only=research_only,
                        )
                if not isinstance(midi, pretty_midi.PrettyMIDI):
                    raise TypeError(f"Engine {engine} returned no MIDI.")
                scores = evaluate_drums(reference, midi)
            except Exception as exc:
                # An inference failure counts as all-reference-note misses, not
                # as an omitted hard song that would inflate reported F1.
                failed = True
                midi = pretty_midi.PrettyMIDI()
                midi.instruments.append(pretty_midi.Instrument(program=0, is_drum=True))
                diagnostics = {"error_type": type(exc).__name__, "error": str(exc)[:400]}
                scores = evaluate_drums(reference, midi)
            seconds = time.perf_counter() - started
            sample_results.append({
                "sample_id": entry["sample_id"],
                "song_id": entry["source_song_id"],
                "performance_id": entry["performance_id"],
                "audio_domain": entry["audio_domain"],
                "technique_tags": entry.get("technique_tags", []),
                "engine": engine,
                "failed": failed,
                "duration_seconds": round(checked["duration"], 4),
                "sample_rate_hz": checked["sample_rate"],
                "seconds": round(seconds, 4),
                "realtime_factor": round(seconds / checked["duration"], 6),
                "scores": scores,
                "model_details": diagnostics,
            })
    grouped = {}
    for domain in DOMAINS:
        grouped[domain] = {}
        for engine in engines:
            data = [r for r in sample_results if r["audio_domain"] == domain and r["engine"] == engine]
            grouped[domain][engine] = _summarize(data)
    report = {
        "schema_version": "1",
        "kind": "rights_reviewed_multisong_drum_evaluation",
        "reference": "held-out GM percussion MIDI, unquantized predicted onset, 50ms tolerance",
        "reference_license": "metadata self-declared; independent legal review required",
        "real_recordings_present": bool(grouped["real_recording"][engines[0]]["sample_count"]),
        "real_coverage_gate": {
            "minimum_song_count": 5,
            "enough_distinct_songs": grouped["real_recording"][engines[0]]["song_count"] >= 5,
            "reference_gm_families_covered": bool(
                grouped["real_recording"][engines[0]].get("real_kit_coverage_complete", False)
            ),
            "no_inference_failures": all(
                grouped["real_recording"][engine].get("failure_count", 0) == 0
                for engine in engines
            ),
            "note": "Coverage screening only, not statistical model validation or legal clearance",
        },
        "synthetic_scores_separate": True,
        "commercial_model_status": {"dsp": "dependency_review_pending", "adt_str": "research_only"},
        "engines": list(engines),
        "by_audio_domain": grouped,
        "samples": sample_results,
        "warning": "No model is proven best for real drums until a sufficiently diverse held-out dataset "
                   "and all model/data rights have been reviewed.",
    }
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output, suffix=".tmp", delete=False) as t:
        json.dump(report, t, ensure_ascii=False, indent=2)
        t.write("\n")
        staged = Path(t.name)
    os.replace(staged, output / "drum_suite_report.json")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run rights-gated multi-song drum benchmark")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engines", nargs="+", choices=ENGINES, default=["dsp"])
    parser.add_argument("--include-synthetic", action="store_true",
                        help="Allow synthetic samples but report separately from real recordings")
    parser.add_argument("--research-only", action="store_true")
    parser.add_argument("--adt-root", type=Path)
    parser.add_argument("--adt-checkpoint", type=Path)
    parser.add_argument("--adt-python")
    args = parser.parse_args(argv)
    try:
        report = run_suite(
            args.manifest, output_dir=args.output, include_synthetic=args.include_synthetic,
            engines=tuple(args.engines), research_only=args.research_only,
            adt_root=args.adt_root, adt_checkpoint=args.adt_checkpoint,
            adt_python=args.adt_python,
        )
    except (OSError, ValueError, RuntimeError, PermissionError, EOFError) as exc:
        parser.exit(1, f"DRUM BENCHMARK BLOCKED: {exc}\n")
    print(json.dumps({
        "real_recordings_present": report["real_recordings_present"],
        "engines": report["engines"],
        "by_audio_domain": report["by_audio_domain"],
        "report": str(Path(args.output) / "drum_suite_report.json"),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
