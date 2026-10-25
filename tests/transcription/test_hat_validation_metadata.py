"""No-net E-GMD metadata selection and plan; synthetic test rows only."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from midivolt.hat_validation import choose_validation_metadata
from scripts.egmd_hat_prepare import prepare


FIELDS = [
    "drummer", "session", "id", "style", "bpm", "beat_type",
    "split", "midi_filename", "audio_filename", "kit_name", "duration",
]


def rows():
    result = []
    for n in range(1, 18):
        drummer = f"drummer{n % 4}"
        beat = "fill" if n % 3 == 0 else "beat"
        result.append({
            "id": f"{drummer}/session/{n}",
            "drummer": drummer,
            "session": f"{drummer}/session",
            "style": ("funk" if n % 2 else "rock") + "/groove",
            "bpm": str(90 + n * 3),
            "duration": str(2 + n),
            "beat_type": beat,
            "split": "validation",
            "kit_name": "Acoustic Kit",
            "midi_filename": f"{drummer}/session/{n}.midi",
            "audio_filename": f"{drummer}/session/{n}.wav",
        })
    return result


class HatValidationMetadataTests(unittest.TestCase):
    def test_selects_only_validation_with_long_beats_and_short_fills(self):
        result = choose_validation_metadata(rows(), count=6, short_fill_count=2)
        self.assertEqual(len(result), 6)
        self.assertEqual(sum(x["beat_type"] == "beat" for x in result), 4)
        self.assertEqual(sum(x["beat_type"] == "fill" for x in result), 2)
        self.assertTrue(all(x["split"] == "validation" for x in result))
        self.assertEqual(len({x["id"] for x in result}), 6)

    def test_deterministic_when_metadata_order_is_reversed(self):
        original = choose_validation_metadata(rows(), count=6)
        reversed_order = choose_validation_metadata(list(reversed(rows())), count=6)
        self.assertEqual([x["id"] for x in original],
                         [x["id"] for x in reversed_order])

    def test_rejects_missing_validation_fills(self):
        only_beats = [x for x in rows() if x["beat_type"] == "beat"]
        with self.assertRaisesRegex(ValueError, "Validation fill"):
            choose_validation_metadata(only_beats, count=6, short_fill_count=2)

    def test_does_not_substitute_train_or_test_examples(self):
        corrupted = [
            {**row, "split": ("test" if row["beat_type"] == "fill" else "train")}
            for row in rows()
        ]
        with self.assertRaisesRegex(ValueError, "Validation beat"):
            choose_validation_metadata(corrupted, count=6, short_fill_count=2)

    def test_rejects_cross_split_source_identity(self):
        example = rows()
        example.append({**example[0], "split": "test"})
        with self.assertRaisesRegex(ValueError, "spans train/test/validation"):
            choose_validation_metadata(example, count=6)

    def test_one_kit_render_per_source_song(self):
        examples = rows()
        extra_kit = [{**x, "kit_name": "Raw Dnb",
                      "audio_filename": x["audio_filename"].replace(".wav", "-alt.wav")}
                     for x in examples]
        choice = choose_validation_metadata(examples + extra_kit, count=6)
        self.assertEqual(len({x["id"] for x in choice}), 6)
        self.assertTrue(all(x["kit_name"] == "Acoustic Kit" for x in choice))

    def test_bad_selection_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, "selection sizes"):
            choose_validation_metadata(rows(), count=1)
        with self.assertRaisesRegex(ValueError, "selection sizes"):
            choose_validation_metadata(rows(), count=6, short_fill_count=6)

    def test_csv_plan_is_metadata_only_and_does_not_fetch_wav(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            csv_file = root / "e-gmd-v1.0.0.csv"
            with csv_file.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows())
            output = root / "private"
            info = prepare(csv_file, output, count=6, fills=2)
            self.assertEqual(info["status"], "validation_metadata_plan_created")
            self.assertFalse(info["wav_downloaded"])
            plan = json.loads((output / "validation_selection_plan.json").read_text())
            self.assertEqual(plan["upstream_split"], "validation")
            self.assertEqual(plan["beats"], 4)
            self.assertEqual(plan["fills"], 2)
            self.assertEqual(plan["song_count"], 6)
            self.assertEqual(plan["research_rights_status"], "pending_review")
            self.assertFalse((output / "private_pairs").exists())


if __name__ == "__main__":
    unittest.main()
