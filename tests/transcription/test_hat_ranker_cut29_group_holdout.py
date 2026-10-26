"""Offline metadata/group-split and TRAIN scaling evaluation safety tests.

Synthetic WAV/MIDI mocks only; never report these F1 scores as E-GMD.
"""
from __future__ import annotations

import copy
import unittest

import pretty_midi

from midivolt.hat_candidate_ranker import HatRankerModel
from midivolt.hat_ranker_cut29_group_holdout import (
    REVISION, FIT_SONGS, SMALL_SONGS, GROUP_HOLDOUT_SONGS,
    choose_metadata_partition, compare_models, study_digest,
)


def source_rows():
    output = []
    for d in range(9):
        for kind in ("beat", "fill"):
            for n in range(35):
                identity = f"drummer{d}/session1/{kind}{n}"
                output.append({
                    "id": identity, "drummer": f"drummer{d}",
                    "session": f"drummer{d}/session1",
                    "split": "train", "kit_name": "Acoustic Kit",
                    "beat_type": kind, "style": f"rock{n%3}/groove",
                    "duration": "24.0",
                    "audio_filename": f"{identity}.wav",
                    "midi_filename": f"{identity}.mid",
                    "bpm": "110",
                })
    return output


def make_midi(events):
    obj = pretty_midi.PrettyMIDI(initial_tempo=120)
    drum = pretty_midi.Instrument(program=0, is_drum=True)
    for p, at in events:
        drum.notes.append(pretty_midi.Note(
            pitch=p, velocity=80, start=at, end=at+.1,
        ))
    obj.instruments.append(drum)
    return obj


HITS = [(42, .15+.16*k) for k in range(35)]


def setup():
    plan = choose_metadata_partition(source_rows())
    source = []
    for i, s in enumerate(plan["holdout"]):
        truth = make_midi(HITS+[(38, 7.0)]) if i < 8 else make_midi([(38, 7.0)])
        source.append({"song_id": s["id"], "wav": f"clip{i}", "truth": truth})
    def model(n):
        return HatRankerModel(
            mean=(1.,)*5, scale=(1.,)*5, weights=(.2,)*5,
            intercept=1.0, source_songs=n, positive_examples=40,
            negative_examples=40, training_manifest_sha256="b"*64,
        )
    return plan, source, model(12), model(25)


def predict(path, *, hat_subband_config, hat_ranker_model):
    idx = int(path[4:])
    good = idx < 8
    if good:
        hit_count = (
            10 if hat_subband_config is None
            else 13 if hat_ranker_model is None
            else 12
        )
        notes = HITS[:hit_count]+[(38, 7.0)]
    else:
        notes = [(38, 7.0)]
        if hat_subband_config is not None and hat_ranker_model is None:
            notes.append((42, 8.0))
    return make_midi(notes), {}


class Cut29Tests(unittest.TestCase):
    def test_metadata_selection_is_frozen_and_order_independent(self):
        rows = source_rows()
        a = choose_metadata_partition(rows)
        b = choose_metadata_partition(list(reversed(rows)))
        for key in ("fit", "small", "holdout"):
            self.assertEqual([x["id"] for x in a[key]],
                             [x["id"] for x in b[key]])
        self.assertEqual(len(a["fit"]), FIT_SONGS)
        self.assertEqual(len(a["small"]), SMALL_SONGS)
        self.assertEqual(len(a["holdout"]), GROUP_HOLDOUT_SONGS)
        self.assertEqual(len(a["heldout_drummers"]), 2)
        self.assertEqual(len(study_digest()), 64)

    def test_train_only_never_borrows_validation_or_test(self):
        rows = source_rows()
        rows.append({**rows[0], "id": "heldout/test1", "split": "test"})
        rows.append({**rows[1], "id": "heldout/validation1", "split": "validation"})
        plan = choose_metadata_partition(rows)
        for key in ("fit", "small", "holdout"):
            self.assertTrue(all(x["split"] == "train" for x in plan[key]))
        with self.assertRaisesRegex(ValueError, "multiple upstream splits"):
            choose_metadata_partition([rows[0], {**rows[0], "split": "test"}])

    def test_heldout_drummer_never_enters_fit(self):
        plan, _, _, _ = setup()
        fit_d = {x["drummer"] for x in plan["fit"]}
        test_d = {x["drummer"] for x in plan["holdout"]}
        self.assertFalse(fit_d & test_d)
        self.assertTrue({x["id"] for x in plan["small"]}.issubset(
            {x["id"] for x in plan["fit"]}
        ))

    def test_rejects_insufficient_metadata_instead_of_reusing_validation(self):
        rows = source_rows()[:20]
        with self.assertRaisesRegex(ValueError, "No drummer-disjoint"):
            choose_metadata_partition(rows)

    def test_two_models_evaluated_on_identical_train_internal_holdout(self):
        plan, rows, small, full = setup()
        result = compare_models(rows, plan, small, full, transcriber=predict)
        self.assertTrue(result["not_an_official_validation_result"])
        self.assertEqual(result["holdout"]["source_songs"], 24)
        self.assertEqual(result["holdout"]["reference_gm42"], 280)
        self.assertEqual(set(result["score_by_arm"]), {
            "baseline", "raw_subband", "small_24_ranker", "expanded_72_ranker",
        })
        self.assertTrue(result["decision"]["production_dsp_unchanged"])
        self.assertTrue(result["decision"]["official_validation_and_test_not_scored"])

    def test_rejects_drummer_leakage_before_scoring(self):
        plan, rows, small, full = setup()
        plan["holdout"][0]["drummer"] = plan["fit"][0]["drummer"]
        with self.assertRaisesRegex(ValueError, "drummer leakage"):
            compare_models(rows, plan, small, full, transcriber=predict)

    def test_wrong_holdout_id_or_order_fails_closed(self):
        plan, rows, small, full = setup()
        rows[0]["song_id"] = "different_song"
        with self.assertRaisesRegex(ValueError, "holdout data changed"):
            compare_models(rows, plan, small, full, transcriber=predict)

    def test_bad_protocol_or_split_fails_closed(self):
        plan, rows, small, full = setup()
        plan["protocol_digest"] = "0"*64
        with self.assertRaisesRegex(ValueError, "protocol"):
            compare_models(rows, plan, small, full, transcriber=predict)
        plan, rows, small, full = setup()
        plan["upstream_split"] = "validation"
        with self.assertRaisesRegex(ValueError, "original E-GMD TRAIN"):
            compare_models(rows, plan, small, full, transcriber=predict)

    def test_ranker_must_only_filter_new_candidates(self):
        plan, rows, small, full = setup()
        def fake_extra(path, *, hat_subband_config, hat_ranker_model):
            obj, _ = predict(path, hat_subband_config=hat_subband_config,
                             hat_ranker_model=hat_ranker_model)
            if hat_ranker_model is full:
                obj.instruments[0].notes.append(pretty_midi.Note(
                    pitch=42, velocity=80, start=8.6, end=8.7
                ))
            return obj, {}
        with self.assertRaisesRegex(ValueError, "may only filter"):
            compare_models(rows, plan, small, full, transcriber=fake_extra)

    def test_without_hat_negative_control_cannot_pass_quality_gates(self):
        plan, rows, small, full = setup()
        for r in rows:
            r["truth"] = make_midi(HITS+[(38, 7.0)])
        result = compare_models(rows, plan, small, full, transcriber=predict)
        self.assertIn(
            "insufficient_true_hats_or_negative_control_tracks",
            result["incremental"]["expanded_72_ranker"]["blocked_by"],
        )


if __name__ == "__main__":
    unittest.main()
