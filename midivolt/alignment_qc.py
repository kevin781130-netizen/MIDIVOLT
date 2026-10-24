"""Conservative onset alignment diagnostics for WAV and reference drum MIDI.

This inspects the audio's transient energy near ground-truth MIDI events.
It NEVER shifts, edits, time-warps or quantizes either input. It is a
diagnostic, not a correction algorithm or a proof of audio/MIDI alignment.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pretty_midi
from scipy.ndimage import uniform_filter1d

from midivolt.drums import read_audio
from midivolt.compare_drums import drum_events


def inspect_alignment(
    wav_path: Path,
    truth: pretty_midi.PrettyMIDI,
    *,
    pre_ms: float = 65.0,
    post_ms: float = 85.0,
    minimum_events: int = 5,
    warning_threshold_ms: float = 25.0,
) -> dict:
    if not 1 <= pre_ms <= 200 or not 1 <= post_ms <= 200:
        raise ValueError("Invalid alignment search window")
    if minimum_events < 1:
        raise ValueError("minimum_events must be positive")
    audio, sr = read_audio(Path(wav_path))
    events = drum_events(truth)
    times = sorted({round(note.start, 5) for note in events})
    if not times:
        return {
            "status": "insufficient_events",
            "reference_onsets": 0,
            "matched_audio_transients": 0,
            "warning": "No drum note onsets in the MIDI; not scored.",
        }

    # Low-pass absolute amplitude to estimate attack envelope, then compare
    # with a 4-ms lag for positive rises. This favors short drum transients.
    smooth_size = max(3, round(sr * 0.0025))
    envelope = uniform_filter1d(np.abs(audio), size=smooth_size, mode="constant")
    lag_samples = max(1, round(sr * 0.004))
    novelty = np.maximum(
        0.0,
        envelope - np.pad(envelope[:-lag_samples], (lag_samples, 0)),
    )
    top_strength = float(np.max(novelty)) if len(novelty) else 0.0
    if top_strength <= 1e-6:
        return {
            "status": "insufficient_audio_transients",
            "reference_onsets": len(times),
            "matched_audio_transients": 0,
            "warning": "Silence or no measurable onsets; no alignment correction made.",
        }

    differences_ms = []
    for time_s in times:
        # Avoid duplicate measurements of flams / nearby notes, where the
        # strongest transient may belong to the adjacent reference event.
        if any(0 < abs(time_s - other) < 0.12 for other in times):
            continue
        lo = max(0, int((time_s - pre_ms / 1000) * sr))
        hi = min(len(novelty), math.ceil((time_s + post_ms / 1000) * sr))
        if hi <= lo:
            continue
        strength = novelty[lo:hi]
        best_rel = int(np.argmax(strength))
        if float(strength[best_rel]) < top_strength * 0.08:
            continue
        found_s = (lo + best_rel) / sr
        differences_ms.append((found_s - time_s) * 1000)

    n = len(differences_ms)
    if n < minimum_events:
        return {
            "status": "insufficient_confident_events",
            "reference_onsets": len(times),
            "matched_audio_transients": n,
            "warning": "Not enough isolated/high-strength transients; do not infer offset.",
        }

    median = float(np.median(differences_ms))
    mad = float(np.median(np.abs(np.array(differences_ms) - median)))
    issue = abs(median) > warning_threshold_ms and mad < 18.0
    return {
        "status": "suspected_offset" if issue else ("inconclusive" if mad >= 18.0 else "no_large_offset_detected"),
        "reference_onsets": len(times),
        "matched_audio_transients": n,
        "median_audio_minus_midi_ms": round(median, 3),
        "median_abs_deviation_ms": round(mad, 3),
        "max_allowed_diagnostic_offset_ms": warning_threshold_ms,
        "warning": (
            "Potential uniform audio/MIDI time offset; verify source alignment. "
            "This tool deliberately does not edit or compensate event timestamps."
            if issue else
            "Diagnostic only. Low measured offset does not prove absolute alignment."
        ),
    }
