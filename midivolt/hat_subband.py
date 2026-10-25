"""Opt-in, weight-free NEW Closed Hi-hat candidate generator (research r1).

Unlike the earlier spectral-shape post-filter, this proposes *new* GM42
onsets from two independently detected high-frequency subbands. Both
bands must exhibit a locally novel attack near the same time. A shared
refractory stage suppresses duplicates of baseline GM42 predictions.

The source/detector parameters are frozen engineering hypotheses, NOT
fitted to any previously scored E-GMD Test or Validation examples.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy import ndimage, signal

from midivolt.hat_candidate_confidence import (
    HatCandidateConfidence, evaluate_candidate_confidence, VERSION as CONFIDENCE_VERSION,
)
from midivolt.hat_candidate_ranker import HatRankerModel, score_onset, SCHEMA as RANKER_SCHEMA


VERSION = "hat-dual-subband-candidates-r1-20261025"
SUBBANDS = ((5200.0, 7500.0), (7500.0, 10500.0))


@dataclass(frozen=True)
class HatSubbandConfig:
    window_seconds: float = 0.5
    mad_multiplier: float = 3.0
    global_floor_fraction: float = 0.012
    min_attack_ratio: float = 1.7
    max_subband_gap_seconds: float = 0.025
    minimum_spacing_seconds: float = 0.055
    dedupe_seconds: float = 0.045
    min_high_power_share: float = 0.16
    min_high_to_mid_ratio: float = 1.0
    min_rms: float = 0.001

    def __post_init__(self):
        limits = {
            "window_seconds": (0.1, 2.0),
            "mad_multiplier": (1.0, 10.0),
            "global_floor_fraction": (0.001, 0.12),
            "min_attack_ratio": (1.05, 10.0),
            "max_subband_gap_seconds": (0.0, 0.045),
            "minimum_spacing_seconds": (0.045, 0.15),
            "dedupe_seconds": (0.025, 0.065),
            "min_high_power_share": (0.05, 0.50),
            "min_high_to_mid_ratio": (0.4, 6.0),
            "min_rms": (0.0002, 0.015),
        }
        for field, (minimum, maximum) in limits.items():
            value = getattr(self, field)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{field} must be finite")
            if not minimum <= value <= maximum:
                raise ValueError(f"{field} outside [{minimum}, {maximum}]")


def _subband_peaks(
    magnitude: np.ndarray, frequencies: np.ndarray,
    band: tuple[float, float], hop_seconds: float, cfg: HatSubbandConfig,
) -> tuple[np.ndarray, np.ndarray]:
    bins = (frequencies >= band[0]) & (frequencies < band[1])
    if bins.sum() < 4:
        return np.array([], dtype=int), np.empty(0)
    selected = magnitude[bins]
    # Local positive spectral flux: new high-frequency onset energy only.
    flux = np.r_[0.0, np.maximum(np.diff(selected, axis=1), 0).sum(axis=0)]
    positive = flux[flux > 0]
    if not len(positive):
        return np.array([], dtype=int), flux
    window = max(3, int(round(cfg.window_seconds / hop_seconds)) | 1)
    background = ndimage.median_filter(flux, size=window, mode="nearest")
    deviation = ndimage.median_filter(np.abs(flux - background), size=window, mode="nearest")
    floor = max(float(positive.max()) * cfg.global_floor_fraction,
                # Use a LOW global floor: the earlier 25th percentile
                # was biased upward by a loud attack in sparse passages.
                float(np.percentile(positive, 10)) * 0.30)
    threshold = np.maximum(background + cfg.mad_multiplier * 1.4826 * deviation, floor)
    # Measure local attack contrast against background, NOT the threshold
    # floor. The floor may be dominated by an earlier loud hat, while the
    # current weaker hi-hat is still a distinct local transient.
    contrast_floor = max(float(np.percentile(positive, 10)) * 0.05, 1e-12)
    attacks = flux / np.maximum(background, contrast_floor)
    peaks, _ = signal.find_peaks(
        flux, height=threshold,
        distance=max(1, int(round(cfg.minimum_spacing_seconds / hop_seconds))),
    )
    peaks = peaks[attacks[peaks] >= cfg.min_attack_ratio]
    return peaks, flux


def propose_new_hat_onsets(
    magnitude: np.ndarray,
    frequencies: np.ndarray,
    times: np.ndarray,
    audio: np.ndarray,
    sample_rate: int,
    existing_hat_onsets: list[float] | tuple[float, ...],
    *,
    config: HatSubbandConfig,
    confidence: HatCandidateConfidence | None = None,
    ranker: HatRankerModel | None = None,
) -> tuple[list[tuple[float, float]], dict]:
    """Return [(seconds, rms)] of ONLY genuinely new optional GM42 events.

    Does not change/shift existing MIDI note onsets. Uses a one-to-one
    two-subband consensus, spectral high-vs-mid contrast, RMS threshold,
    and 45ms deduplication against original Hi-hats. The caller should
    add these events AFTER ordinary kick/snare/hat detection.
    """
    spec = np.asarray(magnitude)
    hz = np.asarray(frequencies)
    time = np.asarray(times)
    pcm = np.asarray(audio)
    if not isinstance(config, HatSubbandConfig):
        raise ValueError("HatSubbandConfig required")
    if confidence is not None and not isinstance(confidence, HatCandidateConfidence):
        raise ValueError("confidence must be HatCandidateConfidence")
    if ranker is not None and not isinstance(ranker, HatRankerModel):
        raise ValueError("ranker must be a verified TRAIN-only HatRankerModel")
    if confidence is not None and ranker is not None:
        raise ValueError("Cannot apply competing fixed confidence gate and learned ranker")
    if (spec.ndim != 2 or hz.ndim != 1 or time.ndim != 1
            or spec.shape != (len(hz), len(time))):
        raise ValueError("Expected STFT [frequency, frame] and aligned time axis")
    if pcm.ndim != 1 or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError("Expected 1-D PCM and positive sample rate")
    if (not np.isfinite(spec).all() or np.any(spec < 0)
            or not np.isfinite(pcm).all() or not np.isfinite(hz).all()
            or not np.isfinite(time).all()):
        raise ValueError("STFT/PCM/frequencies/time must be finite nonnegative magnitudes")
    if not np.all(np.diff(time) > 0):
        raise ValueError("STFT times must be strictly increasing")
    for old in existing_hat_onsets:
        if not isinstance(old, (int, float)) or not math.isfinite(old) or old < 0:
            raise ValueError("Existing hat time must be nonnegative and finite")
    if len(time) < 4:
        return [], {"version": VERSION, "new_candidates": 0, "insufficient_audio_frames": True}
    hop_seconds = float(np.median(np.diff(time)))
    if not (0 < hop_seconds <= 0.1):
        raise ValueError("Unexpected STFT hop duration")

    (a, fa), (b, fb) = [
        _subband_peaks(spec, hz, span, hop_seconds, config) for span in SUBBANDS
    ]
    accepted = []
    used_b: set[int] = set()
    rejects = {"unpaired_subband": 0, "existing_hat": 0,
               "spectral_nonhat": 0, "quiet_event": 0, "new_hat_spacing": 0,
               "candidate_confidence": 0, "candidate_ranker": 0}
    confidence_reasons: dict[str, int] = {}
    ranker_scores: list[float] = []
    max_gap = config.max_subband_gap_seconds + 1e-10
    duration = len(pcm) / sample_rate
    high = (hz >= SUBBANDS[0][0]) & (hz < SUBBANDS[-1][1])
    mid = (hz >= 180) & (hz < 5200)
    low = (hz >= 35) & (hz < 180)
    for idx in a:
        possible = [int(j) for j in b
                    if int(j) not in used_b and abs(float(time[int(j)] - time[int(idx)])) <= max_gap]
        if not possible:
            rejects["unpaired_subband"] += 1
            continue
        j = min(possible, key=lambda v: (abs(time[v] - time[int(idx)]), v))
        used_b.add(j)
        peak_index = int(round((int(idx) + j) / 2))
        onset = float(time[peak_index])
        if onset < 0 or onset >= duration:
            continue
        if any(abs(onset - float(old)) < config.dedupe_seconds for old in existing_hat_onsets):
            rejects["existing_hat"] += 1
            continue
        if any(abs(onset - old_onset) < config.minimum_spacing_seconds for old_onset, _ in accepted):
            rejects["new_hat_spacing"] += 1
            continue
        # Reject an unrelated high-band transient riding on a much
        # louder snare/kick. Measure local *power*, not flux, only once
        # per candidate to keep this lightweight.
        spectrum = np.square(spec[:, peak_index:min(peak_index + 4, len(time))])
        energy_high = float(spectrum[high].sum())
        energy_mid = float(spectrum[mid].sum())
        energy_low = float(spectrum[low].sum())
        total = energy_high + energy_mid + energy_low
        if (total <= 1e-14 or energy_high / total < config.min_high_power_share
                or energy_high < config.min_high_to_mid_ratio * energy_mid):
            rejects["spectral_nonhat"] += 1
            continue
        start = max(0, int(round(onset * sample_rate)))
        stop = min(len(pcm), start + int(round(.07 * sample_rate)))
        rms = float(np.sqrt(np.mean(pcm[start:stop] ** 2))) if stop > start else 0
        if not math.isfinite(rms) or rms < config.min_rms:
            rejects["quiet_event"] += 1
            continue
        if confidence is not None:
            inspected = evaluate_candidate_confidence(
                spec, hz, peak_index, hop_seconds=hop_seconds, config=confidence,
            )
            if not inspected["accepted"]:
                rejects["candidate_confidence"] += 1
                reasons = inspected.get("blocked_by") or [inspected["reason"]]
                for reason in reasons:
                    confidence_reasons[reason] = confidence_reasons.get(reason, 0) + 1
                continue
        if ranker is not None:
            classified = score_onset(
                spec, hz, peak_index, hop_seconds=hop_seconds, model=ranker,
            )
            if classified["ranker_probability"] is not None:
                ranker_scores.append(classified["ranker_probability"])
            if not classified["accepted"]:
                rejects["candidate_ranker"] += 1
                continue
        accepted.append((onset, rms))
    return accepted, {
        "version": VERSION, "subband_peak_counts": [len(a), len(b)],
        "new_candidates": len(accepted), "rejected": rejects,
        "does_not_modify_original_events": True,
        "candidate_ranker": {
            "enabled": ranker is not None, "schema": RANKER_SCHEMA,
            "rejected": rejects["candidate_ranker"],
            "scored_candidates": len(ranker_scores),
            "frozen_threshold": ranker.decision_threshold if ranker else None,
        },
        "candidate_confidence": {
            "enabled": confidence is not None,
            "version": CONFIDENCE_VERSION,
            "rejected": rejects["candidate_confidence"],
            "reason_counts": confidence_reasons,
        },
    }
