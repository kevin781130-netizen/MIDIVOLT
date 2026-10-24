"""E-GMD metadata import and reference-label checks; no third-party downloads."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
import wave
from pathlib import Path

import pretty_midi

from midivolt.drum_suite import (
    _normalize_reference, validate_dataset, run_suite,
)
from midivolt.egmd_import import read_metadata, choose_test_samples, make_plan, build_review_manifest


FIELDS = [
    "drummer", "session", "id", "style", "bpm", "beat_type",
    "split", "midi_filename", "audio_filename", "kit_name",
]


def fixture_rows():
    performances = [
        ("drummer1/session1/1", "funk", "beat", "test"),
        ("drummer1/session1/2", "rock", "fill", "test"),
        ("drummer2/session2/3", "jazz", "beat", "test"),
        ("drummer3/session1/4", "pop", "beat", "train"),
    ]
    rows = []
    for ident, style, kind, split in performances:
        for kit in ("kit-A", "kit-B"):
            rows.append({
                "drummer": ident.split("/")[0],
                "session": "/".join(ident.split("/")[:2]),
                "id": ident,
                "style": style + "/secondary",
                "bpm": "118",
                "beat_type": kind,
                "split": split,
                "midi_filename": f"{ident}_drums.midi",
                "audio_filename": f"{ident}_{kit}.wav",
                "kit_name": kit,
            })
    return rows


def create_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def create_files(root: Path, rows):
    for row in rows:
        wav_path = root / row["audio_filename"]
        midi_path = root / row["midi_filename"]
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        midi_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(wav_path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(22050)
            f.writeframes(b"\x00\x00" * 22050)
        if not midi_path.exists():
            ref = pretty_midi.PrettyMIDI(initial_tempo=118)
            drum = pretty_midi.Instrument(program=0, is_drum=True)
            for pitch, start in ((22, 0.14), (26, 0.28), (58, 0.47)):
                drum.notes.append(pretty_midi.Note(
                    pitch=pitch, start=start, end=start + 0.1, velocity=100
                ))
            ref.instruments.append(drum)
            ref.write(str(midi_path))


class EgmdImportTests(unittest.TestCase):
    def test_only_upstream_test_performances_and_distinct_kits(self):
        selection = choose_test_samples(fixture_rows(), max_performances=2, kits_per_performance=2)
        self.assertEqual(len(selection), 4)
        self.assertTrue(all(r["split"] == "test" for r in selection))
        self.assertEqual(len({r["id"] for r in selection}), 2)
        self.assertEqual(len({(r["id"], r["kit_name"]) for r in selection}), 4)

    def test_selection_is_deterministic_across_csv_row_order(self):
        original = fixture_rows()
        first = choose_test_samples(original, max_performances=3, kits_per_performance=1)
        second = choose_test_samples(list(reversed(original)), max_performances=3, kits_per_performance=1)
        self.assertEqual(first, second)

    def test_upstream_metadata_integrity_and_required_fields(self):
        with tempfile.TemporaryDirectory() as t:
            csv_file = Path(t) / "metadata.csv"
            create_csv(csv_file, fixture_rows())
            self.assertEqual(len(read_metadata(csv_file)), 8)
            create_csv(csv_file, [{k:v for k,v in row.items() if k != "kit_name"}
                                  for row in fixture_rows()])
            with self.assertRaisesRegex(ValueError, "kit_name"):
                read_metadata(csv_file)

    def test_selection_plan_does_not_need_90gb_download(self):
        with tempfile.TemporaryDirectory() as t:
            plan = make_plan(
                choose_test_samples(fixture_rows(), max_performances=1), Path(t)
            )
            self.assertEqual(plan["pairs_with_local_files"], 0)
            self.assertEqual(plan["pair_count"], 2)
            self.assertEqual(plan["audio_domain"], "electronic_kit_recording")
            self.assertFalse(plan["license_clearance"] == "approved")

    def test_review_manifest_requires_all_selected_wav_and_midi_files(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            rows = choose_test_samples(fixture_rows(), max_performances=1)
            with self.assertRaisesRegex(ValueError, "missing"):
                build_review_manifest(rows, root)
            create_files(root, rows)
            result = build_review_manifest(rows, root)
            self.assertEqual(len(result["samples"]), 2)
            self.assertEqual({s["source_song_id"] for s in result["samples"]},
                             {"e_gmd_" + rows[0]["id"]})
            self.assertEqual(result["samples"][0]["reference_midi_mapping"], "roland_td11_to_gm")
            self.assertTrue(all(s["rights"]["status"] == "pending" for s in result["samples"]))

    def test_real_electronic_kit_evaluation_blocked_until_rights_approval(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            selected = choose_test_samples(fixture_rows(), max_performances=1)
            create_files(root, selected)
            dataset = build_review_manifest(selected, root)
            path = root / "manifest.json"
            path.write_text(json.dumps(dataset), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing approved commercial benchmark"):
                validate_dataset(path)

    def test_roland_non_gm_hits_normalized_without_mutating_reference(self):
        ref = pretty_midi.PrettyMIDI()
        ins = pretty_midi.Instrument(program=0, is_drum=True)
        for p in (22, 26, 58, 37):
            ins.notes.append(pretty_midi.Note(pitch=p, start=0.25, end=0.4, velocity=80))
        ref.instruments.append(ins)
        mapped = _normalize_reference(ref, "roland_td11_to_gm")
        self.assertEqual(sorted(n.pitch for n in mapped.instruments[0].notes), [37, 42, 43, 46])
        self.assertEqual(sorted(n.pitch for n in ref.instruments[0].notes), [22, 26, 37, 58])

    def test_human_performed_electronic_kit_not_labeled_acoustic_recording(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            rows = choose_test_samples(fixture_rows(), max_performances=2, kits_per_performance=1)
            create_files(root, rows)
            dataset = build_review_manifest(rows, root)
            for sample in dataset["samples"]:
                sample["rights"]["status"] = "approved"
                sample["rights"]["commercial_benchmark_allowed"] = True
                sample["rights"]["reviewer"] = "fixture reviewer (unit tests only)"
            path = root / "manifest.json"
            path.write_text(json.dumps(dataset), encoding="utf-8")
            def mock_dsp(wav):
                result = pretty_midi.PrettyMIDI()
                track = pretty_midi.Instrument(program=0, is_drum=True)
                for p, start in ((42, 0.14), (46, 0.28), (43, 0.47)):
                    track.notes.append(pretty_midi.Note(pitch=p, start=start, end=start + 0.1, velocity=100))
                result.instruments.append(track)
                return result, {"source": "fixture only"}
            output = run_suite(path, output_dir=root / "out", engines=("dsp",), dsp_predict=mock_dsp)
            self.assertFalse(output["real_recordings_present"])
            self.assertTrue(output["electronic_kit_recordings_present"])
            self.assertEqual(output["by_audio_domain"]["electronic_kit_recording"]["dsp"]["song_count"], 2)
            self.assertEqual(output["by_audio_domain"]["electronic_kit_recording"]["dsp"]["event_micro"]["f1"], 1.0)
            self.assertEqual(output["by_audio_domain"]["real_recording"]["dsp"]["sample_count"], 0)


if __name__ == "__main__":
    unittest.main()
