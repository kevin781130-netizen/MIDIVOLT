"""Verify E-GMD GM pitch onset replay against a frozen earlier benchmark.

Can read GitHub's published research_metrics.json or ZIP artifact. Requires
same WAV/MIDI SHA-256, same model revision and original per-song scores before
calling any new onset pairing comparable. NEVER changes held-out F1.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

CANDIDATES = ((35, 36), (58, 43))
ENGINES = ("dsp", "adt_str")
SOURCE_KIND = "human_performed_electronic_drumkit_audio_NOT_direct_acoustic_drums"


def load_metrics(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [
                name for name in archive.namelist()
                if name == "research_metrics.json" or name.endswith("/research_metrics.json")
            ]
            if len(names) != 1:
                raise ValueError("ZIP must contain exactly one research_metrics.json")
            data = json.loads(archive.read(names[0]))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Benchmark report must be an object")
    return data


def _index(report: dict) -> tuple[dict, dict]:
    if report.get("status") != "research_only_completed" or report.get("dataset") != "E-GMD v1.0.0":
        raise ValueError("Expected completed official E-GMD research test report")
    if report.get("dataset_type") != SOURCE_KIND:
        raise ValueError("Refusing different audio domain")
    source = report.get("sample_provenance")
    if not isinstance(source, list) or not source:
        raise ValueError("Report missing sample provenance")
    provenance = {}
    for record in source:
        song = record.get("source_song_id")
        if not isinstance(song, str) or not song or song in provenance:
            raise ValueError("Missing/duplicate song provenance")
        for key in ("wav_sha256", "midi_sha256"):
            value = record.get(key)
            if (
                not isinstance(value, str) or len(value) != 64
                or not all(c in "0123456789abcdef" for c in value)
            ):
                raise ValueError(f"Missing/invalid source SHA-256 {song}/{key}")
        if record.get("source_split") != "test":
            raise ValueError("Test/train leakage")
        provenance[song] = record
    samples = report.get("samples")
    if not isinstance(samples, list):
        raise ValueError("Missing samples")
    pairs = {}
    for sample in samples:
        song, engine = sample.get("song_id"), sample.get("engine")
        if song not in provenance or engine not in ENGINES:
            raise ValueError("Unknown song or engine")
        key = (song, engine)
        if key in pairs:
            raise ValueError("Duplicate engine/song evidence")
        if sample.get("failed") is not False:
            raise ValueError("Incomplete model inference: evidence cannot prove a mapping")
        if sample.get("audio_domain") != "electronic_kit_recording":
            raise ValueError("Mixed microphone and electronic-kit scores")
        pairs[key] = sample
    if len(pairs) != 2 * len(provenance):
        raise ValueError("Missing paired engine observation")
    return provenance, pairs


def _counts(sample: dict) -> tuple[int, int, int]:
    raw = sample.get("scores", {}).get("micro", {})
    values = tuple(raw.get(key) for key in ("tp", "fp", "fn"))
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Invalid sample TP/FP/FN")
    return values


def _hypothesis_bounds(pairs: dict, songs: dict, predicted: int, reference: int) -> dict:
    per_song = []
    for song in sorted(songs):
        pitch = pairs[(song, "adt_str")].get("scores", {}).get("per_gm_pitch", {})
        fp = int(pitch.get(str(predicted), {}).get("fp", 0))
        fn = int(pitch.get(str(reference), {}).get("fn", 0))
        if fp < 0 or fn < 0:
            raise ValueError("Invalid pitch FP/FN")
        per_song.append({
            "song_id": song, "source_extra": fp, "target_missed": fn,
            "same_song_upper_bound": min(fp, fn),
        })
    return {
        "predicted_pitch": predicted, "reference_pitch": reference,
        "unmatched_predictions": sum(x["source_extra"] for x in per_song),
        "missed_reference_notes": sum(x["target_missed"] for x in per_song),
        "max_possible_same_song_pairs": sum(x["same_song_upper_bound"] for x in per_song),
        "per_song": per_song,
        "actual_onset_pairs_known": False,
    }


def build_evidence(original: dict, replay: dict | None = None) -> dict:
    source, paired = _index(original)
    bounds = [_hypothesis_bounds(paired, source, src, ref) for src, ref in CANDIDATES]
    result = {
        "schema_version": "1",
        "analysis": "heldout_same_song_label_pair_evidence",
        "status": "awaiting_actual_predicted_MIDI_onsets" if replay is None else "replay_checked",
        "recording_type": "human_performed_electronic_kit_NOT_live_acoustic_mics",
        "original_song_count": len(source),
        "original_heldout_scores_unchanged": True,
        "model": original.get("model"),
        "selection_plan_sha256": original.get("selection_plan_sha256"),
        "hypotheses": bounds,
        "note": "Same-song count upper bounds are NOT evidence of matching onset timestamps.",
    }
    if replay is None:
        return result
    updated_source, updated_pairs = _index(replay)
    if original.get("selection_plan_sha256") != replay.get("selection_plan_sha256"):
        raise ValueError("Different selection-plan hash; cannot compare replay")
    if original.get("model") != replay.get("model"):
        raise ValueError("Different ADT_STR model revision/checkpoint metadata")
    if set(source) != set(updated_source):
        raise ValueError("Changed song selection")
    for song in source:
        for key in ("wav_sha256", "midi_sha256", "source_split", "kit_name"):
            if source[song].get(key) != updated_source[song].get(key):
                raise ValueError(f"Changed source identity: {song}/{key}")

    delta = []
    for song in sorted(source):
        for engine in ENGINES:
            old = _counts(paired[(song, engine)])
            new = _counts(updated_pairs[(song, engine)])
            if old != new:
                delta.append({
                    "song_id": song, "engine": engine,
                    "original_tp_fp_fn": old, "replay_tp_fp_fn": new,
                })
    observations = []
    for song in sorted(source):
        for engine in ENGINES:
            old = paired[(song, engine)]
            new = updated_pairs[(song, engine)]
            if old.get("alignment_quality") != new.get("alignment_quality"):
                raise ValueError(f"Alignment QC drift: {song}/{engine}")
            label = new.get("label_timing_diagnostic")
            if not isinstance(label, dict):
                raise ValueError(f"No actual MIDI label-timing diagnostic for {song}/{engine}")
            exact = label.get("original_exact_gm", {})
            if tuple(exact.get(k) for k in ("tp", "fp", "fn")) != _counts(new):
                raise ValueError(f"Label diagnostic does not match exact scoring: {song}/{engine}")
            if engine == "adt_str":
                for candidate in label.get("label_hypotheses", []):
                    pair = (candidate.get("predicted_pitch"), candidate.get("reference_pitch"))
                    if pair not in CANDIDATES:
                        continue
                    count = candidate.get("paired_within_tolerance")
                    if type(count) is not int or count < 0:
                        raise ValueError("Invalid actual onset pairing count")
                    pitch = old["scores"]["per_gm_pitch"]
                    cap = min(
                        int(pitch.get(str(pair[0]), {}).get("fp", 0)),
                        int(pitch.get(str(pair[1]), {}).get("fn", 0)),
                    )
                    if not delta and count > cap:
                        raise ValueError("Pairing count exceeds original same-song bound")
                    observations.append({
                        "song_id": song,
                        "predicted_pitch": pair[0],
                        "reference_pitch": pair[1],
                        "onset_pairs": count,
                        "original_same_song_count_upper_bound": cap,
                        "aligned_enough_for_timing_claim": (
                            old.get("alignment_quality", {}).get("status")
                            == "no_large_offset_detected"
                        ),
                        "suggestive_onset_evidence": candidate.get("suggestive_onset_evidence") is True,
                        "proves_same_instrument": False,
                    })
    if delta:
        result["status"] = "not_comparable_replay_drift"
        result["score_drift"] = delta
        result["actual_pairing_conclusion_allowed"] = False
    else:
        result["status"] = "paired_onset_evidence_available"
        result["score_drift"] = []
        result["actual_pairing_conclusion_allowed"] = True
    result["paired_event_evidence"] = observations
    result["cautions"] = [
        "Actual time proximity does not prove drum decoder pitch semantics.",
        "Clips flagged for suspected WAV/MIDI offset cannot establish confident onset agreement.",
        "Never silently remap Test-set MIDI or change held-out F1 after analysis.",
    ]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = build_evidence(
            load_metrics(args.original),
            load_metrics(args.replay) if args.replay else None,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": data["status"], "output": str(args.output),
            "songs": data["original_song_count"],
        }, ensure_ascii=False))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"VERIFICATION FAILED: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
