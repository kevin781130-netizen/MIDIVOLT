"""Research-only shape comparison: fresh cohort, falsification controls, no Test."""
from __future__ import annotations

import copy
import unittest

import pretty_midi

from midivolt.drums import HatDetectionConfig
from midivolt.hat_shape import HatShapeGate
from midivolt.hat_shape_validation import (
    STUDY_ARMS, study_sha256, evaluate_shape_study,
)
from midivolt.hat_validation import CUT21_VALIDATION_SONG_IDS


def midi(*events):
    song = pretty_midi.PrettyMIDI(initial_tempo=120)
    track = pretty_midi.Instrument(program=0, is_drum=True)
    for pitch, onset in events:
        track.notes.append(pretty_midi.Note(
            pitch=pitch, velocity=90, start=onset, end=onset + .09
        ))
    song.instruments.append(track)
    return song


HATS = [(42, .2 + i * .19) for i in range(10)]


def cohort():
    entries = [
        {"song_id": "new_control", "wav": "new_control", "truth": midi((38, .3))}
    ]
    for i in range(5):
        entries.append({
            "song_id": f"new_song_{i}", "wav": f"new_song_{i}",
            "truth": midi(*HATS, (38, 2.4)),
        })
    plan = {
        "dataset": "E-GMD v1.0.0",
        "upstream_split": "validation",
        "excludes_previous_validation_experiments": True,
        "excluded_previous_validation_source_song_ids": sorted(CUT21_VALIDATION_SONG_IDS),
        "samples": [{"id": r["song_id"]} for r in entries],
    }
    return entries, plan


def good_mock(wav, *, hat_config, hat_shape_gate):
    if wav == "new_control":
        if hat_shape_gate is None and hat_config != STUDY_ARMS["baseline"][0]:
            return midi((38, .3), (42, .65)), {}
        return midi((38, .3)), {"shape_gate": {"rejected_candidates": 1}}
    if hat_shape_gate is None:
        count = 3 if hat_config == STUDY_ARMS["baseline"][0] else 8
    else:
        count = 6 if hat_config == STUDY_ARMS["moderate_shape"][0] else 4
    return midi(*HATS[:count], (38, 2.4)), {
        "shape_gate": {"rejected_candidates": max(0, 10-count)}
    }


class HatShapeValidationTests(unittest.TestCase):
    def test_four_frozen_experimental_arms(self):
        self.assertEqual(
            list(STUDY_ARMS),
            ["baseline", "moderate_unfiltered", "moderate_shape", "conservative_shape"],
        )
        self.assertIsNone(STUDY_ARMS["baseline"][1])
        self.assertIsNone(STUDY_ARMS["moderate_unfiltered"][1])
        self.assertIsInstance(STUDY_ARMS["moderate_shape"][1], HatShapeGate)
        self.assertEqual(len(study_sha256()), 64)

    def test_independent_validation_cohort_has_no_old_song_overlap(self):
        records, plan = cohort()
        report = evaluate_shape_study(records, selection_plan=plan, transcriber=good_mock)
        self.assertEqual(report["new_cohort_proof"]["previous_validation_songs_excluded"], 6)
        self.assertTrue(report["new_cohort_proof"]["zero_previous_songs_reused"])
        self.assertEqual(report["sample_count"], 6)
        self.assertTrue(report["official_test_partition_not_touched"])
        self.assertTrue(report["production_dsp_default_unchanged"])

    def test_precision_safe_shape_candidate_not_automatic_production(self):
        records, plan = cohort()
        report = evaluate_shape_study(records, selection_plan=plan, transcriber=good_mock)
        self.assertEqual(report["decision"]["status"], "validation_only_candidate_not_auto_applied")
        self.assertEqual(report["decision"]["candidate"], "moderate_shape")
        self.assertGreater(
            report["summary_by_arm"]["moderate_shape"]["closed_hi_hat"]["recall"],
            report["summary_by_arm"]["baseline"]["closed_hi_hat"]["recall"],
        )
        self.assertEqual(
            report["negative_control"]["false_gm42_by_arm"]["moderate_shape"], 0
        )
        self.assertEqual(
            report["negative_control"]["false_gm42_by_arm"]["moderate_unfiltered"], 1
        )

    def test_negative_control_blocks_false_hats_even_if_recall_wins(self):
        records, plan = cohort()
        def unsafe_shape(wav, *, hat_config, hat_shape_gate):
            output, details = good_mock(
                wav, hat_config=hat_config, hat_shape_gate=hat_shape_gate
            )
            if wav == "new_control" and hat_shape_gate is not None:
                return midi((38, .3), (42, .68)), details
            return output, details
        report = evaluate_shape_study(
            records, selection_plan=plan, transcriber=unsafe_shape
        )
        self.assertEqual(report["decision"]["status"], "retain_production_baseline")
        self.assertTrue(any(
            "new_false_closed_hat_on_negative_controls" in check["blocked_by"]
            for check in report["decision"]["comparisons"]
            if check["name"] == "moderate_shape"
        ))

    def test_without_negative_control_cannot_pick_preset(self):
        records, plan = cohort()
        records[0]["truth"] = midi((42, .2), (38, .3))
        report = evaluate_shape_study(records, selection_plan=plan, transcriber=good_mock)
        self.assertEqual(report["decision"]["status"],
                         "blocked_missing_no_hat_negative_control")

    def test_cannot_reuse_previous_validation_song(self):
        records, plan = cohort()
        prior = sorted(CUT21_VALIDATION_SONG_IDS)[0]
        records[0]["song_id"] = prior
        plan["samples"][0]["id"] = prior
        with self.assertRaisesRegex(ValueError, "Reused previous"):
            evaluate_shape_study(records, selection_plan=plan, transcriber=good_mock)

    def test_missing_exclusion_provenance_refused(self):
        records, plan = cohort()
        plan["excludes_previous_validation_experiments"] = False
        with self.assertRaisesRegex(ValueError, "exclude previous"):
            evaluate_shape_study(records, selection_plan=plan, transcriber=good_mock)

    def test_manifest_and_selection_must_match(self):
        records, plan = cohort()
        plan["samples"][0]["id"] = "different_song"
        with self.assertRaisesRegex(ValueError, "Manifest WAV/MIDI"):
            evaluate_shape_study(records, selection_plan=plan, transcriber=good_mock)

    def test_fewer_than_six_songs_blocked(self):
        records, plan = cohort()
        del records[-1]
        del plan["samples"][-1]
        with self.assertRaisesRegex(ValueError, "At least six"):
            evaluate_shape_study(records, selection_plan=plan, transcriber=good_mock)

    def test_invalid_duplicate_exclusions_refused(self):
        records, plan = cohort()
        plan["excluded_previous_validation_source_song_ids"].append(
            plan["excluded_previous_validation_source_song_ids"][0]
        )
        with self.assertRaisesRegex(ValueError, "duplicate exclusions"):
            evaluate_shape_study(records, selection_plan=plan, transcriber=good_mock)


if __name__ == "__main__":
    unittest.main()
