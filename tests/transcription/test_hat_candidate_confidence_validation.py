"""Frozen independent candidate-confidence Validation safety checks, no real media."""
from __future__ import annotations

import unittest
import pretty_midi

from midivolt.hat_candidate_confidence_validation import (
    REVISION, OLD_CUT25_PLAN_SHA256, CUT25_SONG_IDS, EXCLUSIONS,
    ARMS, settings_digest, evaluate_confidence_study,
)
from midivolt.hat_candidate_confidence import HatCandidateConfidence
from midivolt.hat_subband import HatSubbandConfig


def midi(*hits):
    m = pretty_midi.PrettyMIDI(initial_tempo=120)
    drum = pretty_midi.Instrument(program=0, is_drum=True)
    for pitch, onset in hits:
        drum.notes.append(
            pretty_midi.Note(pitch=pitch, velocity=80, start=onset, end=onset + .1)
        )
    m.instruments.append(drum)
    return m


HITS = [(42, .20 + i*.21) for i in range(35)]


def fake_cohort():
    records, selected = [], []
    for i in range(24):
        name = f"newdrummer{i%5}/song{i}"
        records.append({
            "song_id": name, "wav": name,
            "truth": midi(*HITS, (38, 9.0)) if i < 4 else midi((38, 9.0)),
        })
        selected.append({
            "id": name, "drummer": f"drummer{i%5}", "kit_name": "Acoustic Kit",
            "split": "validation",
        })
    plan = {
        "dataset": "E-GMD v1.0.0",
        "upstream_split": "validation",
        "study_revision": REVISION,
        "settings_digest": settings_digest(),
        "original_cut25_selection_sha256": OLD_CUT25_PLAN_SHA256,
        "excluded_previous_song_ids": sorted(EXCLUSIONS),
        "selected": selected,
    }
    return records, plan


def mock_recognizer(wav, *, hat_subband_config, hat_candidate_confidence):
    i = int(wav.split("song")[-1])
    if i >= 4:
        parts = [(38, 9.0)]
        if hat_subband_config is not None and hat_candidate_confidence is None:
            parts += [(42, 8.4)]
    else:
        count = (10 if hat_subband_config is None else
                 15 if hat_candidate_confidence is not None else 20)
        parts = HITS[:count] + [(38, 9.0)]
        if hat_subband_config is not None and hat_candidate_confidence is None:
            parts += [(42, 8.4)]
    return midi(*parts), {
        "subband_candidates": {
            "new_candidates": 5 if hat_candidate_confidence else 10,
            "candidate_confidence": {"rejected": 5 if hat_candidate_confidence else 0},
        }
    }


class ConfidenceStudyTests(unittest.TestCase):
    def test_fixed_three_arms_and_all_36_past_song_exclusions(self):
        self.assertEqual(list(ARMS), ["baseline", "raw_subband", "confidence_subband"])
        self.assertIsNone(ARMS["baseline"][0])
        self.assertIsInstance(ARMS["raw_subband"][0], HatSubbandConfig)
        self.assertIsNone(ARMS["raw_subband"][1])
        self.assertIsInstance(ARMS["confidence_subband"][1], HatCandidateConfidence)
        self.assertEqual(len(EXCLUSIONS), 36)
        self.assertEqual(len(CUT25_SONG_IDS), 24)
        self.assertEqual(len(settings_digest()), 64)

    def test_clean_confidence_candidate_is_still_research_only(self):
        rows, plan = fake_cohort()
        report = evaluate_confidence_study(rows, plan, transcriber=mock_recognizer)
        self.assertEqual(report["decision"]["status"], "validation_candidate_not_production")
        self.assertEqual(report["decision"]["blocked_by"], [])
        self.assertEqual(report["reference_closed_hat_count"], 140)
        self.assertEqual(report["provenance"]["past_songs_excluded"], 36)
        self.assertEqual(report["no_hat_control_tracks"], 20)
        self.assertEqual(report["raw_vs_filtered_hat"]["confident_new_true_hits"], 20)
        self.assertEqual(report["raw_vs_filtered_hat"]["confident_new_false_hits"], 0)
        self.assertFalse(report["commercial_beta_ready"])

    def test_new_false_hats_on_control_fail_regardless_of_gain(self):
        rows, plan = fake_cohort()
        def noisy(wav, *, hat_subband_config, hat_candidate_confidence):
            obj, detail = mock_recognizer(
                wav, hat_subband_config=hat_subband_config,
                hat_candidate_confidence=hat_candidate_confidence,
            )
            # This FP was ALREADY proposed by the raw generator.
            # Let the filter fail to reject it; it must not invent a new note.
            if wav.endswith("song4") and hat_candidate_confidence is not None:
                obj.instruments[0].notes.append(
                    pretty_midi.Note(pitch=42, velocity=80, start=8.4, end=8.5)
                )
            return obj, detail
        report = evaluate_confidence_study(rows, plan, transcriber=noisy)
        self.assertEqual(report["decision"]["status"], "retain_original_DSP_baseline")
        self.assertIn(
            "new_false_closed_hats_in_negative_controls",
            report["decision"]["blocked_by"],
        )

    def test_new_confidence_cannot_add_notes_not_generated_by_raw_subband(self):
        rows, plan = fake_cohort()
        def illegal(wav, *, hat_subband_config, hat_candidate_confidence):
            obj, detail = mock_recognizer(
                wav, hat_subband_config=hat_subband_config,
                hat_candidate_confidence=hat_candidate_confidence,
            )
            if hat_candidate_confidence is not None:
                obj.instruments[0].notes.append(
                    pretty_midi.Note(pitch=42, velocity=80, start=12, end=12.1)
                )
            return obj, detail
        with self.assertRaisesRegex(ValueError, "only filter"):
            evaluate_confidence_study(rows, plan, transcriber=illegal)

    def test_new_confidence_must_not_remove_baseline(self):
        rows, plan = fake_cohort()
        def illegal(wav, *, hat_subband_config, hat_candidate_confidence):
            obj, detail = mock_recognizer(
                wav, hat_subband_config=hat_subband_config,
                hat_candidate_confidence=hat_candidate_confidence,
            )
            if hat_candidate_confidence is not None:
                obj.instruments[0].notes = [
                    note for note in obj.instruments[0].notes if note.pitch != 38
                ]
            return obj, detail
        with self.assertRaisesRegex(ValueError, "must retain baseline"):
            evaluate_confidence_study(rows, plan, transcriber=illegal)

    def test_new_confidence_must_not_remove_baseline_kick(self):
        rows, plan = fake_cohort()
        rows[0]["truth"] = midi((36, .1), *HITS, (38, 9.0))
        def illegal(wav, *, hat_subband_config, hat_candidate_confidence):
            obj, detail = mock_recognizer(
                wav, hat_subband_config=hat_subband_config,
                hat_candidate_confidence=hat_candidate_confidence,
            )
            if hat_subband_config is None:
                obj.instruments[0].notes.append(
                    pretty_midi.Note(pitch=36, velocity=90, start=.1, end=.2)
                )
            return obj, detail
        with self.assertRaisesRegex(ValueError, "must retain baseline"):
            evaluate_confidence_study(rows, plan, transcriber=illegal)

    def test_prior_24_source_song_is_forbidden(self):
        rows, plan = fake_cohort()
        prior = sorted(CUT25_SONG_IDS)[0]
        rows[0]["song_id"] = prior
        plan["selected"][0]["id"] = prior
        with self.assertRaisesRegex(ValueError, "repeated Validation"):
            evaluate_confidence_study(rows, plan, transcriber=mock_recognizer)

    def test_test_partition_forbidden(self):
        rows, plan = fake_cohort()
        plan["selected"][0]["split"] = "test"
        with self.assertRaisesRegex(ValueError, "split"):
            evaluate_confidence_study(rows, plan, transcriber=mock_recognizer)

    def test_changed_sha_or_settings_fail_closed(self):
        rows, plan = fake_cohort()
        plan["original_cut25_selection_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "evidence"):
            evaluate_confidence_study(rows, plan, transcriber=mock_recognizer)
        plan["original_cut25_selection_sha256"] = OLD_CUT25_PLAN_SHA256
        plan["settings_digest"] = "0"*64
        with self.assertRaisesRegex(ValueError, "not frozen"):
            evaluate_confidence_study(rows, plan, transcriber=mock_recognizer)

    def test_too_few_songs_blocks_before_inference(self):
        rows, plan = fake_cohort()
        rows.pop()
        plan["selected"].pop()
        with self.assertRaisesRegex(ValueError, "24 new"):
            evaluate_confidence_study(rows, plan, transcriber=mock_recognizer)

    def test_low_reference_hat_coverage_cannot_promote(self):
        rows, plan = fake_cohort()
        for record in rows[:3]:
            record["truth"] = midi((38,9))
        report = evaluate_confidence_study(rows, plan, transcriber=mock_recognizer)
        self.assertIn(
            "insufficient_hihat_ground_truth_or_negative_control_coverage",
            report["decision"]["blocked_by"],
        )

    def test_raw_generator_can_be_bad_while_confidence_filters_it(self):
        rows, plan = fake_cohort()
        report = evaluate_confidence_study(rows, plan, transcriber=mock_recognizer)
        self.assertGreater(
            report["negative_control_false_hats"]["raw_subband"],
            report["negative_control_false_hats"]["confidence_subband"],
        )


if __name__ == "__main__":
    unittest.main()
