"""Standalone spectral confidence tests. No external data/model download."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from midivolt.hat_candidate_confidence import (
    HatCandidateConfidence, VERSION, evaluate_candidate_confidence,
)
from midivolt.hat_subband import HatSubbandConfig, propose_new_hat_onsets
from midivolt.drums import transcribe_drum_wav


def spectrum(kind: str = "hat"):
    hz = np.arange(0, 11050, 50.0)
    seconds = np.arange(0, 2.50, 0.01)
    mag = np.full((len(hz), len(seconds)), .001, dtype=float)
    a = (hz >= 5200) & (hz < 7500)
    b = (hz >= 7500) & (hz < 10500)
    m = (hz >= 180) & (hz < 5200)
    center = 65
    if kind == "wash":
        mag[a | b, :] = 1.0
        mag[a | b, center:center+3] = 1.25
    elif kind == "tone":
        mag[np.flatnonzero(a)[2], center:center+3] = 14.0
        mag[np.flatnonzero(b)[2], center:center+3] = 14.0
    else:
        mag[a | b, center:center+3] = 1.5
        if kind == "snare":
            mag[m, center:center+3] = 3.0
        if kind == "long_tail":
            mag[a | b, center+8:center+16] = 1.2
    return mag, hz, seconds, center


def classify(kind):
    mag, hz, _, center = spectrum(kind)
    return evaluate_candidate_confidence(
        mag, hz, center, hop_seconds=.01,
        config=HatCandidateConfidence(),
    )


class CandidateConfidenceTests(unittest.TestCase):
    def test_true_short_broadband_hat_passes(self):
        observed = classify("hat")
        self.assertTrue(observed["accepted"], observed)
        self.assertEqual(observed["feature_version"], VERSION)
        self.assertGreater(observed["features"]["noise_flatness"], .95)
        self.assertLess(observed["features"]["tail_to_attack"], .1)

    def test_narrowband_tone_cannot_be_hat(self):
        observed = classify("tone")
        self.assertFalse(observed["accepted"])
        self.assertTrue(
            set(observed["blocked_by"]) & {"tonal_or_narrowband", "uneven_high_subbands"}
        )

    def test_snare_high_frequency_bleed_is_refused(self):
        observed = classify("snare")
        self.assertFalse(observed["accepted"])
        self.assertIn("midband_shadow", observed["blocked_by"])

    def test_sustained_cymbal_wash_is_refused(self):
        observed = classify("wash")
        self.assertFalse(observed["accepted"])
        self.assertTrue(
            set(observed["blocked_by"]) &
            {"continuous_cymbal_wash", "sustained_cymbal_tail"}
        )

    def test_long_ring_raises_tail_veto(self):
        observed = classify("long_tail")
        self.assertFalse(observed["accepted"])
        self.assertIn("sustained_cymbal_tail", observed["blocked_by"])

    def test_signal_near_end_fails_closed(self):
        mag, hz, _, _ = spectrum("hat")
        response = evaluate_candidate_confidence(
            mag, hz, mag.shape[1]-3, hop_seconds=.01,
            config=HatCandidateConfidence(),
        )
        self.assertFalse(response["accepted"])
        self.assertIn("insufficient_", response["reason"])

    def test_wrong_stft_and_nonfinite_local_samples_rejected(self):
        mag, hz, _, center = spectrum()
        with self.assertRaisesRegex(ValueError, "geometry"):
            evaluate_candidate_confidence(
                mag, hz[:-2], center, hop_seconds=.01,
                config=HatCandidateConfidence(),
            )
        mag[(hz >= 5200).nonzero()[0][0], center] = np.nan
        with self.assertRaisesRegex(ValueError, "local STFT"):
            evaluate_candidate_confidence(
                mag, hz, center, hop_seconds=.01,
                config=HatCandidateConfidence(),
            )

    def test_invalid_configuration_fails_closed(self):
        for kwargs in (
            {"min_noise_flatness": .99},
            {"max_tail_to_attack": -1},
            {"min_high_to_mid": float("nan")},
        ):
            with self.assertRaises(ValueError):
                HatCandidateConfidence(**kwargs)

    def test_original_candidate_path_unchanged_when_confidence_disabled(self):
        mag, hz, times, _ = spectrum("hat")
        pcm = np.full(round(len(times) * .01 * 22050), .025, dtype=float)
        old, _ = propose_new_hat_onsets(
            mag, hz, times, pcm, 22050, [],
            config=HatSubbandConfig(),
        )
        explicit, info = propose_new_hat_onsets(
            mag, hz, times, pcm, 22050, [],
            config=HatSubbandConfig(), confidence=None,
        )
        self.assertEqual(old, explicit)
        self.assertFalse(info["candidate_confidence"]["enabled"])

    def test_confidence_filter_cannot_add_more_candidates(self):
        mag, hz, times, _ = spectrum("hat")
        pcm = np.full(round(len(times) * .01 * 22050), .025, dtype=float)
        original, _ = propose_new_hat_onsets(
            mag, hz, times, pcm, 22050, [], config=HatSubbandConfig(),
        )
        classified, info = propose_new_hat_onsets(
            mag, hz, times, pcm, 22050, [],
            config=HatSubbandConfig(), confidence=HatCandidateConfidence(),
        )
        self.assertTrue(set(classified).issubset(set(original)))
        self.assertTrue(info["candidate_confidence"]["enabled"])

    def test_opt_in_requires_candidate_generation_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            wav = Path(folder) / "audio.wav"
            wavfile.write(wav, 22050, np.zeros(22050, dtype=np.int16))
            with self.assertRaisesRegex(ValueError, "requires opt-in"):
                transcribe_drum_wav(wav, hat_candidate_confidence=HatCandidateConfidence())

    def test_default_drum_midi_unchanged_when_confidence_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            wav = Path(folder) / "hits.wav"
            sr = 22050
            audio = np.zeros(2 * sr, dtype=np.float64)
            rng = np.random.default_rng(12)
            for at in (.32, .7, 1.3):
                start = round(at * sr)
                n = 1400
                audio[start:start+n] += .25 * rng.normal(size=n) * np.exp(-np.arange(n)/160)
            wavfile.write(wav, sr, np.round(np.clip(audio,-1,1)*26000).astype(np.int16))
            old, _ = transcribe_drum_wav(wav)
            new, _ = transcribe_drum_wav(wav, hat_candidate_confidence=None)
            original = [(n.pitch, n.start, n.end, n.velocity) for ins in old.instruments for n in ins.notes]
            retained = [(n.pitch, n.start, n.end, n.velocity) for ins in new.instruments for n in ins.notes]
            self.assertEqual(original, retained)


if __name__ == "__main__":
    unittest.main()
