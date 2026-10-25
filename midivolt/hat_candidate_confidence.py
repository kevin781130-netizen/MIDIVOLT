"""Research-only confidence guard for NEW GM42 subband onset candidates.

Never modify pre-existing DSP notes. This is a frozen physical-acoustics
hypothesis, not a model trained or calibrated on the failed Cut-25 cohort.
Applied after candidate generation, *only* to newly proposed GM42 events.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

VERSION = "new-gm42-candidate-confidence-r1"


@dataclass(frozen=True)
class HatCandidateConfidence:
    min_high_to_mid: float = 2.0
    min_noise_flatness: float = 0.32
    min_two_band_balance: float = 0.22
    min_attack_to_before: float = 2.0
    max_tail_to_attack: float = 0.62

    def __post_init__(self):
        bounds = {
            "min_high_to_mid": (1.0, 8.0),
            "min_noise_flatness": (0.1, 0.9),
            "min_two_band_balance": (0.05, 1.0),
            "min_attack_to_before": (1.0, 20.0),
            "max_tail_to_attack": (0.05, 1.0),
        }
        for key, (low, high) in bounds.items():
            value = getattr(self, key)
            if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{key} requires finite value in [{low},{high}]")


def evaluate_candidate_confidence(
    magnitude: np.ndarray,
    frequencies: np.ndarray,
    frame_index: int,
    *,
    hop_seconds: float,
    config: HatCandidateConfidence,
) -> dict:
    """Classify one already-proposed candidate by attack shape.

    Require dual-band broadband noise at the attack, meaningful increase
    against the preceding high-frequency floor, high:mid dominance, and
    relatively short HF decay. Unlike an extra onset detector this guard
    can only reject candidates, never create any new ones.
    """
    if not isinstance(config, HatCandidateConfidence):
        raise ValueError("HatCandidateConfidence required")
    mag, hz = np.asarray(magnitude), np.asarray(frequencies)
    if (mag.ndim != 2 or hz.ndim != 1 or mag.shape[0] != hz.size
            or isinstance(frame_index, bool) or not isinstance(frame_index, (int, np.integer))
            or not 0 <= int(frame_index) < mag.shape[1]
            or not math.isfinite(hop_seconds) or hop_seconds <= 0 or hop_seconds > 0.1):
        raise ValueError("Bad candidate STFT geometry or time")
    frame = int(frame_index)
    pre = max(1, round(0.05 / hop_seconds))
    early = max(1, round(0.025 / hop_seconds))
    tail_first = max(1, round(0.08 / hop_seconds))
    tail_last = max(tail_first + 1, round(0.15 / hop_seconds))
    if frame < pre or frame + tail_last > mag.shape[1]:
        return {"accepted": False, "reason": "insufficient_50ms_history_or_150ms_tail", "feature_version": VERSION}
    lo = (hz >= 5200) & (hz < 7500)
    hi = (hz >= 7500) & (hz < 10500)
    mid = (hz >= 180) & (hz < 5200)
    if min(np.count_nonzero(lo), np.count_nonzero(hi)) < 3 or not np.any(mid):
        return {"accepted": False, "reason": "missing_stft_frequency_bins", "feature_version": VERSION}
    local = mag[:, frame-pre:frame+tail_last]
    if not np.isfinite(local).all() or np.any(local < 0):
        raise ValueError("Bad local STFT magnitude")
    # Local extraction only; never scan the entire song on every candidate.
    power = np.square(local.astype(np.float64, copy=False))
    at = pre
    before = power[:, :at]
    attack = power[:, at:at+early]
    tail = power[:, at+tail_first:at+tail_last]
    eps = 1e-15
    high_mask = lo | hi
    attack_spectrum = attack.mean(axis=1)
    attack_hi = float(attack_spectrum[high_mask].sum())
    if attack_hi <= eps:
        return {"accepted": False, "reason": "no_high_frequency_attack", "feature_version": VERSION}
    mid_energy = float(attack_spectrum[mid].sum())
    lo_energy = float(attack_spectrum[lo].sum())
    hi_energy = float(attack_spectrum[hi].sum())
    balance = min(lo_energy, hi_energy) / max(lo_energy, hi_energy, eps)
    bins = attack_spectrum[high_mask]
    noise_floor = max(float(np.mean(bins)) * 1e-7, eps)
    flatness = float(np.exp(np.mean(np.log(bins + noise_floor))) / np.mean(bins + noise_floor))
    prior_energy = float(before[high_mask].sum(axis=0).mean())
    tail_energy = float(tail[high_mask].sum(axis=0).mean())
    attack_over_before = attack_hi / max(prior_energy, attack_hi * 0.01, eps)
    tail_over_attack = tail_energy / max(attack_hi, eps)
    observed = {
        "high_to_mid": round(attack_hi / max(mid_energy, eps), 6),
        "noise_flatness": round(flatness, 6),
        "two_band_balance": round(balance, 6),
        "attack_to_prior": round(attack_over_before, 6),
        "tail_to_attack": round(tail_over_attack, 6),
    }
    tests = {
        "midband_shadow": observed["high_to_mid"] >= config.min_high_to_mid,
        "tonal_or_narrowband": observed["noise_flatness"] >= config.min_noise_flatness,
        "uneven_high_subbands": observed["two_band_balance"] >= config.min_two_band_balance,
        "continuous_cymbal_wash": observed["attack_to_prior"] >= config.min_attack_to_before,
        "sustained_cymbal_tail": observed["tail_to_attack"] <= config.max_tail_to_attack,
    }
    blocked = [name for name, ok in tests.items() if not ok]
    return {
        "accepted": not blocked, "reason": "passed" if not blocked else "candidate_confidence_rejected",
        "blocked_by": blocked, "features": observed, "feature_version": VERSION,
    }
