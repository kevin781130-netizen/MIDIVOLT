"""Drum pitch-label confusion diagnosis using actual MIDI onset timestamps.

This is a read-only diagnostic. Exact pitch matches are reserved FIRST;
candidate cross-pitch matches can only use events still unmatched after the
original 50ms exact-GM score. The output does not remap notes or change F1.

Use this on independently aligned ground-truth/predicted MIDI from the SAME
audio stem. Deliberately no access to model parameters or waveform content.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pretty_midi

from midivolt.compare_drums import drum_events
from midivolt.evaluate import Event, matching

# Predicted pitch -> reference pitch. HYPOTHESES ONLY, not equivalences.
CANDIDATES = ((35, 36), (58, 43), (40, 38), (44, 42))
DEFAULT_TOLERANCE_MS = 50.0
# "Shift controls" approximate accidental alignment in repetitive drum parts.
NULL_SHIFTS_SECONDS = (0.137, 0.283)


def _matched_pairs(reference: list[Event], predicted: list[Event], tolerance_s: float):
    return matching(reference, predicted, tolerance_s, require_offset=False)


def _label_matches(
    truth: list[Event], predicted: list[Event],
    source_pitch: int, target_pitch: int, tolerance_s: float,
):
    # Keep the original one-to-one EXACT-GM note matches; a predicted note
    # cannot be both an exact match and a label-error suggestion.
    exact = _matched_pairs(truth, predicted, tolerance_s)
    truth_matched = {r for r, _ in exact}
    predicted_matched = {p for _, p in exact}
    truth_indices = [
        i for i, e in enumerate(truth)
        if e.pitch == target_pitch and i not in truth_matched
    ]
    predicted_indices = [
        i for i, e in enumerate(predicted)
        if e.pitch == source_pitch and i not in predicted_matched
    ]
    truths = [truth[i] for i in truth_indices]
    predicted_unmatched = [predicted[i] for i in predicted_indices]
    # Scoring for the hypothesis compares onset TIME ONLY and does not
    # modify the actual reported pitches, MIDI, or official F1.
    projected = [
        Event(pitch=target_pitch, start=n.start, end=n.end)
        for n in predicted_unmatched
    ]
    pairs = _matched_pairs(truths, projected, tolerance_s)
    return {
        "truths": truths, "predicted": predicted_unmatched,
        "pairs": [(truth_indices[r], predicted_indices[p]) for r, p in pairs],
        "exact_pairs_reserved": len(exact),
    }


def _offsets(truth: list[Event], pred: list[Event], pairs):
    ms = [(pred[p].start - truth[r].start) * 1000 for r, p in pairs]
    return {
        "onset_mae_ms": round(sum(map(abs, ms)) / len(ms), 3) if ms else None,
        "onset_bias_ms": round(sum(ms) / len(ms), 3) if ms else None,
        "nearest_max_abs_error_ms": round(max(map(abs, ms)), 3) if ms else None,
    }


def analyze_pitch_labels(
    reference_midi: pretty_midi.PrettyMIDI,
    predicted_midi: pretty_midi.PrettyMIDI,
    *,
    tolerance_ms: float = DEFAULT_TOLERANCE_MS,
    candidates=CANDIDATES,
) -> dict:
    if not math.isfinite(tolerance_ms) or not 1 <= tolerance_ms <= 200:
        raise ValueError("tolerance_ms must be finite between 1 and 200")
    truth = drum_events(reference_midi)
    pred = drum_events(predicted_midi)
    tol = tolerance_ms / 1000.0
    original_exact = _matched_pairs(truth, pred, tol)
    original_fp = len(pred) - len(original_exact)
    original_fn = len(truth) - len(original_exact)
    reports = []
    for source, target in candidates:
        if any(not isinstance(pitch, int) or not 0 <= pitch < 128 for pitch in (source, target)):
            raise ValueError("Candidate pitches must be valid MIDI integers")
        if source == target:
            raise ValueError("Cross-pitch candidate must have different pitches")
        outcome = _label_matches(truth, pred, source, target, tol)
        pairs = outcome["pairs"]
        control_counts = []
        for shift in NULL_SHIFTS_SECONDS:
            # Shift ONLY the candidate predicted events in a separate,
            # diagnostic copy, never the actual MIDI or exact match status.
            unmatched_truth = outcome["truths"]
            shifted = [
                Event(pitch=target, start=e.start + shift, end=e.end + shift)
                for e in outcome["predicted"]
            ]
            control_counts.append(
                len(_matched_pairs(unmatched_truth, shifted, tol))
            )
        enough_evidence = (
            len(pairs) >= 3 and
            len(pairs) > max(control_counts) and
            len(pairs) >= 2 * max(1, max(control_counts))
        )
        reports.append({
            "predicted_pitch": source,
            "reference_pitch": target,
            "unmatched_predicted_at_source_pitch": len(outcome["predicted"]),
            "unmatched_reference_at_target_pitch": len(outcome["truths"]),
            "paired_within_tolerance": len(pairs),
            "paired_fraction_of_source_extras": (
                round(len(pairs) / len(outcome["predicted"]), 6)
                if outcome["predicted"] else None
            ),
            "paired_fraction_of_target_misses": (
                round(len(pairs) / len(outcome["truths"]), 6)
                if outcome["truths"] else None
            ),
            **_offsets(truth, pred, pairs),
            "shifted_null_control_pair_counts": dict(
                zip((str(x) for x in NULL_SHIFTS_SECONDS), control_counts)
            ),
            "suggestive_onset_evidence": enough_evidence,
            "proves_same_instrument": False,
            "requires_decoder_and_instrument_schema_review": bool(pairs),
        })

    return {
        "schema_version": "1",
        "mode": "read_only_original_exact_matches_reserved",
        "onset_tolerance_ms": tolerance_ms,
        "reference_events": len(truth),
        "predicted_events": len(pred),
        "original_exact_gm": {
            "tp": len(original_exact), "fp": original_fp, "fn": original_fn
        },
        "label_hypotheses": reports,
        "limits": [
            "A near-simultaneous event does not establish instrument identity.",
            "Shifted-control coincidences can be high in periodic drum grooves.",
            "No predictions or truth were relabeled, moved or quantized.",
            "Official F1 must remain unchanged; use this only for error diagnosis.",
            "Uncertain audio/MIDI alignment can suppress true candidate matches.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--predicted", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance-ms", type=float, default=DEFAULT_TOLERANCE_MS)
    args = parser.parse_args(argv)
    try:
        if not args.reference.is_file() or not args.predicted.is_file():
            raise ValueError("Both reference and prediction MIDI must exist locally")
        result = analyze_pitch_labels(
            pretty_midi.PrettyMIDI(str(args.reference)),
            pretty_midi.PrettyMIDI(str(args.predicted)),
            tolerance_ms=args.tolerance_ms,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, EOFError, TypeError) as exc:
        parser.exit(1, f"DRUM LABEL DIAGNOSTIC ERROR: {exc}\n")
    print(json.dumps({
        "original_exact_gm": result["original_exact_gm"],
        "label_hypotheses": result["label_hypotheses"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
