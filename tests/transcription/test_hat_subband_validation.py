"""Safety tests for independent 24-song dual-subband Validation A/B.

Mocked waveforms/predictions, NOT real E-GMD scores.
"""
from __future__ import annotations

import copy
import unittest

import pretty_midi

from midivolt.hat_subband import HatSubbandConfig
from midivolt.hat_subband_validation import (
    ARMS, EXCLUDED_PREVIOUS_SONG_IDS, STUDY_REVISION,
    evaluate_candidate_generator, settings_digest,
)


def midi(*hits):
    song = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=0, is_drum=True)
    for p, t in hits:
        inst.notes.append(pretty_midi.Note(
            velocity=100, pitch=p, start=t, end=t + 0.09
        ))
    song.instruments.append(inst)
    return song


HATS = [(42, .2 + .18 * n) for n in range(30)]


def study():
    records = []
    selection = []
    for n in range(24):
        identity = f"fresh/drummer{n%4}/song{n}"
        record = {
            "song_id": identity,
            "wav": identity,
            "truth": midi(*HATS, (38, 6.3)) if n < 4 else midi((38, .9)),
        }
        records.append(record)
        selection.append({
            "id": identity, "drummer": f"drummer{n%4}", "split": "validation",
            "kit_name": "Acoustic Kit",
        })
    plan = {
        "dataset": "E-GMD v1.0.0",
        "upstream_split": "validation",
        "study_revision": STUDY_REVISION,
        "settings_digest": settings_digest(),
        "excluded_previous_song_ids": sorted(EXCLUDED_PREVIOUS_SONG_IDS),
        "selected": selection,
    }
    return records, plan


def mock_model(wav, *, hat_subband_config):
    index = int(wav.split("song")[-1])
    positive = index < 4
    if positive:
        count = 10 if hat_subband_config is None else 12
        result = midi(*HATS[:count], (38, 6.3))
    else:
        result = midi((38, .9))
    return result, {
        "subband_candidates": {
            "enabled": hat_subband_config is not None,
            "new_candidates": 2 if positive and hat_subband_config else 0,
        }
    }


class SubbandValidationTests(unittest.TestCase):
    def test_pinned_exact_two_arms_and_twelve_previous_songs(self):
        self.assertEqual(list(ARMS), ["baseline", "dual_subband"])
        self.assertIsNone(ARMS["baseline"])
        self.assertIsInstance(ARMS["dual_subband"], HatSubbandConfig)
        self.assertEqual(len(EXCLUDED_PREVIOUS_SONG_IDS), 12)
        self.assertEqual(len(settings_digest()), 64)

    def test_only_new_24_song_set_and_preserve_production_baseline(self):
        records, plan = study()
        report = evaluate_candidate_generator(
            records, plan, transcriber=mock_model
        )
        self.assertEqual(report["decision"]["status"], "validation_only_candidate_NOT_production")
        self.assertTrue(report["production_dsp_default_unchanged"])
        self.assertEqual(report["reference_gm42_count"], 120)
        self.assertEqual(report["provenance"]["drummers"], 4)
        self.assertEqual(report["positive_song_count"], 4)
        self.assertEqual(report["zero_hat_control_song_count"], 20)
        self.assertEqual(report["zero_hat_false_predictions_by_arm"]["dual_subband"], 0)
        self.assertGreater(report["decision"]["hat_recall_absolute_delta"], 0.03)

    def test_any_new_false_hat_on_negative_control_blocks_candidate(self):
        records, plan = study()
        def unsafe(wav, *, hat_subband_config):
            result, diagnostic = mock_model(wav, hat_subband_config=hat_subband_config)
            if wav.endswith("song4") and hat_subband_config is not None:
                result.instruments[0].notes.append(
                    pretty_midi.Note(velocity=100, pitch=42, start=1.3, end=1.39)
                )
            return result, diagnostic
        report = evaluate_candidate_generator(
            records, plan, transcriber=unsafe
        )
        self.assertEqual(report["decision"]["status"], "retain_production_baseline")
        self.assertIn(
            "new_false_gm42_on_zero_hat_negative_controls",
            report["decision"]["blocked_by"],
        )

    def test_new_lane_may_not_remove_or_shift_existing_notes(self):
        records, plan = study()
        def unsafe(wav, *, hat_subband_config):
            result, diagnostic = mock_model(wav, hat_subband_config=hat_subband_config)
            if hat_subband_config is not None:
                result.instruments[0].notes[0].start += .07
            return result, diagnostic
        with self.assertRaisesRegex(ValueError, "removed/moved"):
            evaluate_candidate_generator(records, plan, transcriber=unsafe)

    def test_new_lane_may_not_add_non_hat_notes(self):
        records, plan = study()
        def unsafe(wav, *, hat_subband_config):
            result, diagnostic = mock_model(wav, hat_subband_config=hat_subband_config)
            if hat_subband_config is not None:
                result.instruments[0].notes.append(
                    pretty_midi.Note(velocity=100, pitch=38, start=7.2, end=7.29)
                )
            return result, diagnostic
        with self.assertRaisesRegex(ValueError, "non-GM42"):
            evaluate_candidate_generator(records, plan, transcriber=unsafe)

    def test_previous_cut21_or_cut23_song_rejected(self):
        records, plan = study()
        reused = sorted(EXCLUDED_PREVIOUS_SONG_IDS)[0]
        records[0]["song_id"] = reused
        plan["selected"][0]["id"] = reused
        with self.assertRaisesRegex(ValueError, "old song reused"):
            evaluate_candidate_generator(records, plan, transcriber=mock_model)

    def test_train_and_test_split_cannot_be_used(self):
        records, plan = study()
        plan["selected"][0]["split"] = "test"
        with self.assertRaisesRegex(ValueError, "Test or Train"):
            evaluate_candidate_generator(records, plan, transcriber=mock_model)

    def test_less_than_24_songs_fails_closed(self):
        records, plan = study()
        plan["selected"].pop()
        records.pop()
        with self.assertRaisesRegex(ValueError, "Exactly 24"):
            evaluate_candidate_generator(records, plan, transcriber=mock_model)

    def test_changed_settings_digest_fails_closed(self):
        records, plan = study()
        plan["settings_digest"] = "x" * 64
        with self.assertRaisesRegex(ValueError, "settings drifted"):
            evaluate_candidate_generator(records, plan, transcriber=mock_model)

    def test_low_reference_hat_coverage_retains_baseline(self):
        records, plan = study()
        for rec in records[:3]:
            rec["truth"] = midi((38, .9))
        report = evaluate_candidate_generator(records, plan, transcriber=mock_model)
        self.assertEqual(report["positive_song_count"], 1)
        self.assertEqual(report["decision"]["status"], "retain_production_baseline")
        self.assertIn(
            "insufficient_pre_registered_positive_and_negative_control_coverage",
            report["decision"]["blocked_by"],
        )


if __name__ == "__main__":
    unittest.main()
