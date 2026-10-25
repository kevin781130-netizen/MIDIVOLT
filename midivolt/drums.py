"""Fast, weight-free drum-event transcription baseline for *isolated drum* WAVs.

DSP detection + conservative spectral heuristics; NOT a neural drum classifier.
No model downloads or sample templates. Emits only three GM drum voices:
36 kick, 38 snare, 42 closed hi-hat. No invented cymbal/tom classes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pretty_midi
from scipy import signal
from scipy.io import wavfile

from midivolt.hat_shape import HatShapeGate, hat_shape_features, FEATURE_VERSION
from midivolt.hat_subband import HatSubbandConfig, propose_new_hat_onsets, VERSION as SUBBAND_VERSION
from midivolt.hat_candidate_confidence import HatCandidateConfidence, VERSION as CONFIDENCE_VERSION

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


@dataclass(frozen=True)
class HatDetectionConfig:
    """Independent high-hat sensitivity knobs, not a new model.

    The default values exactly mirror DSP v1. Alternative parameter values
    are for separately authorized validation-split experiments ONLY.
    """
    peak_fraction_scale: float = 1.0
    flux_noise_multiplier: float = 3.0
    min_high_power_share: float = 0.12
    min_high_to_mid_ratio: float = 2.5
    min_rms: float = 0.001

    def __post_init__(self):
        fields = (
            ("peak_fraction_scale", self.peak_fraction_scale, 0.25, 2.0),
            ("flux_noise_multiplier", self.flux_noise_multiplier, 1.0, 6.0),
            ("min_high_power_share", self.min_high_power_share, 0.03, 0.4),
            ("min_high_to_mid_ratio", self.min_high_to_mid_ratio, 0.5, 6.0),
            ("min_rms", self.min_rms, 0.0002, 0.01),
        )
        for name, value, low, high in fields:
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"HatDetectionConfig.{name} must be finite in [{low}, {high}]")



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


def _accept(
    kind: str, shares: tuple[float, float, float],
    hat: HatDetectionConfig | None = None,
) -> bool:
    low, mid, high = shares
    if kind == "kick":
        return low >= 0.38 and low >= mid
    if kind == "snare":
        return mid >= 0.43 and mid >= 1.8 * high
    if kind == "hat":
        # Defaults reproduce the original DSP v1 exactly. Independently vary
        # only the high-frequency criteria on a held-out validation split.
        config = hat or HatDetectionConfig()
        return (
            high >= config.min_high_power_share
            and high >= config.min_high_to_mid_ratio * mid
        )
    return False


def transcribe_drum_wav(
    path: Path,
    *,
    tempo: float = 120.0,
    min_peak_fraction: float = 0.09,
    hat_config: HatDetectionConfig | None = None,
    hat_shape_gate: HatShapeGate | None = None,
    hat_subband_config: HatSubbandConfig | None = None,
    hat_candidate_confidence: HatCandidateConfidence | None = None,
) -> tuple[pretty_midi.PrettyMIDI, dict]:
    """Return drum MIDI and diagnostics, with all event times in WAV seconds.

    This is a baseline for clean drum stems, not a validated production model.
    """
    if not (20 <= tempo <= 400):
        raise ValueError("Drum MIDI grid tempo must be 20..400 BPM")
    if not math.isfinite(min_peak_fraction) or not (0.01 <= min_peak_fraction <= 0.8):
        raise ValueError("min_peak_fraction must be finite and 0.01..0.8")
    if hat_config is not None and not isinstance(hat_config, HatDetectionConfig):
        raise ValueError("hat_config must be a HatDetectionConfig")
    if hat_shape_gate is not None and not isinstance(hat_shape_gate, HatShapeGate):
        raise ValueError("hat_shape_gate must be a HatShapeGate")
    if hat_subband_config is not None and not isinstance(hat_subband_config, HatSubbandConfig):
        raise ValueError("hat_subband_config must be a HatSubbandConfig")
    if hat_candidate_confidence is not None and not isinstance(hat_candidate_confidence, HatCandidateConfidence):
        raise ValueError("hat_candidate_confidence must be a HatCandidateConfidence")
    if hat_candidate_confidence is not None and hat_subband_config is None:
        raise ValueError("hat_candidate_confidence requires opt-in hat_subband_config")
    hat = hat_config or HatDetectionConfig()
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
    shape_rejected = 0
    shape_accepted = 0

    for kind, (lo, hi) in FLUX_BANDS.items():
        band = magnitude[(frequencies >= lo) & (frequencies < hi)]
        if band.size == 0:
            continue
        flux = np.r_[0.0, np.sum(np.maximum(0.0, np.diff(band, axis=1)), axis=0)]
        nonzero = flux[flux > 0]
        if not len(nonzero):
            continue
        threshold = max(
            float(np.max(flux)) * min_peak_fraction * (
                hat.peak_fraction_scale if kind == "hat" else 1.0
            ),
            float(np.percentile(nonzero, 60)) * (
                hat.flux_noise_multiplier if kind == "hat" else 3.0
            ),
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
            if not _accept(kind, shares, hat):
                ignored += 1
                continue
            # Optional shape gate runs ONLY on Hi-hat candidates. Existing
            # Kick/Snare decisions are byte-for-byte equivalent to DSP v1.
            if kind == "hat" and hat_shape_gate is not None:
                shape = hat_shape_features(
                    magnitude, frequencies, int(i),
                    hop_seconds=HOP / sr, config=hat_shape_gate,
                )
                if not shape["accepted"]:
                    shape_rejected += 1
                    ignored += 1
                    continue
                shape_accepted += 1
            # Exclude tiny events amid strong background/silence.
            start = max(0, round(onset * sr))
            stop = min(len(audio), start + round(0.07 * sr))
            rms = float(np.sqrt(np.mean(audio[start:stop] ** 2))) if stop > start else 0.0
            if rms < (hat.min_rms if kind == "hat" else 0.001):
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

    subband_diagnostic = {"enabled": False, "version": SUBBAND_VERSION, "new_candidates": 0}
    if hat_subband_config is not None:
        # Entirely optional NEW high-band onset path. Preserve the baseline
        # (kick, snare and hat) events; only append independent GM42 notes.
        extra, subband_diagnostic = propose_new_hat_onsets(
            magnitude, frequencies, times, audio, sr,
            [event[1] for event in events if event[0] == "hat"],
            config=hat_subband_config,
            confidence=hat_candidate_confidence,
        )
        subband_diagnostic["enabled"] = True
        for onset, rms in extra:
            events.append(("hat", onset, rms))

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
        "hat_config": {
            "peak_fraction_scale": hat.peak_fraction_scale,
            "flux_noise_multiplier": hat.flux_noise_multiplier,
            "min_high_power_share": hat.min_high_power_share,
            "min_high_to_mid_ratio": hat.min_high_to_mid_ratio,
            "min_rms": hat.min_rms,
        },
        "counts": counts,
        "subband_candidates": subband_diagnostic,
        "candidate_confidence": {
            "enabled": hat_candidate_confidence is not None,
            "version": CONFIDENCE_VERSION,
        },
        "shape_gate": (
            {"enabled": True, "feature_version": FEATURE_VERSION,
             "criteria": {
                 "min_flatness": hat_shape_gate.min_flatness,
                 "min_attack_contrast": hat_shape_gate.min_attack_contrast,
                 "max_tail_ratio": hat_shape_gate.max_tail_ratio,
             }, "accepted_candidates": shape_accepted,
             "rejected_candidates": shape_rejected}
            if hat_shape_gate else {"enabled": False}
        ),
        "detected": len(events),
        "ignored_candidates": ignored,
        "duration_seconds": round(duration, 6),
        "caveat": "Kick/snare/closed-hat baseline only; onset/spectral heuristic may miss "
                  "ghost notes, classify cymbals/snare incorrectly, and cannot identify "
                  "tom/open-hat/ride. No beats quantized or timeline shifted.",
    }
