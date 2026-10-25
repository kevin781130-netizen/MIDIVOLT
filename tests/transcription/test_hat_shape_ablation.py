"""No-network retrospective Conservative+shape ablation verification.

All audio/model calls are mocked; validates identical cohort, same
checkpoint/preset/old scores, and strictly no automatic promotion.
"""
from __future__ import annotations

import copy
import unittest

import pretty_midi

from midivolt.hat_validation import CUT21_VALIDATION_SONG_IDS
from midivolt.hat_shape_ablation import (
    ARMS, CUT23_PLAN_SHA256, CUT23_SONG_IDS, run_ablation,
)
from midivolt.hat_shape_validation import evaluate_shape_study


def midi(events):
    song = pretty_midi.PrettyMIDI(initial_tempo=120)
    track = pretty_midi.Instrument(program=0, is_drum=True)
    for pitch, start in events:
        track.notes.append(pretty_midi.Note(
            velocity=85, pitch=pitch, start=start, end=start + 0.09,
        ))
    song.instruments.append(track)
    return song


HATS = [(42, .2 + k * .21) for k in range(10)]


def setup():
    ids = sorted(CUT23_SONG_IDS)
    rows = []
    for i, name in enumerate(ids):
        rows.append({
            "song_id": name, "wav": name,
            "truth": midi([(38, 2.7)] + (HATS if i == 0 else [])),
        })
    plan = {
        "dataset": "E-GMD v1.0.0",
        "upstream_split": "validation",
        "excludes_previous_validation_experiments": True,
        "excluded_previous_validation_source_song_ids": sorted(CUT21_VALIDATION_SONG_IDS),
        "samples": [{"id": name} for name in ids],
    }
    return rows, plan


def detector(wav, *, hat_config, hat_shape_gate):
    is_control = wav != sorted(CUT23_SONG_IDS)[0]
    is_baseline = hat_config.peak_fraction_scale == 1.0
    if is_control:
        guesses = [(38, 2.7)]
        if not is_baseline and hat_shape_gate is None:
            guesses.append((42, 2.3))
    else:
        correct = 4 if is_baseline else 7
        guesses = [(38, 2.7)] + HATS[:correct]
        if not is_baseline and hat_shape_gate is None:
            guesses.append((42, 2.31))  # FP >50 ms from reference
    return midi(guesses), {"shape_gate":{"rejected_candidates":int(bool(hat_shape_gate))}}


class ConservativeAblationTests(unittest.TestCase):
    def make_prior(self, rows, plan):
        return evaluate_shape_study(
            rows, selection_plan=plan, transcriber=detector,
        )

    def test_fixed_two_arms_only(self):
        self.assertEqual(list(ARMS), ["conservative_unfiltered", "conservative_shape"])
        self.assertEqual(ARMS["conservative_unfiltered"][0], ARMS["conservative_shape"][0])
        self.assertIsNone(ARMS["conservative_unfiltered"][1])
        self.assertIsNotNone(ARMS["conservative_shape"][1])

    def test_pairing_attributes_removed_false_hat_not_new_hits(self):
        rows, plan = setup()
        previous = self.make_prior(rows, plan)
        out = run_ablation(
            rows, plan, previous, plan_sha256=CUT23_PLAN_SHA256,
            transcriber=detector,
        )
        self.assertTrue(out["prior_conservative_shape_scores_exactly_reproduced"])
        self.assertFalse(out["independent_confirmation"])
        self.assertFalse(out["candidate_promotion_allowed"])
        self.assertEqual(out["shape_minus_unfiltered"]["hat_tp"], 0)
        self.assertLess(out["shape_minus_unfiltered"]["hat_fp"], 0)
        self.assertGreater(out["shape_minus_unfiltered"]["hat_precision"], 0)
        self.assertEqual(out["shape_minus_unfiltered"]["other_instrument_changes"], 0)
        self.assertTrue(out["production_default_unchanged"])

    def test_any_wrong_baseline_sha_rejected(self):
        rows, plan = setup()
        with self.assertRaisesRegex(ValueError, "byte hash"):
            run_ablation(rows, plan, self.make_prior(rows, plan),
                         plan_sha256="0"*64, transcriber=detector)

    def test_changed_song_selection_fails_closed(self):
        rows, plan = setup()
        plan["samples"][0]["id"] = "not_this_performance"
        with self.assertRaisesRegex(ValueError, "Manifest WAV/MIDI"):
            run_ablation(rows, plan, self.make_prior(rows, setup()[1]),
                         plan_sha256=CUT23_PLAN_SHA256, transcriber=detector)

    def test_score_drift_blocks_attribution(self):
        rows, plan = setup()
        old = self.make_prior(rows, plan)
        old["summary_by_arm"]["conservative_shape"]["closed_hi_hat"]["tp"] += 1
        with self.assertRaisesRegex(ValueError, "score drift"):
            run_ablation(rows, plan, old,
                         plan_sha256=CUT23_PLAN_SHA256, transcriber=detector)

    def test_missing_old_original_arm_is_refused(self):
        rows, plan = setup()
        old = self.make_prior(rows, plan)
        del old["summary_by_arm"]["moderate_shape"]
        with self.assertRaisesRegex(ValueError, "Invalid historical"):
            run_ablation(rows, plan, old,
                         plan_sha256=CUT23_PLAN_SHA256, transcriber=detector)

    def test_filter_must_not_add_notes(self):
        rows, plan = setup()
        old = self.make_prior(rows, plan)
        def unsafe(wav, *, hat_config, hat_shape_gate):
            prediction, info = detector(wav, hat_config=hat_config,
                                        hat_shape_gate=hat_shape_gate)
            if hat_shape_gate is not None:
                prediction.instruments[0].notes.append(pretty_midi.Note(
                    velocity=90, pitch=42, start=3.05, end=3.12))
            return prediction, info
        with self.assertRaisesRegex(ValueError, "added or altered"):
            run_ablation(rows, plan, old,
                         plan_sha256=CUT23_PLAN_SHA256, transcriber=unsafe)

    def test_filter_must_not_remove_snare(self):
        rows, plan = setup()
        old = self.make_prior(rows, plan)
        def unsafe(wav, *, hat_config, hat_shape_gate):
            prediction, info = detector(wav, hat_config=hat_config,
                                        hat_shape_gate=hat_shape_gate)
            if hat_shape_gate is not None:
                prediction.instruments[0].notes = [
                    n for n in prediction.instruments[0].notes if n.pitch != 38
                ]
            return prediction, info
        with self.assertRaisesRegex(ValueError, "Kick/Snare"):
            run_ablation(rows, plan, old,
                         plan_sha256=CUT23_PLAN_SHA256, transcriber=unsafe)


if __name__ == "__main__":
    unittest.main()
