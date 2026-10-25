"""Offline provenance and one-to-one MIDI label replay attestation tests.

No network, model checkpoints, copyrighted audio, or GitHub Actions needed.
"""
from __future__ import annotations

import unittest

from midivolt.drum_replay_evidence import build_evidence


def _sample(song: str, engine: str, *, pairs: bool = False):
    metrics = {"tp": 1, "fp": 1, "fn": 1}
    pitch = {
        "35": {"fp": 1, "fn": 0},
        "36": {"fp": 0, "fn": 1},
        "42": {"fp": 0, "fn": 0, "tp": 1},
    }
    row = {
        "song_id": song, "engine": engine,
        "audio_domain": "electronic_kit_recording",
        "failed": False,
        "scores": {"micro": metrics, "per_gm_pitch": pitch},
        "alignment_quality": {
            "status": "no_large_offset_detected",
            "median_audio_minus_midi_ms": 3.0,
        },
    }
    if pairs:
        row["label_timing_diagnostic"] = {
            "original_exact_gm": metrics.copy(),
            "label_hypotheses": [
                {
                    "predicted_pitch": 35, "reference_pitch": 36,
                    "paired_within_tolerance": 1,
                    "suggestive_onset_evidence": False,
                },
                {
                    "predicted_pitch": 58, "reference_pitch": 43,
                    "paired_within_tolerance": 0,
                },
            ],
        }
    return row


def report(*, pairs: bool = False):
    song = "drummer1/session2/167"
    return {
        "status": "research_only_completed",
        "dataset": "E-GMD v1.0.0",
        "dataset_type": "human_performed_electronic_drumkit_audio_NOT_direct_acoustic_drums",
        "model": {"id": "adt-str", "revision": "a" * 40, "sha256": "b" * 64},
        "selection_plan_sha256": "c" * 64,
        "sample_provenance": [
            {
                "source_song_id": song,
                "wav_sha256": "d" * 64, "midi_sha256": "e" * 64,
                "source_split": "test", "kit_name": "Acoustic Kit",
            },
        ],
        "samples": [_sample(song, engine, pairs=pairs) for engine in ("dsp", "adt_str")],
    }


class ReplayEvidenceTests(unittest.TestCase):
    def test_old_report_does_not_claim_any_actual_onset_pair(self):
        result = build_evidence(report())
        self.assertEqual(result["status"], "awaiting_actual_predicted_MIDI_onsets")
        self.assertTrue(all(not x["actual_onset_pairs_known"] for x in result["hypotheses"]))
        self.assertEqual(result["hypotheses"][0]["max_possible_same_song_pairs"], 1)

    def test_actual_replay_requires_same_source_and_model(self):
        result = build_evidence(report(), report(pairs=True))
        self.assertEqual(result["status"], "paired_onset_evidence_available")
        self.assertTrue(result["actual_pairing_conclusion_allowed"])
        self.assertTrue(result["original_heldout_scores_unchanged"])
        kick = next(x for x in result["paired_event_evidence"] if x["predicted_pitch"] == 35)
        self.assertEqual(kick["onset_pairs"], 1)
        self.assertFalse(kick["proves_same_instrument"])

    def test_modified_audio_hash_rejected(self):
        old, updated = report(), report(pairs=True)
        updated["sample_provenance"][0]["wav_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "Changed source identity"):
            build_evidence(old, updated)

    def test_modified_midi_hash_rejected(self):
        old, updated = report(), report(pairs=True)
        updated["sample_provenance"][0]["midi_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "Changed source identity"):
            build_evidence(old, updated)

    def test_modified_checkpoint_rejected(self):
        old, updated = report(), report(pairs=True)
        updated["model"]["revision"] = "d" * 40
        with self.assertRaisesRegex(ValueError, "Different ADT_STR model"):
            build_evidence(old, updated)

    def test_score_drift_disallows_comparison(self):
        old, updated = report(), report(pairs=True)
        updated["samples"][1]["scores"]["micro"]["tp"] = 2
        updated["samples"][1]["label_timing_diagnostic"]["original_exact_gm"]["tp"] = 2
        result = build_evidence(old, updated)
        self.assertEqual(result["status"], "not_comparable_replay_drift")
        self.assertFalse(result["actual_pairing_conclusion_allowed"])
        self.assertEqual(len(result["score_drift"]), 1)

    def test_missing_new_label_audit_blocks_comparison(self):
        with self.assertRaisesRegex(ValueError, "No actual MIDI"):
            build_evidence(report(), report())

    def test_out_of_bound_pair_count_rejected(self):
        old, updated = report(), report(pairs=True)
        updated["samples"][1]["label_timing_diagnostic"]["label_hypotheses"][0]["paired_within_tolerance"] = 2
        with self.assertRaisesRegex(ValueError, "exceeds original"):
            build_evidence(old, updated)

    def test_suspected_offset_disallows_confident_pairing_claim(self):
        old, updated = report(), report(pairs=True)
        for obj in (old, updated):
            for sample in obj["samples"]:
                sample["alignment_quality"] = {
                    "status": "suspected_offset",
                    "median_audio_minus_midi_ms": -55.0,
                }
        result = build_evidence(old, updated)
        kick = next(x for x in result["paired_event_evidence"] if x["predicted_pitch"] == 35)
        self.assertFalse(kick["aligned_enough_for_timing_claim"])

    def test_different_domain_rejected(self):
        obj = report()
        obj["dataset_type"] = "acoustic_microphone_recording"
        with self.assertRaisesRegex(ValueError, "audio domain"):
            build_evidence(obj)


if __name__ == "__main__":
    unittest.main()
