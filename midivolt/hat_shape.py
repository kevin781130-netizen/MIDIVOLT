"""Pre-registered, weight-free closed Hi-hat shape features (research v1).

Not a trained model and not a generalized instrument recognizer. Features
inspect the high-frequency attack and decay of an existing *candidate*
onset in its original STFT. No ML libraries, data or samples bundled.
The frozen rules must be evaluated on NEW official Validation performances
before use. Legacy DSP inference is unchanged unless explicitly enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


FEATURE_VERSION = "hat-shape-r1-frozen-20261025"


@dataclass(frozen=True)
class HatShapeGate:
    """Engineering hypothesis, NOT tuned on the published Validation/Test F1.

    High-band spectral flatness distinguishes noise-like bursts from pitched
    transients; attack contrast rejects continuous sizzle; short high-band
    decay rejects sustained cymbal wash. All thresholds are hypotheses.
    """

    min_flatness: float = 0.22
    min_attack_contrast: float = 1.6
    max_tail_ratio: float = 0.66

    def __post_init__(self) -> None:
        for name, value, low, high in (
            ("min_flatness", self.min_flatness, 0.05, 0.9),
            ("min_attack_contrast", self.min_attack_contrast, 1.05, 25.0),
            ("max_tail_ratio", self.max_tail_ratio, 0.05, 1.0),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be finite in [{low}, {high}]")


def hat_shape_features(
    magnitude: np.ndarray,
    frequencies: np.ndarray,
    frame_index: int,
    *,
    hop_seconds: float,
    config: HatShapeGate,
) -> dict:
    """Compute features on the 5.2–10.5 kHz STFT power (no global fitting).

    Magnitude is [frequency, frame]. Frames near audio end without a
    diagnostic decay window are marked insufficient, not accepted.
    """
    mag = np.asarray(magnitude)
    freq = np.asarray(frequencies)
    if mag.ndim != 2 or freq.ndim != 1 or mag.shape[0] != len(freq):
        raise ValueError("Expected magnitude [frequency, frame] and frequency bins")
    if isinstance(frame_index, bool) or not isinstance(frame_index, (int, np.integer)):
        raise ValueError("frame_index must be an integer")
    if not (0 <= frame_index < mag.shape[1]):
        raise ValueError("frame_index outside available signal")
    if not math.isfinite(hop_seconds) or hop_seconds <= 0:
        raise ValueError("hop_seconds must be positive and finite")
    if not np.isfinite(mag).all() or np.any(mag < 0):
        raise ValueError("Nonfinite or negative spectral magnitudes")
    if not isinstance(config, HatShapeGate):
        raise ValueError("config must be a HatShapeGate")

    high_band = (freq >= 5200.0) & (freq < 10500.0)
    if np.count_nonzero(high_band) < 4:
        return {"accepted": False, "reason": "insufficient_high_frequency_bins"}

    frame = int(frame_index)
    # 2-frame attack; 30–80ms history; 80–150ms sustained tail.
    attack_n = max(1, round(0.025 / hop_seconds))
    pre_n = max(1, round(0.05 / hop_seconds))
    tail_from = max(1, round(0.080 / hop_seconds))
    tail_to = max(tail_from + 1, round(0.150 / hop_seconds))
    if frame + tail_to > mag.shape[1]:
        return {"accepted": False, "reason": "insufficient_decay_window"}
    power = np.square(mag[high_band, :].astype(np.float64, copy=False))
    early = power[:, frame:frame + attack_n]
    before = power[:, max(0, frame - pre_n):frame]
    tail = power[:, frame + tail_from:frame + tail_to]
    eps = 1e-14
    attack_energy = float(np.mean(np.sum(early, axis=0)))
    if attack_energy <= eps:
        return {"accepted": False, "reason": "no_high_frequency_attack"}

    spectral_profile = np.mean(early, axis=1)
    floor = max(float(np.mean(spectral_profile)) * 1e-7, eps)
    flatness = float(
        np.exp(np.mean(np.log(spectral_profile + floor)))
        / np.mean(spectral_profile + floor)
    )
    baseline_energy = float(np.mean(np.sum(before, axis=0))) if before.size else 0.0
    attack_contrast = attack_energy / max(
        baseline_energy,
        # Avoid treating tiny numerical noise as an infinite attack.
        attack_energy * 0.01,
        eps,
    )
    tail_energy = float(np.mean(np.sum(tail, axis=0)))
    tail_ratio = tail_energy / max(attack_energy, eps)
    accepted = (
        flatness >= config.min_flatness
        and attack_contrast >= config.min_attack_contrast
        and tail_ratio <= config.max_tail_ratio
    )
    return {
        "accepted": bool(accepted),
        "reason": "passed" if accepted else "spectral_shape_rejected",
        "spectral_flatness": round(flatness, 6),
        "attack_contrast": round(attack_contrast, 6),
        "tail_to_attack_ratio": round(tail_ratio, 6),
        "feature_version": FEATURE_VERSION,
    }
