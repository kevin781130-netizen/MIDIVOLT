"""Replay identity gates: independent, synthetic ZIP fixtures; no model/WAV download."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from midivolt.egmd_replay_lock import (
    load_replay_lock, verify_audio_lock, verify_model_lock, verify_selection_lock,
)


def row():
    return {
        "id": "drummer1/session2/167", "drummer": "drummer1",
        "split": "test", "style": "afrocuban/rhumba",
        "beat_type": "fill", "bpm": "120",
        "duration": "2.0", "kit_name": "Acoustic Kit",
        "audio_filename": "drummer1/session2/167.wav",
        "midi_filename": "drummer1/session2/167.midi",
    }


def model():
    return {
        "id": "Pierfrancesco/adt-str", "revision": "a" * 40,
        "variant": "setting-tau-0.8", "sha256": "b" * 64,
        "commercial_status": "not_cleared",
    }


def source():
    return {
        "source_song_id": row()["id"],
        "source_split": "test",
        "kit_name": "Acoustic Kit",
        "official_wav_member": row()["audio_filename"],
        "official_midi_member": row()["midi_filename"],
        "wav_sha256": "c" * 64, "midi_sha256": "d" * 64,
    }


def zip_fixture(path: Path, *, changes=None, plan_changes=None):
    plan = {"selected": [row()], "metadata_sha256": "e" * 64}
    if plan_changes:
        plan_changes(plan)
    plan_bytes = (json.dumps(plan, indent=2) + "\n").encode("utf-8")
    report = {
        "status": "research_only_completed",
        "dataset": "E-GMD v1.0.0",
        "dataset_type": "human_performed_electronic_drumkit_audio_NOT_direct_acoustic_drums",
        "selection_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "sample_provenance": [source()],
        "model": model(),
    }
    if changes:
        changes(report)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("selection_plan.json", plan_bytes)
        z.writestr("research_metrics.json", json.dumps(report))
    return path


class EgmdReplayLockTests(unittest.TestCase):
    def with_lock(self, test):
        with tempfile.TemporaryDirectory() as d:
            file = zip_fixture(Path(d) / "six-songs.zip")
            test(load_replay_lock(file))

    def test_valid_selection_preflights_before_remote_zip(self):
        def check(lock):
            proof = verify_selection_lock(lock, [row()], "e" * 64)
            self.assertEqual(proof["stage"], "metadata_selection_identical")
            self.assertEqual(proof["source_song_count"], 1)
        self.with_lock(check)

    def test_valid_audio_and_midi_hashes_then_pinned_model(self):
        def check(lock):
            proof = verify_audio_lock(lock, [source()])
            self.assertEqual(proof["stage"], "identical_wav_and_midi_bytes_confirmed")
            self.assertTrue(proof["does_not_establish_audio_midi_alignment"])
            model_proof = verify_model_lock(lock, model())
            self.assertFalse(model_proof["commercial_release_approved"])
        self.with_lock(check)

    def test_metadata_csv_version_change_blocked(self):
        def check(lock):
            with self.assertRaisesRegex(ValueError, "CSV changed"):
                verify_selection_lock(lock, [row()], "f" * 64)
        self.with_lock(check)

    def test_changed_performer_song_blocked(self):
        def check(lock):
            changed = dict(row(), id="drummer2/session5/7")
            with self.assertRaisesRegex(ValueError, "selection drift"):
                verify_selection_lock(lock, [changed], "e" * 64)
        self.with_lock(check)

    def test_selection_order_and_count_change_blocked(self):
        def check(lock):
            with self.assertRaisesRegex(ValueError, "song count"):
                verify_selection_lock(lock, [row(), row()], "e" * 64)
        self.with_lock(check)

    def test_changed_selected_beat_type_blocked(self):
        def check(lock):
            changed = dict(row(), beat_type="beat")
            with self.assertRaisesRegex(ValueError, "beat_type"):
                verify_selection_lock(lock, [changed], "e" * 64)
        self.with_lock(check)

    def test_any_wav_checksum_difference_blocks_model(self):
        def check(lock):
            changed = dict(source(), wav_sha256="f" * 64)
            with self.assertRaisesRegex(ValueError, "wav_sha256"):
                verify_audio_lock(lock, [changed])
        self.with_lock(check)

    def test_any_midi_checksum_difference_blocks_model(self):
        def check(lock):
            changed = dict(source(), midi_sha256="f" * 64)
            with self.assertRaisesRegex(ValueError, "midi_sha256"):
                verify_audio_lock(lock, [changed])
        self.with_lock(check)

    def test_changed_original_zip_selection_digest_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            def make_bad(report):
                report["selection_plan_sha256"] = "f" * 64
            file = zip_fixture(Path(d) / "corrupted.zip", changes=make_bad)
            with self.assertRaisesRegex(ValueError, "selection plan SHA-256"):
                load_replay_lock(file)

    def test_changed_model_weight_rejected(self):
        def check(lock):
            changed = dict(model(), sha256="f" * 64)
            with self.assertRaisesRegex(ValueError, "Model changed"):
                verify_model_lock(lock, changed)
        self.with_lock(check)

    def test_changed_upstream_model_revision_rejected(self):
        def check(lock):
            changed = dict(model(), revision="f" * 40)
            with self.assertRaisesRegex(ValueError, "revision"):
                verify_model_lock(lock, changed)
        self.with_lock(check)

    def test_original_non_test_sample_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            def bad(report):
                report["sample_provenance"][0]["source_split"] = "train"
            file = zip_fixture(Path(d) / "train.zip", changes=bad)
            with self.assertRaisesRegex(ValueError, "Non-Test"):
                load_replay_lock(file)

    def test_baseline_wrong_audio_domain_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            def bad(report):
                report["dataset_type"] = "live_acoustic_microphone"
            file = zip_fixture(Path(d) / "other.zip", changes=bad)
            with self.assertRaisesRegex(ValueError, "electronic-kit"):
                load_replay_lock(file)


if __name__ == "__main__":
    unittest.main()
