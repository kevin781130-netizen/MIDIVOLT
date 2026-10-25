"""Offline regression cases for the original-F1-preserving drum report audit."""
from __future__ import annotations

import copy
import unittest

from midivolt.drum_report_audit import audit_report


def score(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else (1.0 if fn == 0 else 0.0)
    r = tp / (tp + fn) if tp + fn else (1.0 if fp == 0 else 0.0)
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 6), "recall": round(r, 6), "f1": round(f, 6)}


def fixture():
    # Two engines are paired on exactly the same reference drum clip.
    return {
        "status": "research_only_completed",
        "dataset": "E-GMD v1.0.0",
        "dataset_type": "human_performed_electronic_drumkit_audio_NOT_direct_acoustic_drums",
        "sample_provenance": [
            {
                "source_song_id": "drummer1/song1", "source_split": "test",
                "drummer": "drummer1", "kit_name": "Acoustic Kit",
            }
        ],
        "performance_by_engine": {
            "dsp": {
                "sample_count": 1, "song_count": 1, "failure_count": 0,
                "event_micro": score(1, 0, 1), "song_macro_f1": 0.666667,
                "latency_seconds_median": 0.01,
            },
            "adt_str": {
                "sample_count": 1, "song_count": 1, "failure_count": 0,
                "event_micro": score(1, 1, 1), "song_macro_f1": 0.5,
                "latency_seconds_median": 2.5,
            },
        },
        "samples": [
            {
                "engine": "dsp", "song_id": "drummer1/song1",
                "audio_domain": "electronic_kit_recording", "failed": False,
                "alignment_quality": {"status": "suspected_offset", "median_audio_minus_midi_ms": -51},
                "scores": {
                    "micro": score(1, 0, 1),
                    "per_gm_pitch": {"36": score(1, 0, 0), "42": score(0, 0, 1)},
                },
            },
            {
                "engine": "adt_str", "song_id": "drummer1/song1",
                "audio_domain": "electronic_kit_recording", "failed": False,
                "alignment_quality": {"status": "suspected_offset", "median_audio_minus_midi_ms": -51},
                "scores": {
                    "micro": score(1, 1, 1),
                    "per_gm_pitch": {
                        "35": score(0, 1, 0), "36": score(1, 0, 0),
                        "42": score(0, 0, 1),
                    },
                },
            },
        ],
    }


class DrumReportAuditTests(unittest.TestCase):
    def test_reports_original_scores_without_f1_modifications(self):
        out = audit_report(fixture())
        self.assertEqual(out["evaluated_song_count"], 1)
        self.assertEqual(out["independent_drummer_count"], 1)
        self.assertEqual(out["engines"]["dsp"]["event_micro"]["f1"], 0.666667)
        self.assertEqual(out["engines"]["adt_str"]["event_micro"]["f1"], 0.5)
        self.assertEqual(len(out["rejected_alignment_or_inconclusive"]), 1)
        self.assertFalse(out["commercial_release_gate"]["allowed"])

    def test_potential_label_pair_never_claimed_to_be_true_match(self):
        item = fixture()
        item["samples"][1]["scores"]["per_gm_pitch"]["42"] = score(0, 0, 1)
        out = audit_report(item)
        self.assertTrue(all(not x["proven_pairing"] for x in out["representation_mismatch_hypotheses"]))
        self.assertEqual(out["engines"]["adt_str"]["event_micro"]["fp"], 1)

    def test_candidate_kick_mapping_is_flagged_but_not_applied(self):
        item = fixture()
        ai = item["samples"][1]
        ai["scores"]["micro"] = score(0, 1, 2)
        ai["scores"]["per_gm_pitch"] = {
            "35": score(0, 1, 0),
            "36": score(0, 0, 1),
            "42": score(0, 0, 1),
        }
        item["performance_by_engine"]["adt_str"]["event_micro"] = score(0, 1, 2)
        item["performance_by_engine"]["adt_str"]["song_macro_f1"] = 0.0
        audit = audit_report(item)
        candidates = audit["representation_mismatch_hypotheses"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["predicted_gm_pitch"], 35)
        self.assertEqual(candidates[0]["reference_gm_pitch"], 36)
        self.assertFalse(candidates[0]["proven_pairing"])
        self.assertEqual(audit["engines"]["adt_str"]["event_micro"]["f1"], 0.0)

    def test_engine_missing_is_rejected(self):
        item = fixture()
        item["samples"].pop()
        with self.assertRaisesRegex(ValueError, "Both engines"):
            audit_report(item)

    def test_non_test_origin_is_rejected(self):
        item = fixture()
        item["sample_provenance"][0]["source_split"] = "train"
        with self.assertRaisesRegex(ValueError, "Non-held-out"):
            audit_report(item)

    def test_corrupted_f1_is_rejected(self):
        item = fixture()
        item["samples"][0]["scores"]["micro"]["f1"] = 0.99
        with self.assertRaisesRegex(ValueError, "inconsistent f1"):
            audit_report(item)

    def test_pitch_aggregation_inconsistent_is_rejected(self):
        item = fixture()
        item["samples"][1]["scores"]["per_gm_pitch"]["35"] = score(0, 2, 0)
        with self.assertRaisesRegex(ValueError, "pitch totals differ"):
            audit_report(item)

    def test_mismatched_alignment_same_song_rejected(self):
        item = fixture()
        item["samples"][1]["alignment_quality"]["status"] = "no_large_offset_detected"
        with self.assertRaisesRegex(ValueError, "alignment diagnostics"):
            audit_report(item)

    def test_reference_truth_mismatch_between_engines_rejected(self):
        item = fixture()
        item["samples"][1]["scores"]["per_gm_pitch"] = {
            "35": score(0, 1, 0), "36": score(1, 0, 1),
        }
        with self.assertRaisesRegex(ValueError, "ground-truth drum events|Ground truth mismatch"):
            audit_report(item)

    def test_acoustic_recording_mislabel_rejected(self):
        item = fixture()
        item["dataset_type"] = "real_acoustic_recording"
        with self.assertRaisesRegex(ValueError, "recording domain"):
            audit_report(item)

    def test_failed_inference_is_preserved(self):
        item = fixture()
        item["samples"][0]["failed"] = True
        item["performance_by_engine"]["dsp"]["failure_count"] = 1
        out = audit_report(item)
        self.assertEqual(out["engines"]["dsp"]["failure_count"], 1)


if __name__ == "__main__":
    unittest.main()
