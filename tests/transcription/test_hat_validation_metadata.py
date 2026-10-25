"""No-net E-GMD metadata selection and plan; synthetic test rows only."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from midivolt.hat_validation import choose_validation_metadata, CUT21_VALIDATION_SONG_IDS
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

    def test_source_license_review_is_explicit_and_never_commercial_approval(self):
        from unittest.mock import patch

        def fake_extract(_url, selected, folder, *, max_entry_mb):
            folder.mkdir(parents=True, exist_ok=True)
            result = []
            for i, row in enumerate(selected):
                wav = folder / f"recording_{i:02d}.wav"
                ref = folder / f"recording_{i:02d}.mid"
                wav.write_bytes(b"mock-synthetic-wav-" + str(i).encode())
                ref.write_bytes(b"mock-synthetic-midi-" + str(i).encode())
                import hashlib
                result.append({
                    "source_song_id": row["id"],
                    "source_split": row["split"],
                    "kit_name": row["kit_name"],
                    "style": row["style"],
                    "bpm": float(row["bpm"]),
                    "wav": str(wav),
                    "midi": str(ref),
                    "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                    "midi_sha256": hashlib.sha256(ref.read_bytes()).hexdigest(),
                })
            return result

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            csv_file = root / "official.csv"
            with csv_file.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows())
            with patch("scripts.egmd_mini_real.preflight_ranges", return_value=1000), patch(
                "scripts.egmd_mini_real.acquire_selected", side_effect=fake_extract
            ):
                pending = prepare(csv_file, root / "pending", extract_range=True)
                self.assertFalse(pending["benchmark_execution_allowed"])
                self.assertFalse(pending["independent_legal_clearance"])
                self.assertTrue(Path(pending["manifest"]).is_file())

                reviewed = prepare(
                    csv_file, root / "reviewed", extract_range=True,
                    official_cc_by_research_review=True,
                )
                self.assertTrue(reviewed["benchmark_execution_allowed"])
                self.assertFalse(reviewed["independent_legal_clearance"])
                manifest_data = json.loads(Path(reviewed["manifest"]).read_text())
                self.assertEqual(len(manifest_data["samples"]), 6)
                self.assertFalse(
                    manifest_data["license_verification"]["legal_clearance_for_product_distribution"]
                )
                self.assertTrue(all(
                    s["rights"]["research_evaluation_allowed"]
                    and not s["rights"]["commercial_benchmark_allowed"]
                    and "automated" in s["rights"]["reviewer"]
                    for s in manifest_data["samples"]
                ))

    def test_new_shape_selection_explicitly_excludes_previous_validation_songs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            csv_file = root / "e-gmd-v1.0.0.csv"
            with csv_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows())
            earlier = root / "previous_selection_plan.json"
            earlier.write_text(json.dumps({
                "dataset": "E-GMD v1.0.0",
                "upstream_split": "validation",
                "samples": [{"id": name} for name in sorted(CUT21_VALIDATION_SONG_IDS)],
            }), encoding="utf-8")
            result = prepare(
                csv_file, root / "fresh", count=6, fills=2,
                exclude_plan_path=earlier,
            )
            self.assertEqual(result["status"], "validation_metadata_plan_created")
            report = json.loads((root / "fresh/validation_selection_plan.json").read_text())
            forbidden = set(CUT21_VALIDATION_SONG_IDS)
            actual = {entry["id"] for entry in report["samples"]}
            self.assertTrue(forbidden.isdisjoint(actual))
            self.assertTrue(report["excludes_previous_validation_experiments"])
            self.assertEqual(set(report["excluded_previous_validation_source_song_ids"]), forbidden)

    def test_previous_plan_with_missing_historical_song_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            csv_file = root / "e-gmd-v1.0.0.csv"
            with csv_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows())
            previous = root / "prior.json"
            previous.write_text(json.dumps({
                "dataset": "E-GMD v1.0.0",
                "upstream_split": "validation",
                "samples": [
                    {"id": name}
                    for name in sorted(CUT21_VALIDATION_SONG_IDS)[:-1]
                ],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly the six"):
                prepare(csv_file, root / "fresh",
                        exclude_plan_path=previous)

    def test_untrusted_previous_plan_is_rejected_before_audio_access(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            csv_file = root / "e-gmd-v1.0.0.csv"
            with csv_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows())
            previous = root / "prior.json"
            previous.write_text(json.dumps({
                "dataset": "E-GMD v1.0.0",
                "upstream_split": "test",
                "samples": [{"id": "someone/test1"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Excluded selection plan"):
                prepare(
                    csv_file, root / "fresh", count=6, fills=2,
                    exclude_plan_path=previous,
                )

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
