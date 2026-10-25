"""E-GMD metadata-only held-out selection regression tests.

No model downloads, no training/testing leakage and no original data assets.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from midivolt.egmd_selection import select_diverse_test_rows, select_mixed_test_rows, selection_summary
from scripts.egmd_mini_real import _float_pcm


def sample(performance: int, *, drummer: str, typ: str, duration: float,
           kit: str = "Acoustic Kit", split: str = "test") -> dict:
    return {
        "id": f"{drummer}/session1/{performance}",
        "drummer": drummer,
        "session": f"{drummer}/session1",
        "kit_name": kit,
        "beat_type": typ,
        "style": ("funk" if performance % 3 == 0 else "rock" if performance % 3 == 1 else "jazz") + "/groove",
        "duration": str(duration),
        "split": split,
        "bpm": str(65 + (performance % 10) * 19),
        "midi_filename": f"{drummer}/session1/{performance}.midi",
        "audio_filename": f"{drummer}/session1/{performance}.wav",
    }


def demo():
    data = []
    for n in range(1, 13):
        person = f"drummer{n % 5 + 1}"
        data.append(sample(n, drummer=person,
                           typ=("beat" if n % 2 else "fill"),
                           duration=9.0 + (n % 7) * 4.0))
    # A large kit catalog should NOT imply extra independent performances.
    for row in list(data):
        data.append({**row, "kit_name": "Raw Dnb",
                     "audio_filename": row["audio_filename"].replace(".wav", "_raw_dnb.wav")})
    data.append(sample(100, drummer="drummer_extra", typ="beat", duration=20, split="train"))
    data.append(sample(101, drummer="drummer_extra", typ="fill", duration=20, split="validation"))
    data.append(sample(102, drummer="drummer_extra", typ="beat", duration=2.5))
    return data


class DiverseSelectionTests(unittest.TestCase):
    def test_chooses_six_long_diverse_test_performances(self):
        selected = select_diverse_test_rows(demo(), count=6, min_drummers=3)
        report = selection_summary(selected)
        self.assertEqual(report["performance_count"], 6)
        self.assertEqual(report["unique_song_ids"], 6)
        self.assertGreaterEqual(report["drummer_count"], 3)
        self.assertEqual(set(report["beat_types"]), {"beat", "fill"})
        self.assertGreaterEqual(report["duration_seconds_min_max"][0], 8)
        self.assertTrue(all(x["split"] == "test" for x in selected))
        self.assertEqual(report["kit_names"], ["Acoustic Kit"])
        self.assertEqual(report["selection_policy"], "metadata_only_before_inference_no_test_tuning")

    def test_selection_deterministic_under_metadata_row_permutation(self):
        rows = demo()
        original = select_diverse_test_rows(rows, count=6)
        shuffled = select_diverse_test_rows(list(reversed(rows)), count=6)
        self.assertEqual([x["id"] for x in original], [x["id"] for x in shuffled])

    def test_no_train_or_validation_substitution(self):
        rows = [sample(1, drummer="a", typ="beat", duration=22, split="train"),
                sample(2, drummer="b", typ="fill", duration=24, split="validation")]
        with self.assertRaisesRegex(ValueError, "official Test"):
            select_diverse_test_rows(rows, count=1, min_drummers=1)

    def test_fail_closed_if_diverse_drummers_unavailable(self):
        rows = [sample(i, drummer="only", typ="beat" if i % 2 else "fill", duration=20)
                for i in range(1, 10)]
        with self.assertRaisesRegex(ValueError, "distinct eligible drummers"):
            select_diverse_test_rows(rows, count=6, min_drummers=3)

    def test_fail_closed_if_long_test_recordings_unavailable(self):
        rows = [sample(i, drummer=f"d{i}", typ="beat", duration=2.0)
                for i in range(1, 7)]
        with self.assertRaisesRegex(ValueError, "official Test"):
            select_diverse_test_rows(rows, count=6, min_drummers=3)

    def test_no_duplicate_real_performances_from_multiple_kits(self):
        rows = demo()
        with self.assertRaisesRegex(ValueError, "official Test"):
            select_diverse_test_rows(rows, count=20, min_drummers=3)

    def test_explicit_kit_selection(self):
        selected = select_diverse_test_rows(demo(), count=3, min_drummers=2, kit="Raw Dnb")
        self.assertTrue(all(item["kit_name"] == "Raw Dnb" for item in selected))

    def test_mixed_selection_keeps_long_grooves_and_short_fills(self):
        rows = demo()
        rows.extend([
            sample(31, drummer="drummer2", typ="fill", duration=2.5),
            sample(32, drummer="drummer3", typ="fill", duration=3.5),
            sample(33, drummer="drummer4", typ="fill", duration=3.0),
        ])
        selected = select_mixed_test_rows(rows, count=6, short_fill_count=2,
                                          min_drummers=3, min_long_duration=8.0,
                                          max_long_duration=35.0)
        self.assertEqual(len(selected), 6)
        report = selection_summary(selected)
        self.assertGreaterEqual(report["drummer_count"], 3)
        self.assertEqual(report["beat_types"], {"beat": 4, "fill": 2})
        self.assertTrue(all(float(s["duration"]) >= 8 for s in selected if s["beat_type"] == "beat"))
        self.assertTrue(all(float(s["duration"]) <= 7 for s in selected if s["beat_type"] == "fill"))
        self.assertEqual(len({s["id"] for s in selected}), 6)

    def test_mixed_selection_aborts_when_short_fill_stratum_is_absent(self):
        with self.assertRaisesRegex(ValueError, "official Test"):
            select_mixed_test_rows(demo(), count=6, short_fill_count=2, min_drummers=3)

    def test_mixed_selection_is_deterministic(self):
        rows = demo() + [
            sample(31, drummer="drummer2", typ="fill", duration=2.5),
            sample(32, drummer="drummer3", typ="fill", duration=3.5),
        ]
        a = select_mixed_test_rows(rows, count=6, short_fill_count=2, min_drummers=3)
        b = select_mixed_test_rows(list(reversed(rows)), count=6,
                                   short_fill_count=2, min_drummers=3)
        self.assertEqual([s["id"] for s in a], [s["id"] for s in b])

    def test_pcm_stereo_int16_normalization_not_broken(self):
        samples = np.array([[16384, 16384], [-16384, -16384], [0, 0]], dtype=np.int16)
        mono = _float_pcm(samples)
        self.assertEqual(mono.shape, (3,))
        self.assertTrue(np.allclose(mono, [0.5, -0.5, 0], atol=0.001))

    def test_pcm_stereo_uint8_normalization(self):
        samples = np.array([[255, 255], [0, 0], [128, 128]], dtype=np.uint8)
        mono = _float_pcm(samples)
        self.assertTrue(np.allclose(mono, [127/128, -1, 0], atol=0.001))

    def test_pcm_mono_float_is_preserved(self):
        samples = np.array([0.25, -0.25, 0], dtype=np.float32)
        self.assertTrue(np.array_equal(_float_pcm(samples), samples))


if __name__ == "__main__":
    unittest.main()
