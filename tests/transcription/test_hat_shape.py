"""Hat spectral shape is opt-in; unit tests use hand-built spectra/WAV only."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from midivolt.drums import HatDetectionConfig, transcribe_drum_wav
from midivolt.hat_shape import HatShapeGate, FEATURE_VERSION, hat_shape_features


def fake_stft(kind: str):
    freq = np.arange(0, 11025, 125, dtype=float)
    mag = np.zeros((len(freq), 70), dtype=float)
    high = (freq >= 5200) & (freq < 10500)
    mag[high, :] = 0.02
    start = 12
    if kind == "burst":
        mag[high, start:start + 3] = 2.0
        mag[high, start + 8:start + 16] = 0.1
    elif kind == "tonal":
        mag[high, start:start + 3] = 0.02
        first_high = np.flatnonzero(high)[0]
        mag[first_high, start:start + 3] = 15.0
    elif kind == "wash":
        mag[high, :] = 1.0
        mag[high, start:start + 3] = 1.2
    elif kind == "silent":
        mag[:, :] = 0
    else:
        raise AssertionError("unknown fixture")
    return mag, freq, start


def notes(midi):
    return [(n.pitch, round(n.start, 5), n.velocity)
            for inst in midi.instruments for n in inst.notes]


class ShapeGateTests(unittest.TestCase):
    def test_broadband_short_noise_burst_accepted(self):
        mag, freq, frame = fake_stft("burst")
        result = hat_shape_features(
            mag, freq, frame, hop_seconds=0.01, config=HatShapeGate()
        )
        self.assertTrue(result["accepted"], result)
        self.assertGreater(result["spectral_flatness"], .95)
        self.assertLess(result["tail_to_attack_ratio"], .1)
        self.assertEqual(result["feature_version"], FEATURE_VERSION)

    def test_tonal_high_frequency_transient_rejected(self):
        mag, freq, frame = fake_stft("tonal")
        result = hat_shape_features(
            mag, freq, frame, hop_seconds=.01, config=HatShapeGate()
        )
        self.assertFalse(result["accepted"])
        self.assertLess(result["spectral_flatness"], .22)

    def test_sustained_cymbal_wash_rejected(self):
        mag, freq, frame = fake_stft("wash")
        result = hat_shape_features(
            mag, freq, frame, hop_seconds=.01, config=HatShapeGate()
        )
        self.assertFalse(result["accepted"])
        self.assertGreater(result["tail_to_attack_ratio"], .66)

    def test_silent_high_band_rejected(self):
        mag, freq, frame = fake_stft("silent")
        self.assertEqual(
            hat_shape_features(
                mag, freq, frame, hop_seconds=.01, config=HatShapeGate()
            )["reason"],
            "no_high_frequency_attack",
        )

    def test_short_tail_insufficient_never_passes(self):
        mag, freq, _ = fake_stft("burst")
        result = hat_shape_features(
            mag[:, :18], freq, 12,
            hop_seconds=.01, config=HatShapeGate()
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "insufficient_decay_window")

    def test_no_high_frequency_bins_never_passes(self):
        mag, freq, idx = fake_stft("burst")
        result = hat_shape_features(
            mag[:10], freq[:10], idx,
            hop_seconds=.01, config=HatShapeGate(),
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "insufficient_high_frequency_bins")

    def test_invalid_spectral_input_fails_closed(self):
        mag, freq, idx = fake_stft("burst")
        with self.assertRaisesRegex(ValueError, "magnitude"):
            hat_shape_features(mag[0], freq, idx, hop_seconds=.01, config=HatShapeGate())
        broken = mag.copy()
        broken[np.flatnonzero(freq >= 5200)[0], idx] = float("nan")
        with self.assertRaisesRegex(ValueError, "Nonfinite"):
            hat_shape_features(broken, freq, idx, hop_seconds=.01, config=HatShapeGate())

    def test_invalid_onset_and_hop_fails_closed(self):
        mag, freq, idx = fake_stft("burst")
        with self.assertRaisesRegex(ValueError, "frame_index"):
            hat_shape_features(mag, freq, -1, hop_seconds=.01, config=HatShapeGate())
        with self.assertRaisesRegex(ValueError, "hop_seconds"):
            hat_shape_features(mag, freq, idx, hop_seconds=0.0, config=HatShapeGate())

    def test_invalid_candidate_config_fails_closed(self):
        for kw in (
            {"min_flatness": .99},
            {"min_attack_contrast": float("nan")},
            {"max_tail_ratio": 0.0},
        ):
            with self.assertRaises(ValueError):
                HatShapeGate(**kw)

    def test_dsp_default_and_explicit_disabled_shape_identical(self):
        with tempfile.TemporaryDirectory() as root:
            wav = Path(root) / "short_noise.wav"
            rng = np.random.default_rng(42)
            sr = 22050
            sound = np.zeros(sr * 2, dtype=np.float32)
            for when in (.3, .7, 1.1):
                ix = int(when * sr)
                noise = rng.standard_normal(1500)
                env = np.exp(-np.arange(1500) / 180)
                sound[ix:ix + 1500] += .25 * (noise * env)
            wavfile.write(str(wav), sr, np.clip(sound * 18000, -32000, 32000).astype(np.int16))
            baseline, _ = transcribe_drum_wav(wav)
            disabled, details = transcribe_drum_wav(wav, hat_shape_gate=None)
            self.assertEqual(notes(baseline), notes(disabled))
            self.assertFalse(details["shape_gate"]["enabled"])

    def test_shape_only_changes_hat_not_kick_or_snare(self):
        with tempfile.TemporaryDirectory() as root:
            wav = Path(root) / "short_noise.wav"
            rng = np.random.default_rng(21)
            sr = 22050
            sound = np.zeros(sr * 2, dtype=np.float32)
            for when in (.25, .55, .85, 1.30):
                ix = int(when * sr)
                noise = rng.standard_normal(1600)
                env = np.exp(-np.arange(1600) / 220)
                sound[ix:ix + 1600] += .28 * (noise * env)
            wavfile.write(str(wav), sr, np.clip(sound * 17000, -32000, 32000).astype(np.int16))
            baseline, _ = transcribe_drum_wav(wav, hat_config=HatDetectionConfig(peak_fraction_scale=.7))
            gated, info = transcribe_drum_wav(
                wav, hat_config=HatDetectionConfig(peak_fraction_scale=.7),
                hat_shape_gate=HatShapeGate(),
            )
            self.assertEqual(
                [n for n in notes(baseline) if n[0] in (36, 38)],
                [n for n in notes(gated) if n[0] in (36, 38)],
            )
            self.assertTrue(info["shape_gate"]["enabled"])
            self.assertEqual(info["shape_gate"]["feature_version"], FEATURE_VERSION)
            self.assertLessEqual(sum(p == 42 for p, _, _ in notes(gated)),
                                 sum(p == 42 for p, _, _ in notes(baseline)))


if __name__ == "__main__":
    unittest.main()
