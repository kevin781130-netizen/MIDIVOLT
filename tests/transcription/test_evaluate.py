"""Deterministic evaluator tests; no model download is required."""
from __future__ import annotations

import unittest

import pretty_midi

from midivolt.evaluate import evaluate


def midi(*events, drum=False):
    data = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0, is_drum=drum, name="test")
    for pitch, start, end in events:
        inst.notes.append(pretty_midi.Note(velocity=90, pitch=pitch, start=start, end=end))
    data.instruments.append(inst)
    return data


class ScoreTests(unittest.TestCase):
    def test_perfect_matching(self):
        reference = midi((60, 0.1, 0.6), (64, 1.0, 1.5))
        report = evaluate(reference, reference)
        self.assertEqual(report["note_onset"]["tp"], 2)
        self.assertEqual(report["note_onset"]["f1"], 1.0)
        self.assertEqual(report["strict_note_onset_offset"]["f1"], 1.0)
        self.assertEqual(report["timing_of_onset_matched_notes"]["onset_mae_ms"], 0.0)

    def test_duplicate_note_is_false_positive(self):
        reference = midi((60, 0.5, 1.0))
        predicted = midi((60, 0.5, 1.0), (60, 0.51, 0.98))
        report = evaluate(reference, predicted)
        self.assertEqual(report["note_onset"]["tp"], 1)
        self.assertEqual(report["note_onset"]["fp"], 1)
        self.assertEqual(report["note_onset"]["fn"], 0)
        self.assertEqual(report["diagnostics"]["duplicate_onset_candidates"], 1)

    def test_offset_error_fails_strict_but_passes_onset(self):
        reference = midi((60, 1.0, 1.5))
        predicted = midi((60, 1.02, 1.9))
        report = evaluate(reference, predicted)
        self.assertEqual(report["note_onset"]["f1"], 1.0)
        self.assertEqual(report["strict_note_onset_offset"]["f1"], 0.0)
        self.assertAlmostEqual(report["timing_of_onset_matched_notes"]["onset_mae_ms"], 20)
        self.assertAlmostEqual(report["timing_of_onset_matched_notes"]["offset_mae_ms"], 400)

    def test_octave_false_note_and_missing_reference(self):
        reference = midi((60, 1.0, 1.5))
        predicted = midi((72, 1.01, 1.5))
        report = evaluate(reference, predicted)
        self.assertEqual(report["note_onset"]["fp"], 1)
        self.assertEqual(report["note_onset"]["fn"], 1)
        self.assertEqual(report["diagnostics"]["octave_error_candidates"], 1)
        self.assertEqual(report["diagnostics"]["unmatched_predicted_notes"][0]["pitch"], 72)

    def test_split_tail_fragment_detected(self):
        reference = midi((60, 0.35, 1.28))
        predicted = midi((60, 0.35, 1.28), (60, 1.219, 1.335))
        report = evaluate(reference, predicted)
        self.assertEqual(report["diagnostics"]["split_tail_fragment_candidates"], 1)
        self.assertEqual(report["note_onset"]["fp"], 1)

    def test_max_cardinality_not_greedy(self):
        reference = midi((60, 1.0, 1.5), (60, 1.06, 1.56))
        predicted = midi((60, 0.98, 1.5), (60, 1.03, 1.56))
        report = evaluate(reference, predicted)
        self.assertEqual(report["note_onset"]["tp"], 2)

    def test_empty_reference_and_prediction(self):
        report = evaluate(midi(), midi())
        self.assertEqual(report["note_onset"]["f1"], 1.0)
        self.assertIsNone(report["timing_of_onset_matched_notes"]["onset_mae_ms"])

    def test_missing_all_reference_notes(self):
        report = evaluate(midi((60, 0.1, 0.5)), midi())
        self.assertEqual(report["note_onset"]["fn"], 1)
        self.assertEqual(report["note_onset"]["f1"], 0.0)

    def test_drum_performance_requires_separate_evaluator(self):
        with self.assertRaisesRegex(ValueError, "Drum MIDI"):
            evaluate(midi((36, 1.0, 1.05), drum=True), midi())

    def test_reject_invalid_tolerance(self):
        with self.assertRaisesRegex(ValueError, "onset_tolerance"):
            evaluate(midi(), midi(), onset_tolerance_ms=0)


if __name__ == "__main__":
    unittest.main()
