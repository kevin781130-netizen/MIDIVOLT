"""Tests of exact-first onsets and hypothetical cross-GM-pitch confusion."""
from __future__ import annotations

import unittest

import pretty_midi

from midivolt.drum_label_pairs import analyze_pitch_labels


def gm(*events, drum=True):
    """(pitch, onset) events with an unchanged native GM drum track."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    track = pretty_midi.Instrument(program=0, is_drum=drum)
    for pitch, onset in events:
        track.notes.append(
            pretty_midi.Note(velocity=100, pitch=pitch, start=onset, end=onset + 0.09)
        )
    midi.instruments.append(track)
    return midi


def hypothesis(report, predicted, truth):
    return next(
        row for row in report["label_hypotheses"]
        if row["predicted_pitch"] == predicted and row["reference_pitch"] == truth
    )


class LabelOnsetPairTests(unittest.TestCase):
    def test_three_time_aligned_kick_label_candidates_without_rescoring(self):
        truth = gm((36, .2), (36, .7), (36, 1.2))
        pred = gm((35, .209), (35, .708), (35, 1.194))
        report = analyze_pitch_labels(truth, pred)
        self.assertEqual(report["original_exact_gm"], {"tp": 0, "fp": 3, "fn": 3})
        candidate = hypothesis(report, 35, 36)
        self.assertEqual(candidate["paired_within_tolerance"], 3)
        self.assertTrue(candidate["suggestive_onset_evidence"])
        self.assertFalse(candidate["proves_same_instrument"])
        self.assertLess(candidate["onset_mae_ms"], 10)

    def test_exact_pitch_match_has_priority_and_prevents_false_remap(self):
        report = analyze_pitch_labels(
            gm((36, .2)), gm((36, .2), (35, .208))
        )
        self.assertEqual(report["original_exact_gm"], {"tp": 1, "fp": 1, "fn": 0})
        self.assertEqual(hypothesis(report, 35, 36)["paired_within_tolerance"], 0)

    def test_far_apart_kicks_are_not_label_matches(self):
        report = analyze_pitch_labels(gm((36, .2)), gm((35, .55)))
        item = hypothesis(report, 35, 36)
        self.assertEqual(item["paired_within_tolerance"], 0)
        self.assertIsNone(item["onset_mae_ms"])
        self.assertFalse(item["suggestive_onset_evidence"])

    def test_one_to_one_pairing_does_not_count_duplicate_hallucination(self):
        report = analyze_pitch_labels(
            gm((36, .2)), gm((35, .19), (35, .205))
        )
        self.assertEqual(hypothesis(report, 35, 36)["paired_within_tolerance"], 1)
        self.assertEqual(report["original_exact_gm"]["fp"], 2)

    def test_roland_pitch58_to_gm43_is_only_hypothesis(self):
        report = analyze_pitch_labels(gm((43, 1.2)), gm((58, 1.203)))
        candidate = hypothesis(report, 58, 43)
        self.assertEqual(candidate["paired_within_tolerance"], 1)
        self.assertFalse(candidate["suggestive_onset_evidence"])
        self.assertTrue(candidate["requires_decoder_and_instrument_schema_review"])

    def test_unrelated_simultaneous_hits_not_falsely_matched(self):
        report = analyze_pitch_labels(gm((36, 1), (38, 1)), gm((35, 1), (42, 1)))
        self.assertEqual(hypothesis(report, 35, 36)["paired_within_tolerance"], 1)
        self.assertEqual(hypothesis(report, 58, 43)["paired_within_tolerance"], 0)
        self.assertFalse(hypothesis(report, 35, 36)["proves_same_instrument"])

    def test_analysis_does_not_mutate_reference_or_predictions(self):
        truth = gm((36, .2))
        pred = gm((35, .21))
        before = (
            truth.instruments[0].notes[0].pitch,
            truth.instruments[0].notes[0].start,
            pred.instruments[0].notes[0].pitch,
            pred.instruments[0].notes[0].start,
        )
        analyze_pitch_labels(truth, pred)
        after = (
            truth.instruments[0].notes[0].pitch,
            truth.instruments[0].notes[0].start,
            pred.instruments[0].notes[0].pitch,
            pred.instruments[0].notes[0].start,
        )
        self.assertEqual(before, after)

    def test_musical_pitch_midi_cannot_be_misread_as_drum(self):
        with self.assertRaisesRegex(ValueError, "percussion"):
            analyze_pitch_labels(gm((36, .2)), gm((35, .2), drum=False))

    def test_invalid_search_window_rejected(self):
        with self.assertRaisesRegex(ValueError, "tolerance_ms"):
            analyze_pitch_labels(gm(), gm(), tolerance_ms=0)

    def test_null_shift_does_not_inflate_pairing(self):
        truth = gm((36, .2), (36, .7), (36, 1.2))
        prediction = gm((35, .21), (35, .71), (35, 1.21))
        candidates = hypothesis(analyze_pitch_labels(truth, prediction), 35, 36)
        self.assertTrue(all(n < 3 for n in candidates["shifted_null_control_pair_counts"].values()))

    def test_large_offset_does_not_falsely_prove_schema_match(self):
        truth = gm((36, .2), (36, .7))
        prediction = gm((35, .261), (35, .762))
        report = analyze_pitch_labels(truth, prediction)
        self.assertEqual(hypothesis(report, 35, 36)["paired_within_tolerance"], 0)
        expanded = analyze_pitch_labels(truth, prediction, tolerance_ms=100)
        self.assertEqual(hypothesis(expanded, 35, 36)["paired_within_tolerance"], 2)
        self.assertFalse(hypothesis(expanded, 35, 36)["proves_same_instrument"])


if __name__ == "__main__":
    unittest.main()
