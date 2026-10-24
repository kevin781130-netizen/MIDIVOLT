"""Fast, weight-free drum-event transcription baseline for *isolated drum* WAVs.

DSP detection + conservative spectral heuristics; NOT a neural drum classifier.
No model downloads or sample templates. Emits only three GM drum voices:
36 kick, 38 snare, 42 closed hi-hat. No invented cymbal/tom classes.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pretty_midi
from scipy import signal
from scipy.io import wavfile

TARGET_SR = 22050
FFT_SIZE = 1024
HOP = 256
GM_PITCH = {"kick": 36, "snare": 38, "hat": 42}
FLUX_BANDS = {
    "kick": (35, 180),
    "snare": (300, 4000),
    "hat": (5200, 10500),
}
POWER_BANDS = {
    "low": (35, 180),
    "mid": (180, 5200),
    "high": (5200, 10500),
}


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    """Read finite mono/stereo WAV; resample only, preserve the original zero."""
    sr, raw = wavfile.read(str(path))
    if sr <= 0 or raw.size == 0:
        raise ValueError(f"Drum WAV is empty or invalid: {path}")
    if raw.ndim not in (1, 2):
        raise ValueError("Only mono and multichannel WAV are supported.")
    if raw.dtype.kind == "u" and raw.dtype.itemsize == 1:
        samples = (raw.astype(np.float32) - 128.0) / 128.0
    elif raw.dtype.kind in "iu":
        # scipy stores signed 24-bit PCM in int32, left-justified.
        samples = raw.astype(np.float32) / float(2 ** (raw.dtype.itemsize * 8 - 1))
    elif raw.dtype.kind == "f":
        samples = raw.astype(np.float32)
    else:
        raise ValueError(f"Unsupported WAV sample format: {raw.dtype}")
    if samples.ndim == 2:
        samples = np.mean(samples, axis=1, dtype=np.float32)
    if not np.isfinite(samples).all():
        raise ValueError("Drum WAV contains nonfinite audio.")
    if sr != TARGET_SR:
        gcd = math.gcd(sr, TARGET_SR)
        samples = signal.resample_poly(samples, TARGET_SR // gcd, sr // gcd).astype(np.float32)
    return np.clip(samples, -1.0, 1.0), TARGET_SR


def _power_shares(magnitude: np.ndarray, freq: np.ndarray, i: int) -> tuple[float, float, float]:
    # Use frames around the transient, not the entire decaying tail.
    sample = np.mean(magnitude[:, i:min(i + 4, magnitude.shape[1])] ** 2, axis=1)
    parts = []
    for low, high in POWER_BANDS.values():
        parts.append(float(np.sum(sample[(freq >= low) & (freq < high)])))
    total = sum(parts)
    return tuple(v / total if total > 1e-14 else 0.0 for v in parts)


def _accept(kind: str, shares: tuple[float, float, float]) -> bool:
    low, mid, high = shares
    if kind == "kick":
        return low >= 0.38 and low >= mid
    if kind == "snare":
        return mid >= 0.43 and mid >= 1.8 * high
    if kind == "hat":
        # Hat can coexist with a loud kick; check high-to-mid ratio too.
        return high >= 0.12 and high >= 2.5 * mid
    return False


def transcribe_drum_wav(
    path: Path,
    *,
    tempo: float = 120.0,
    min_peak_fraction: float = 0.09,
) -> tuple[pretty_midi.PrettyMIDI, dict]:
    """Return drum MIDI and diagnostics, with all event times in WAV seconds.

    This is a baseline for clean drum stems, not a validated production model.
    """
    if not (20 <= tempo <= 400):
        raise ValueError("Drum MIDI grid tempo must be 20..400 BPM")
    if not (0.01 <= min_peak_fraction <= 0.8):
        raise ValueError("min_peak_fraction must be 0.01..0.8")
    audio, sr = read_audio(Path(path))
    midi = pretty_midi.PrettyMIDI(initial_tempo=tempo, resolution=960)
    track = pretty_midi.Instrument(program=0, is_drum=True, name=f"drums | {Path(path).stem}")
    midi.instruments.append(track)
    duration = len(audio) / sr
    if np.max(np.abs(audio)) < 0.003:
        return midi, {"engine": "drum_dsp_v1", "counts": dict.fromkeys(GM_PITCH, 0),
                      "detected": 0, "ignored_candidates": 0, "duration_seconds": duration}

    frequencies, times, stft = signal.stft(
        audio, fs=sr, window="hann", nperseg=FFT_SIZE, noverlap=FFT_SIZE - HOP,
        boundary="zeros", padded=True,
    )
    magnitude = np.abs(stft)
    events = []
    ignored = 0

    for kind, (lo, hi) in FLUX_BANDS.items():
        band = magnitude[(frequencies >= lo) & (frequencies < hi)]
        if band.size == 0:
            continue
        flux = np.r_[0.0, np.sum(np.maximum(0.0, np.diff(band, axis=1)), axis=0)]
        nonzero = flux[flux > 0]
        if not len(nonzero):
            continue
        threshold = max(
            float(np.max(flux)) * min_peak_fraction,
            float(np.percentile(nonzero, 60)) * 3.0,
        )
        peaks, _ = signal.find_peaks(
            flux, height=threshold, prominence=threshold * 0.5,
            distance=max(1, round(0.05 * sr / HOP)),
        )
        candidates = []
        for i in peaks:
            onset = float(times[i])
            if onset > duration + HOP / sr:
                continue
            # Classify on the transient's spectral profile, not the onset's
            # nominal frequency-band label alone.
            shares = _power_shares(magnitude, frequencies, int(i))
            if not _accept(kind, shares):
                ignored += 1
                continue
            # Exclude tiny events amid strong background/silence.
            start = max(0, round(onset * sr))
            stop = min(len(audio), start + round(0.07 * sr))
            rms = float(np.sqrt(np.mean(audio[start:stop] ** 2))) if stop > start else 0.0
            if rms < 0.001:
                ignored += 1
                continue
            candidates.append((max(0.0, onset), rms))

        # The same event may produce several adjacent spectral peaks.
        for onset, rms in sorted(candidates):
            if events and any(
                e[0] == kind and abs(e[1] - onset) < 0.045
                for e in events[-8:]
            ):
                ignored += 1
            else:
                events.append((kind, onset, rms))

    events.sort(key=lambda item: (item[1], GM_PITCH[item[0]]))
    rms_reference = float(np.percentile([e[2] for e in events], 90)) if events else 0.0
    counts = {kind: 0 for kind in GM_PITCH}
    for kind, onset, rms in events:
        counts[kind] += 1
        velocity = int(np.clip(round(105 * math.sqrt(rms / max(rms_reference, 1e-9))), 20, 127))
        track.notes.append(pretty_midi.Note(
            velocity=velocity,
            pitch=GM_PITCH[kind],
            start=onset,
            end=onset + 0.10,
        ))
    return midi, {
        "engine": "drum_dsp_v1",
        "counts": counts,
        "detected": len(events),
        "ignored_candidates": ignored,
        "duration_seconds": round(duration, 6),
        "caveat": "Kick/snare/closed-hat baseline only; onset/spectral heuristic may miss "
                  "ghost notes, classify cymbals/snare incorrectly, and cannot identify "
                  "tom/open-hat/ride. No beats quantized or timeline shifted.",
    }
