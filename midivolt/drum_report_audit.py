"""Offline, read-only audit of MIDIVOLT held-out drum benchmark JSON.

The output is a diagnostics report, NEVER a re-scored or "fixed" test F1.
Only aggregated counters and known selection metadata are used.
No remote requests, third-party model weights, or raw drum WAVs are needed.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


SENSITIVE_ALIGNMENT = {
    "suspected_offset",
    "insufficient_confident_events",
    "insufficient_audio_transients",
    "inconclusive",
}
DRUM_LABELS = {
    35: "Acoustic Bass Drum",
    36: "Bass Drum 1",
    37: "Side Stick",
    38: "Acoustic Snare",
    40: "Electric Snare",
    41: "Low Floor Tom",
    42: "Closed Hi-hat",
    43: "High Floor Tom",
    44: "Pedal Hi-hat",
    45: "Low Tom",
    46: "Open Hi-hat",
    48: "Hi-Mid Tom",
    49: "Crash Cymbal 1",
    51: "Ride Cymbal 1",
    52: "Chinese Cymbal",
    55: "Splash Cymbal",
    58: "Vibraslap (GM); Roland alternate drum mapping candidate",
}
# Only possible label disagreements. Counts alone do not prove that
# an unmatched prediction and reference onset are the same performance event.
LABEL_HYPOTHESES = {
    (35, 36): "Two separate standard GM kick pitches; decide canonical policy before held-out scoring.",
    (58, 43): "A Roland vendor-specific tom number versus normalized GM reference; inspect actual note pairs.",
    (40, 38): "Electric Snare versus Acoustic Snare; distinct pitches in exact-GM scoring.",
    (44, 42): "Pedal Hi-hat versus Closed Hi-hat; distinct articulations, must not collapse silently.",
}


def _count(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _scores(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else (1.0 if fn == 0 else 0.0)
    recall = tp / (tp + fn) if (tp + fn) else (1.0 if fp == 0 else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _validate_score(section: dict, context: str) -> dict:
    if not isinstance(section, dict):
        raise ValueError(f"{context}: missing score object")
    tp, fp, fn = (_count(section.get(key), context + "." + key) for key in ("tp", "fp", "fn"))
    expected = _scores(tp, fp, fn)
    for key in ("precision", "recall", "f1"):
        got = section.get(key)
        if isinstance(got, bool) or not isinstance(got, (int, float)) or not math.isfinite(got):
            raise ValueError(f"{context}: missing/invalid {key}")
        if abs(got - expected[key]) > 0.00001:
            raise ValueError(f"{context}: inconsistent {key}; refusing to audit corrupted metrics")
    return expected


def _song_identity(report: dict) -> tuple[dict, dict]:
    samples = report.get("samples")
    provenance = report.get("sample_provenance")
    if not isinstance(samples, list) or not samples:
        raise ValueError("Missing per-engine samples")
    if not isinstance(provenance, list) or not provenance:
        raise ValueError("Missing per-song source provenance")
    songs = {}
    for p in provenance:
        if not isinstance(p, dict) or not isinstance(p.get("source_song_id"), str):
            raise ValueError("Malformed song provenance")
        song = p["source_song_id"]
        if song in songs:
            raise ValueError("Duplicate source song identity in provenance")
        if p.get("source_split") != "test":
            raise ValueError("Non-held-out song in benchmark: " + song)
        if p.get("kit_name") != "Acoustic Kit":
            raise ValueError("Cannot compare differing drum-kit renderings in this fixed pilot")
        songs[song] = p

    pair = defaultdict(dict)
    for index, row in enumerate(samples):
        if not isinstance(row, dict):
            raise ValueError("Malformed sample row")
        engine, song = row.get("engine"), row.get("song_id")
        if engine not in ("dsp", "adt_str") or song not in songs:
            raise ValueError(f"Sample {index}: unknown engine/song")
        if engine in pair[song]:
            raise ValueError(f"Duplicate engine observation for {song}/{engine}")
        if row.get("failed") is True:
            # Keep failed inference in the report rather than treating it as a win.
            pass
        elif row.get("failed") is not False:
            raise ValueError("Inference failure state must be explicit")
        if row.get("audio_domain") != "electronic_kit_recording":
            raise ValueError("Mixed audio domains cannot share headline scores")
        pair[song][engine] = row
    if set(pair) != set(songs) or any(set(x) != {"dsp", "adt_str"} for x in pair.values()):
        raise ValueError("Both engines must be present for every identical held-out song")
    return songs, pair


def audit_report(report: dict) -> dict:
    if not isinstance(report, dict) or report.get("status") != "research_only_completed":
        raise ValueError("Require a completed research-only benchmark JSON")
    if report.get("dataset") != "E-GMD v1.0.0":
        raise ValueError("Audit is explicitly scoped to E-GMD v1.0.0")
    if report.get("dataset_type") != "human_performed_electronic_drumkit_audio_NOT_direct_acoustic_drums":
        raise ValueError("Unrecognized recording domain; refuse to misrepresent acoustic drums")
    songs, pair = _song_identity(report)
    summary = report.get("performance_by_engine")
    if not isinstance(summary, dict) or set(summary) != {"dsp", "adt_str"}:
        raise ValueError("Require matched DSP and ADT_STR engine summaries")

    rechecked = {}
    coverage = {}
    for engine in ("dsp", "adt_str"):
        output = summary[engine]
        if output.get("sample_count") != len(songs) or output.get("song_count") != len(songs):
            raise ValueError(f"{engine}: summary counts do not match provenance")
        counted = Counter()
        pitches = defaultdict(Counter)
        for song, engines in pair.items():
            row = engines[engine]
            score_obj = row.get("scores", {})
            micro = _validate_score(score_obj.get("micro"), f"{song}.{engine}.micro")
            for k in ("tp", "fp", "fn"):
                counted[k] += micro[k]
            event_pitch = score_obj.get("per_gm_pitch")
            if not isinstance(event_pitch, dict):
                raise ValueError(f"{song}.{engine}: missing per-GM-pitch results")
            local_count = Counter()
            for pitch, metric in event_pitch.items():
                if not isinstance(pitch, str) or not pitch.isdecimal():
                    raise ValueError("Invalid GM pitch key")
                numeric = int(pitch)
                if numeric < 0 or numeric > 127:
                    raise ValueError("GM pitch exceeds MIDI note range")
                result = _validate_score(metric, f"{song}.{engine}.{pitch}")
                for key in ("tp", "fp", "fn"):
                    pitches[pitch][key] += result[key]
                    local_count[key] += result[key]
            if any(local_count[key] != micro[key] for key in ("tp", "fp", "fn")):
                raise ValueError(f"{song}.{engine}: pitch totals differ from sample totals")
        expected = _scores(counted["tp"], counted["fp"], counted["fn"])
        actual = _validate_score(output.get("event_micro"), f"{engine}.event_micro")
        if any(expected[key] != actual[key] for key in ("tp", "fp", "fn")):
            raise ValueError(f"{engine}: published aggregate differs from individual samples")

        failure_count = sum(bool(s[engine]["failed"]) for s in pair.values())
        if output.get("failure_count") != failure_count:
            raise ValueError(f"{engine}: failure counts differ")
        rechecked[engine] = {
            "sample_count": len(songs),
            "failure_count": failure_count,
            "event_micro": expected,
            "song_macro_f1_from_original_report": output.get("song_macro_f1"),
            "median_runtime_seconds_from_original_report": output.get("latency_seconds_median"),
        }
        coverage[engine] = {
            pitch: {
                "name": DRUM_LABELS.get(int(pitch), "Other GM percussion"),
                "reference_events": counts["tp"] + counts["fn"],
                "predicted_events": counts["tp"] + counts["fp"],
                "tp": counts["tp"], "fp": counts["fp"], "fn": counts["fn"],
                "recall": round(counts["tp"] / (counts["tp"] + counts["fn"]), 6)
                    if counts["tp"] + counts["fn"] else None,
            }
            for pitch, counts in sorted(pitches.items(), key=lambda kv: int(kv[0]))
        }

    reference_counts = {p: s["reference_events"] for p, s in coverage["dsp"].items() if s["reference_events"]}
    for pitch, value in reference_counts.items():
        if coverage["adt_str"].get(pitch, {}).get("reference_events", 0) != value:
            raise ValueError(f"Different ground-truth drum events for pitch {pitch}")
    # An engine may hallucinate a pitch missing in the reference. Check all
    # reference pitches from both engines, including those absent from DSP.
    all_reference = {
        pitch for model in coverage.values() for pitch, r in model.items() if r["reference_events"]
    }
    for pitch in all_reference:
        if coverage["dsp"].get(pitch, {}).get("reference_events", 0) != (
            coverage["adt_str"].get(pitch, {}).get("reference_events", 0)
        ):
            raise ValueError(f"Ground truth mismatch between engines at pitch {pitch}")

    alignment = []
    for song, engines in sorted(pair.items()):
        first, second = engines["dsp"], engines["adt_str"]
        a, b = first.get("alignment_quality"), second.get("alignment_quality")
        if not isinstance(a, dict) or a != b:
            raise ValueError(f"{song}: alignment diagnostics must agree for both engines")
        status = a.get("status", "missing")
        alignment.append({
            "song_id": song,
            "drummer": songs[song].get("drummer"),
            "status": status,
            "review_needed": status in SENSITIVE_ALIGNMENT or status == "missing",
            "median_audio_minus_midi_ms": a.get("median_audio_minus_midi_ms"),
            "dsp_f1": first["scores"]["micro"]["f1"],
            "adt_str_f1": second["scores"]["micro"]["f1"],
        })

    worst_misses = sorted(
        (
            {"pitch": int(p), "name": data["name"], "reference_events": data["reference_events"],
             "dsp_misses": data["fn"], "adt_str_misses": coverage["adt_str"].get(p, {}).get("fn", 0)}
            for p, data in coverage["dsp"].items() if data["reference_events"]
        ),
        key=lambda x: (-max(x["dsp_misses"], x["adt_str_misses"]), x["pitch"]),
    )
    candidates = []
    for (predicted, reference), reason in LABEL_HYPOTHESES.items():
        p, r = str(predicted), str(reference)
        ai_pred = coverage["adt_str"].get(p, {})
        ground = coverage["adt_str"].get(r, {})
        if ai_pred.get("fp", 0) and ground.get("fn", 0):
            candidates.append({
                "predicted_gm_pitch": predicted,
                "reference_gm_pitch": reference,
                "unmatched_predictions_at_predicted_pitch": ai_pred["fp"],
                "missed_reference_notes_at_reference_pitch": ground["fn"],
                "note": reason,
                "proven_pairing": False,
                "requires_original_midi_event_timings": True,
            })

    return {
        "schema_version": "1",
        "mode": "read_only_posthoc_diagnostic_no_rescoring",
        "dataset": report["dataset"],
        "audio_domain": "human_performed_electronic_kit_not_acoustic_microphones",
        "heldout_test_only": True,
        "evaluated_song_count": len(songs),
        "independent_drummer_count": len({p.get("drummer") for p in songs.values()}),
        "engines": rechecked,
        "rejected_alignment_or_inconclusive": [x for x in alignment if x["review_needed"]],
        "all_song_alignment": alignment,
        "worst_reference_misses": worst_misses[:12],
        "per_gm_pitch": coverage,
        "representation_mismatch_hypotheses": candidates,
        "commercial_release_gate": {
            "allowed": False,
            "reasons": [
                "ADT_STR model checkpoint rights unreviewed",
                "Electronic-kit test recordings are not live acoustic microphone recordings",
                "Some clips have uncertain or suspect time alignment",
                "This benchmark is held out and must not be used for threshold tuning",
                "All claimed drum families need suitable representative ground truth",
            ],
        },
        "explicit_non_actions": [
            "No F1 changed or re-labelled post hoc",
            "No score-driven threshold tuning",
            "No prediction notes remapped by this report",
            "No claim that aggregate pitch mismatch counters prove coincident musical events",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True, help="GitHub E-GMD research_metrics.json")
    ap.add_argument("--output", type=Path, required=True, help="audited JSON evidence")
    args = ap.parse_args(argv)
    try:
        result = audit_report(json.loads(args.input.read_text(encoding="utf-8")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        ap.exit(1, f"MIDIVOLT benchmark audit failed: {exc}\n")
    print(json.dumps({
        "songs": result["evaluated_song_count"],
        "needs_alignment_review": len(result["rejected_alignment_or_inconclusive"]),
        "dsp_f1": result["engines"]["dsp"]["event_micro"]["f1"],
        "adt_str_f1": result["engines"]["adt_str"]["event_micro"]["f1"],
        "report": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
