"""Pitch-specific drum onset metrics and same-reference MIDI A/B comparison.

No accuracy claim is made about engines until the user supplies real, properly
aligned ground-truth drum MIDI. Uses the same 50 ms tolerance on both outputs.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pretty_midi

from midivolt.evaluate import Event, matching, score


def drum_events(midi: pretty_midi.PrettyMIDI) -> list[Event]:
    if not midi.instruments or any(not track.is_drum for track in midi.instruments):
        raise ValueError("Drum scoring requires GM percussion tracks (is_drum=True).")
    events = []
    for track in midi.instruments:
        for note in track.notes:
            if not (math.isfinite(note.start) and math.isfinite(note.end)):
                raise ValueError("MIDI contains nonfinite event times.")
            if note.start < 0 or note.end <= note.start:
                raise ValueError("MIDI contains invalid drum event times.")
            events.append(Event(pitch=note.pitch, start=note.start, end=note.end))
    return sorted(events, key=lambda e: (e.pitch, e.start, e.end))


def evaluate_drums(
    reference: pretty_midi.PrettyMIDI,
    prediction: pretty_midi.PrettyMIDI,
    *,
    tolerance_ms: float = 50.0,
) -> dict:
    if not math.isfinite(tolerance_ms) or not 1 <= tolerance_ms <= 200:
        raise ValueError("Drum onset tolerance must be finite, 1..200 milliseconds.")
    truth, guessed = drum_events(reference), drum_events(prediction)
    tol = tolerance_ms / 1000
    matched = matching(truth, guessed, tol, require_offset=False)
    errors = [1000 * (guessed[p].start - truth[r].start) for r, p in matched]
    pitches = sorted({note.pitch for note in truth + guessed})
    per_pitch = {}
    for pitch in pitches:
        tr = [note for note in truth if note.pitch == pitch]
        pr = [note for note in guessed if note.pitch == pitch]
        pairs = matching(tr, pr, tol, require_offset=False)
        per_pitch[str(pitch)] = {
            "reference_count": len(tr),
            "predicted_count": len(pr),
            **score(len(tr), len(pr), pairs),
        }
    return {
        "reference_events": len(truth),
        "predicted_events": len(guessed),
        "onset_tolerance_ms": tolerance_ms,
        "micro": score(len(truth), len(guessed), matched),
        "per_gm_pitch": per_pitch,
        "matched_onset_mae_ms": (
            round(sum(abs(error) for error in errors) / len(errors), 4)
            if errors else None
        ),
        "matched_onset_bias_ms": (
            round(sum(errors) / len(errors), 4) if errors else None
        ),
        "notes": "Exact GM MIDI pitches, one-to-one onset matching. "
                 "No octave, family or cymbal-class collapsing.",
    }


def compare(
    reference: pretty_midi.PrettyMIDI,
    dsp: pretty_midi.PrettyMIDI,
    ai: pretty_midi.PrettyMIDI,
    *,
    tolerance_ms: float = 50.0,
) -> dict:
    results = {
        "dsp": evaluate_drums(reference, dsp, tolerance_ms=tolerance_ms),
        "adt_str": evaluate_drums(reference, ai, tolerance_ms=tolerance_ms),
    }
    first, second = results["dsp"]["micro"]["f1"], results["adt_str"]["micro"]["f1"]
    results["comparison"] = {
        "adt_minus_dsp_f1": round(second - first, 6),
        "higher_f1_on_this_clip": (
            "adt_str" if second > first else "dsp" if first > second else "tie"
        ),
        "warning": "This clip cannot establish real-world superiority; report "
                   "multiple songs, per-class metrics, license and runtime.",
    }
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare drum MIDI predictions against same reference.")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--dsp", type=Path, required=True)
    parser.add_argument("--adt-str", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--onset-tolerance-ms", type=float, default=50.0)
    args = parser.parse_args(argv)
    try:
        for path in (args.reference, args.dsp, args.adt_str):
            if not path.is_file():
                raise ValueError("MIDI input does not exist: " + str(path))
        result = compare(
            pretty_midi.PrettyMIDI(str(args.reference)),
            pretty_midi.PrettyMIDI(str(args.dsp)),
            pretty_midi.PrettyMIDI(str(args.adt_str)),
            tolerance_ms=args.onset_tolerance_ms,
        )
        result["files"] = {
            "reference": str(args.reference),
            "dsp": str(args.dsp),
            "adt_str": str(args.adt_str),
        }
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (ValueError, EOFError, OSError) as exc:
        parser.exit(1, f"Drum scoring error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
