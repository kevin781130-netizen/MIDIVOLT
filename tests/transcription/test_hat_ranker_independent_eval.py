"""Cut28 no-net independent TRAIN/Validation and candidate-ranker regressions.

All examples are deliberately synthetic. Do not report their F1 as actual
E-GMD measurements or license-validation evidence.
"""
from __future__ import annotations

import json
import unittest

import pretty_midi

from midivolt.hat_candidate_ranker import fit_ranker
from midivolt.hat_ranker_independent_eval import (
    REVISION, PREVIOUS_VAL_IDS, CUT26_SOURCE_SONG_IDS,
    CUT26_PLAN_SHA256, TRAIN_COUNT, VALIDATION_COUNT, protocol_digest,
    evaluate_unseen,
)
from scripts.egmd_hat_ranker_real import (
    select_train_metadata, _original_plan_ok,
)


def midi(*notes):
    m = pretty_midi.PrettyMIDI(initial_tempo=120)
    track = pretty_midi.Instrument(program=0, is_drum=True)
    for p, t in notes:
        track.notes.append(pretty_midi.Note(pitch=p, velocity=80, start=t, end=t+.1))
    m.instruments.append(track)
    return m


TRUTH_HATS = [(42, .2+i*.18) for i in range(40)]


def fitted():
    examples = []
    for s in range(5):
        for i in range(20):
            label = i % 2
            examples.append({
                "split": "train", "source_song_id": f"trainer{s}",
                "label": label,
                "features": {
                    "high_to_mid": 4 if label else .5,
                    "noise_flatness": .9 if label else .1,
                    "two_band_balance": .8 if label else .12,
                    "attack_to_prior": 6 if label else 1,
                    "tail_to_attack": .10 if label else 1.4,
                },
            })
    return fit_ranker(examples, manifest_sha256="d"*64)


def dataset():
    model = fitted()
    train_ids = [f"train/performance{i}" for i in range(TRAIN_COUNT)]
    records, selected = [], []
    for i in range(VALIDATION_COUNT):
        id_ = f"never-seen-val-song{i}"
        records.append({
            "song_id": id_, "wav": id_,
            "truth": midi(*TRUTH_HATS, (38, 8.6)) if i < 3 else midi((38, 8.6)),
        })
        selected.append({
            "id": id_, "split": "validation", "drummer": f"drummer{i%4}",
            "kit_name": "Acoustic Kit",
        })
    plan = {
        "revision": REVISION, "protocol_digest": protocol_digest(),
        "dataset": "E-GMD v1.0.0", "upstream_split": "validation",
        "excluded_previous_val_ids": sorted(PREVIOUS_VAL_IDS),
        "selected": selected,
        "train_source_song_ids": train_ids,
        "train_source_count": TRAIN_COUNT,
        "train_contributing_songs": model.source_songs,
        "train_manifest_sha256": model.training_manifest_sha256,
    }
    return records, plan, model


def fake_transcribe(wav, *, hat_subband_config, hat_ranker_model):
    is_positive = int(wav.split("song")[-1]) < 3
    if is_positive:
        count = 10 if hat_subband_config is None else 13
        extra = TRUTH_HATS[:count]
    else:
        extra = []
        if hat_subband_config is not None and hat_ranker_model is None:
            extra = [(42, 8.9)]
    return midi(*extra, (38, 8.6)), {}


class TrainingValidationTests(unittest.TestCase):
    def test_cut26_source_ids_and_full_60_exclusion_frozen(self):
        self.assertEqual(len(CUT26_SOURCE_SONG_IDS), 24)
        self.assertEqual(len(PREVIOUS_VAL_IDS), 60)
        self.assertEqual(len(protocol_digest()), 64)
        self.assertEqual(len(CUT26_PLAN_SHA256), 64)

    def test_reject_any_new_validation_source_which_was_seen(self):
        records, plan, model = dataset()
        old = sorted(PREVIOUS_VAL_IDS)[0]
        records[0]["song_id"] = old
        plan["selected"][0]["id"] = old
        with self.assertRaisesRegex(ValueError, "Old/duplicated"):
            evaluate_unseen(records, plan, model, transcriber=fake_transcribe)

    def test_valid_12_new_validation_songs_score_three_arms(self):
        records, plan, model = dataset()
        report = evaluate_unseen(records, plan, model, transcriber=fake_transcribe)
        self.assertEqual(report["cohort"]["val_songs"], 12)
        self.assertEqual(report["cohort"]["excluded_old_val_songs"], 60)
        self.assertEqual(report["cohort"]["reference_gm42"], 120)
        self.assertEqual(set(report["scores"]), {"baseline", "raw_subband", "trained_ranker"})
        self.assertGreater(report["new_event_metrics"]["ranker_marginal_precision"], .60)
        self.assertEqual(report["decision"]["status"], "research_candidate_only_NOT_beta")
        self.assertFalse(report["decision"]["official_test_scored"])
        self.assertFalse(report["commercial_distribution_approved"])

    def test_false_hat_in_zero_reference_control_blocks(self):
        records, plan, model = dataset()
        def noisy(wav, *, hat_subband_config, hat_ranker_model):
            pred, diag = fake_transcribe(
                wav, hat_subband_config=hat_subband_config, hat_ranker_model=hat_ranker_model
            )
            if wav.endswith("song5") and hat_ranker_model is not None:
                # Candidate is already proposed by raw; ranker has failed to reject it.
                pred.instruments[0].notes.append(
                    pretty_midi.Note(pitch=42, velocity=80, start=8.9, end=9.0)
                )
            return pred, diag
        report = evaluate_unseen(records, plan, model, transcriber=noisy)
        self.assertEqual(report["decision"]["status"], "retain_production_baseline")
        self.assertIn("new_false_hat_on_zero_reference_control", report["decision"]["blocked_by"])

    def test_filter_may_not_add_nonraw_predictions(self):
        records, plan, model = dataset()
        def bad(wav, *, hat_subband_config, hat_ranker_model):
            p, detail = fake_transcribe(
                wav, hat_subband_config=hat_subband_config, hat_ranker_model=hat_ranker_model
            )
            if hat_ranker_model:
                p.instruments[0].notes.append(
                    pretty_midi.Note(pitch=42, velocity=80, start=19.0, end=19.1)
                )
            return p, detail
        with self.assertRaisesRegex(ValueError, "only raw new"):
            evaluate_unseen(records, plan, model, transcriber=bad)

    def test_reject_non_train_manifest_hash_model(self):
        records, plan, model = dataset()
        plan["train_manifest_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "Train model"):
            evaluate_unseen(records, plan, model, transcriber=fake_transcribe)

    def test_reject_test_partition_and_forged_protocol(self):
        records, plan, model = dataset()
        plan["selected"][0]["split"] = "test"
        with self.assertRaisesRegex(ValueError, "official Validation"):
            evaluate_unseen(records, plan, model, transcriber=fake_transcribe)
        records, plan, model = dataset()
        plan["protocol_digest"] = "0"*64
        with self.assertRaisesRegex(ValueError, "protocol"):
            evaluate_unseen(records, plan, model, transcriber=fake_transcribe)

    def test_too_few_validation_songs_rejected(self):
        records, plan, model = dataset()
        del records[-1]
        del plan["selected"][-1]
        with self.assertRaisesRegex(ValueError, "identities/count"):
            evaluate_unseen(records, plan, model, transcriber=fake_transcribe)

    def test_train_selection_uses_only_train_metadata_not_other_splits(self):
        rows = []
        for i in range(120):
            kind = "beat" if i%2 else "fill"
            rows.append({
                "id": f"train-song{i}", "split": "train",
                "drummer": f"drummer{i%6}",
                "style": f"genre{i%4}/rhythm",
                "beat_type": kind, "duration": str(3+i%50),
                "kit_name": "Acoustic Kit",
                "audio_filename": f"train-song{i}.wav",
            })
        for j in range(25):
            rows.append({
                "id": f"val-song{j}", "split": "validation", "drummer": "x",
                "style": "rock/groove", "beat_type": "beat",
                "duration": "15", "kit_name": "Acoustic Kit",
                "audio_filename": f"val-song{j}.wav",
            })
        chosen = select_train_metadata(rows)
        reversed_result = select_train_metadata(list(reversed(rows)))
        self.assertEqual([x["id"] for x in chosen],
                         [x["id"] for x in reversed_result])
        self.assertEqual(len(chosen), 24)
        self.assertEqual(sum(x["beat_type"] == "beat" for x in chosen), 16)
        self.assertEqual(sum(x["beat_type"] == "fill" for x in chosen), 8)
        self.assertTrue(all(x["split"]=="train" for x in chosen))

    def test_previously_scored_cut26_plan_requires_actual_hash(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/"plan.json"
            p.write_text('{"dataset":"E-GMD v1.0.0","selected":[]}')
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                _original_plan_ok(p)


if __name__ == "__main__":
    unittest.main()
