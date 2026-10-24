"""Deterministic note-event accuracy scoring against aligned reference MIDI.

Use on original (unquantized) predicted MIDI. Results are diagnostics, not a
universal quality score; reference and prediction must refer to the same stem.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import pretty_midi


@dataclass(frozen=True)
class Event:
    pitch: int
    start: float
    end: float


def notes(midi: pretty_midi.PrettyMIDI) -> list[Event]:
    """Flatten a single-stem MIDI; multi-track instrument labels are not scored."""
    out: list[Event] = []
    for instrument in midi.instruments:
        if instrument.is_drum:
            raise ValueError("Drum MIDI must be scored with a drum-specific event evaluator.")
        for note in instrument.notes:
            if not (math.isfinite(note.start) and math.isfinite(note.end)):
                raise ValueError("Nonfinite MIDI event time.")
            if note.end <= note.start:
                raise ValueError("Invalid note duration.")
            out.append(Event(int(note.pitch), float(note.start), float(note.end)))
    return sorted(out, key=lambda item: (item.start, item.pitch, item.end))


def matching(
    reference: list[Event],
    predicted: list[Event],
    onset_tolerance: float,
    require_offset: bool,
) -> list[tuple[int, int]]:
    """Maximum cardinality one-to-one matching, with deterministic tie ordering.

    A predicted note cannot match two reference notes. For strict notes the
    offset tolerance is max(50 ms, 20% of the ground-truth note duration).
    """
    links: list[list[int]] = []
    for ref in reference:
        candidates = []
        for i, pred in enumerate(predicted):
            if pred.pitch != ref.pitch or abs(pred.start - ref.start) > onset_tolerance:
                continue
            if require_offset and abs(pred.end - ref.end) > max(0.05, 0.2 * (ref.end - ref.start)):
                continue
            candidates.append(i)
        candidates.sort(key=lambda i: (
            abs(predicted[i].start - ref.start),
            abs(predicted[i].end - ref.end),
            i,
        ))
        links.append(candidates)

    claimed: dict[int, int] = {}

    def try_match(ref_index: int, seen: set[int]) -> bool:
        for pred_index in links[ref_index]:
            if pred_index in seen:
                continue
            seen.add(pred_index)
            if pred_index not in claimed or try_match(claimed[pred_index], seen):
                claimed[pred_index] = ref_index
                return True
        return False

    for ref_index in range(len(reference)):
        try_match(ref_index, set())
    return sorted(
        ((r, p) for p, r in claimed.items()),
        key=lambda pair: (reference[pair[0]].start, reference[pair[0]].pitch),
    )


def score(ref_count: int, pred_count: int, pairs: list[tuple[int, int]]) -> dict:
    tp = len(pairs)
    fp = pred_count - tp
    fn = ref_count - tp
    precision = tp / pred_count if pred_count else (1.0 if ref_count == 0 else 0.0)
    recall = tp / ref_count if ref_count else (1.0 if pred_count == 0 else 0.0)
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _event_json(note: Event) -> dict:
    return {
        "pitch": note.pitch,
        "start_s": round(note.start, 5),
        "end_s": round(note.end, 5),
    }


def _mean_abs(values: list[float]) -> float | None:
    return round(sum(abs(value) for value in values) * 1000 / len(values), 3) if values else None


def _mean_signed(values: list[float]) -> float | None:
    return round(sum(values) * 1000 / len(values), 3) if values else None


def evaluate(
    reference: pretty_midi.PrettyMIDI,
    predicted: pretty_midi.PrettyMIDI,
    *,
    onset_tolerance_ms: float = 50.0,
) -> dict:
    if not math.isfinite(onset_tolerance_ms) or onset_tolerance_ms <= 0:
        raise ValueError("onset_tolerance_ms must be positive and finite")

    truth = notes(reference)
    guesses = notes(predicted)
    tol = onset_tolerance_ms / 1000.0

    pairs = matching(truth, guesses, tol, require_offset=False)
    strict_pairs = matching(truth, guesses, tol, require_offset=True)
    relaxed_pairs = matching(truth, guesses, 0.1, require_offset=False)
    found_truth = {r for r, _ in pairs}
    found_pred = {p for _, p in pairs}
    missed = [i for i in range(len(truth)) if i not in found_truth]
    extras = [i for i in range(len(guesses)) if i not in found_pred]
    onset_errors = [guesses[p].start - truth[r].start for r, p in pairs]
    offset_errors = [guesses[p].end - truth[r].end for r, p in pairs]

    # Diagnostics are hints, not new matches that alter precision/recall.
    octave_candidates = sum(
        any(
            abs(truth[r].pitch - guesses[p].pitch) == 12
            and abs(truth[r].start - guesses[p].start) <= tol
            for r in missed
        )
        for p in extras
    )
    duplicate_candidates = sum(
        any(
            guesses[p].pitch == truth[r].pitch
            and abs(guesses[p].start - truth[r].start) <= tol
            for r in found_truth
        )
        for p in extras
    )
    return {
        "reference_notes": len(truth),
        "predicted_notes": len(guesses),
        "note_onset": score(len(truth), len(guesses), pairs),
        "strict_note_onset_offset": score(len(truth), len(guesses), strict_pairs),
        "diagnostic_onset_100ms": score(len(truth), len(guesses), relaxed_pairs),
        "timing_of_onset_matched_notes": {
            "onset_mae_ms": _mean_abs(onset_errors),
            "onset_bias_ms": _mean_signed(onset_errors),
            "offset_mae_ms": _mean_abs(offset_errors),
            "offset_bias_ms": _mean_signed(offset_errors),
            "matched_note_count": len(pairs),
        },
        "diagnostics": {
            "unmatched_predicted_notes": [_event_json(guesses[i]) for i in extras],
            "unmatched_reference_notes": [_event_json(truth[i]) for i in missed],
            "octave_error_candidates": octave_candidates,
            "duplicate_onset_candidates": duplicate_candidates,
        },
        "settings": {
            "onset_tolerance_ms": onset_tolerance_ms,
            "strict_offset_tolerance": "max(50ms, 20pct_reference_note_duration)",
            "scoring": "exact_midi_pitch_max_cardinality_one_to_one",
            "quantized": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score one pitched MIDI stem against a reference MIDI.")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--predicted", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="JSON report path")
    parser.add_argument("--onset-tolerance-ms", type=float, default=50.0)
    args = parser.parse_args(argv)
    try:
        if not args.reference.is_file() or not args.predicted.is_file():
            raise ValueError("Both reference and predicted MIDI files must exist.")
        metrics = evaluate(
            pretty_midi.PrettyMIDI(str(args.reference)),
            pretty_midi.PrettyMIDI(str(args.predicted)),
            onset_tolerance_ms=args.onset_tolerance_ms,
        )
        metrics["reference_file"] = str(args.reference)
        metrics["predicted_file"] = str(args.predicted)
        output = json.dumps(metrics, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        print(output, end="")
        return 0
    except (ValueError, OSError, EOFError) as exc:
        parser.exit(1, f"MIDIVOLT scoring error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
