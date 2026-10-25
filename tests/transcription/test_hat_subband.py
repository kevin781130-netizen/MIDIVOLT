"""Dual-subband candidate generation: deterministic synthetic STFT/WAV regression.

These are engineering tests, NOT measured real E-GMD transcription accuracy.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from midivolt.drums import transcribe_drum_wav
from midivolt.hat_subband import (
    VERSION, HatSubbandConfig, propose_new_hat_onsets,
)


def fixture(*, one_band=False, snare_dominant=False):
    hz = np.arange(0, 11050, 50.0)
    time = np.arange(0, 3.0, 0.01)
    mag = np.full((len(hz), len(time)), .00008, dtype=float)
    bands = [(hz >= 5200) & (hz < 7500), (hz >= 7500) & (hz < 10500)]
    for frame, amplitude in ((45, 2.0), (101, .22)):
        mag[bands[0], frame:frame+3] += amplitude
        if not one_band:
            mag[bands[1], frame:frame+3] += amplitude
        if snare_dominant:
            mid = (hz >= 180) & (hz < 5200)
            mag[mid, frame:frame+3] += amplitude * 8
    pcm = np.full(int(3.0 * 22050), .025, dtype=float)
    return mag, hz, time, pcm


def get(*, existing=(), **fixture_opts):
    mag, hz, time, pcm = fixture(**fixture_opts)
    return propose_new_hat_onsets(
        mag, hz, time, pcm, 22050, list(existing),
        config=HatSubbandConfig(),
    )


class SubbandCandidateTests(unittest.TestCase):
    def test_two_band_consensus_detects_weak_after_loud(self):
        events, report = get()
        self.assertEqual(len(events), 2, report)
        self.assertAlmostEqual(events[0][0], .45, delta=.021)
        self.assertAlmostEqual(events[1][0], 1.01, delta=.021)
        self.assertGreater(events[0][1], 0)
        self.assertEqual(report["version"], VERSION)

    def test_dedupes_baseline_predicted_hat_and_keeps_new_weak_onset(self):
        events, report = get(existing=[.45])
        self.assertEqual(len(events), 1, report)
        self.assertAlmostEqual(events[0][0], 1.01, delta=.021)
        self.assertGreaterEqual(report["rejected"]["existing_hat"], 1)

    def test_one_band_noise_does_not_hallucinate_hat(self):
        events, report = get(one_band=True)
        self.assertEqual(events, [])
        self.assertGreater(report["rejected"]["unpaired_subband"], 0)

    def test_snare_midband_dominates_crossband_transient(self):
        events, report = get(snare_dominant=True)
        self.assertEqual(events, [])
        self.assertGreater(report["rejected"]["spectral_nonhat"], 0)

    def test_silence_gives_no_candidate(self):
        mag, hz, time, pcm = fixture()
        mag.fill(0)
        result, details = propose_new_hat_onsets(
            mag, hz, time, pcm, 22050, [], config=HatSubbandConfig(),
        )
        self.assertEqual(result, [])
        self.assertEqual(details["new_candidates"], 0)

    def test_no_duplicate_from_close_baseline_hat(self):
        events, _ = get(existing=[.47, 1.0])
        self.assertFalse(events)

    def test_invalid_config_nan_or_negative_blocks(self):
        for field, value in (
            ("mad_multiplier", float("nan")),
            ("global_floor_fraction", -1.0),
            ("min_rms", .5),
        ):
            with self.assertRaisesRegex(ValueError, field):
                HatSubbandConfig(**{field:value})

    def test_bad_stft_axes_rejected(self):
        mag, hz, time, pcm = fixture()
        with self.assertRaisesRegex(ValueError, "Expected STFT"):
            propose_new_hat_onsets(mag, hz[:-1], time, pcm, 22050, [],
                                   config=HatSubbandConfig())
        mag[0, 0] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            propose_new_hat_onsets(mag, hz, time, pcm, 22050, [],
                                   config=HatSubbandConfig())

    def test_original_dsp_default_is_identical_when_new_option_omitted(self):
        with tempfile.TemporaryDirectory() as d:
            sr = 22050
            audio = np.zeros(sr * 2, dtype=np.float32)
            rng = np.random.default_rng(52)
            for onset in (.25, .75, 1.3):
                idx = int(onset * sr)
                audio[idx:idx+1500] += .25 * rng.standard_normal(1500) * (
                    np.exp(-np.arange(1500) / 150)
                )
            path = Path(d) / "fixture.wav"
            wavfile.write(path, sr, np.round(np.clip(audio, -1, 1) * 22000).astype(np.int16))
            a, _ = transcribe_drum_wav(path)
            b, diag = transcribe_drum_wav(path, hat_subband_config=None)
            self.assertEqual(
                [(n.pitch, n.start, n.velocity) for inst in a.instruments for n in inst.notes],
                [(n.pitch, n.start, n.velocity) for inst in b.instruments for n in inst.notes]
            )
            self.assertFalse(diag["subband_candidates"]["enabled"])

    def test_opt_in_candidate_path_can_only_add_closed_hat_not_other_drums(self):
        with tempfile.TemporaryDirectory() as d:
            sr = 22050
            audio = np.zeros(sr * 2, dtype=np.float32)
            rng = np.random.default_rng(98)
            for onset in (.24, .56, 1.2):
                idx = int(onset * sr)
                audio[idx:idx+1500] += .23 * rng.standard_normal(1500) * (
                    np.exp(-np.arange(1500) / 180)
                )
            path = Path(d) / "fixture.wav"
            wavfile.write(path, sr, np.round(np.clip(audio, -1, 1)*22000).astype(np.int16))
            a, _ = transcribe_drum_wav(path)
            b, diag = transcribe_drum_wav(path, hat_subband_config=HatSubbandConfig())
            original = {(n.pitch, n.start, n.end, n.velocity) for inst in a.instruments for n in inst.notes}
            altered = {(n.pitch, n.start, n.end, n.velocity) for inst in b.instruments for n in inst.notes}
            # Velocity is normalized across ALL events after new detection;
            # validate only pitch and onset, not original velocity.
            before = {(p, t) for p,t,_,_ in original}
            after = {(p, t) for p,t,_,_ in altered}
            self.assertTrue(before.issubset(after))
            self.assertTrue(all(p == 42 for p,t in after-before))
            self.assertTrue(diag["subband_candidates"]["enabled"])


if __name__ == "__main__":
    unittest.main()
