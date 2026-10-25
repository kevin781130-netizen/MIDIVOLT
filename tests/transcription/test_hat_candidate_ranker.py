"""TRAIN-only ranker: deterministic NumPy fit, strict data provenance.

All examples are synthetic feature dictionaries, NOT official data scores.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pretty_midi

from midivolt.hat_candidate_ranker import (
    DECISION_THRESHOLD, FEATURES, SCHEMA, HatRankerModel, fit_ranker,
    vectorize, json_sha256,
)
from midivolt.hat_ranker_training import (
    label_new_candidates, read_train_manifest,
)

PINNED = "a" * 64


def events(*onsets):
    song = pretty_midi.PrettyMIDI(initial_tempo=120)
    drum = pretty_midi.Instrument(program=0, is_drum=True)
    for onset in onsets:
        drum.notes.append(
            pretty_midi.Note(
                pitch=42, velocity=90, start=onset, end=onset+.1
            )
        )
    song.instruments.append(drum)
    return song


def examples():
    output = []
    for song in range(6):
        for j in range(28):
            label = int(j % 2 == 0)
            features = {
                "high_to_mid": 4.0 if label else .5,
                "noise_flatness": .95 if label else .1,
                "two_band_balance": .9 if label else .07,
                "attack_to_prior": 8 if label else 1.1,
                "tail_to_attack": .05 if label else 2.0,
            }
            output.append({
                "split": "train",
                "source_song_id": f"train/drummer{song}/clip{song}",
                "label": label, "features": features,
            })
    return output


def private_manifest(folder, split="train"):
    root = Path(folder)
    samples = []
    for n in range(4):
        wav = root / f"record_{n}.wav"
        mid = root / f"record_{n}.mid"
        wav.write_bytes(b"dummy PCM independent test " + str(n).encode())
        mid.write_bytes(b"dummy MIDI independent test " + str(n).encode())
        samples.append({
            "source_song_id": f"train/performance/{n}",
            "upstream_split": split,
            "audio_path": wav.name, "reference_midi_path": mid.name,
            "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
            "midi_sha256": hashlib.sha256(mid.read_bytes()).hexdigest(),
            "reference_midi_mapping": "roland_td11_to_gm",
            "rights": {
                "status": "approved",
                "research_evaluation_allowed": True,
                "audio_license": "self-generated synthetic fixture",
                "midi_license": "self-generated synthetic fixture",
                "evidence_url": "https://example.org/synthetic-fixture",
            },
        })
    p = root / "train.json"
    p.write_text(json.dumps({
        "dataset": "E-GMD v1.0.0", "split": split, "schema_version": "1",
        "samples": samples,
    }), encoding="utf-8")
    return p


class TrainRankerTests(unittest.TestCase):
    def test_feature_order_fixed_and_transform_finite(self):
        value = examples()[0]["features"]
        v = vectorize(value)
        self.assertEqual(len(v), len(FEATURES))
        self.assertAlmostEqual(v[0], np.log1p(value["high_to_mid"]))

    def test_deterministic_train_only_fit_and_separated_synthetic_scores(self):
        rows = examples()
        a = fit_ranker(rows, manifest_sha256=PINNED)
        b = fit_ranker(rows, manifest_sha256=PINNED)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.decision_threshold, DECISION_THRESHOLD)
        self.assertEqual(a.training_split, "train")
        self.assertGreater(a.probability(rows[0]["features"]), .8)
        self.assertLess(a.probability(rows[1]["features"]), .2)
        self.assertGreater(a.positive_examples, 10)

    def test_model_roundtrip_and_checksum_stability(self):
        model = fit_ranker(examples(), manifest_sha256=PINNED)
        parsed = HatRankerModel.from_dict(json.loads(json.dumps(model.to_dict())))
        self.assertEqual(parsed.to_dict(), model.to_dict())
        self.assertEqual(json_sha256(parsed.to_dict()), json_sha256(model.to_dict()))
        self.assertFalse(parsed.to_dict()["commercial_distribution_approved"])

    def test_training_on_validation_or_test_forbidden(self):
        for split in ("validation", "test"):
            rows = examples()
            rows[0]["split"] = split
            with self.assertRaisesRegex(ValueError, "Validation/Test"):
                fit_ranker(rows, manifest_sha256=PINNED)

    def test_training_cannot_run_from_one_song_or_one_class(self):
        rows = examples()
        for rec in rows:
            rec["source_song_id"] = "same/performance"
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            fit_ranker(rows, manifest_sha256=PINNED)
        rows = examples()
        for rec in rows:
            rec["label"] = 0
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            fit_ranker(rows, manifest_sha256=PINNED)

    def test_bad_input_and_feature_extraction_rejected(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            vectorize({"high_to_mid": 2.0})
        vec = dict(examples()[0]["features"])
        vec["high_to_mid"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            vectorize(vec)

    def test_modified_threshold_model_rejected(self):
        obj = fit_ranker(examples(), manifest_sha256=PINNED).to_dict()
        obj["decision_threshold"] = .55
        with self.assertRaisesRegex(ValueError, "frozen"):
            HatRankerModel.from_dict(obj)

    def test_changed_order_or_schema_rejected(self):
        obj = fit_ranker(examples(), manifest_sha256=PINNED).to_dict()
        obj["features"] = list(reversed(obj["features"]))
        with self.assertRaisesRegex(ValueError, "features"):
            HatRankerModel.from_dict(obj)

    def test_cannot_claim_commercial_redistribution_approval(self):
        obj = fit_ranker(examples(), manifest_sha256=PINNED).to_dict()
        obj["commercial_distribution_approved"] = True
        with self.assertRaisesRegex(ValueError, "distribution"):
            HatRankerModel.from_dict(obj)

    def test_reference_already_matched_by_baseline_not_labelled_true_again(self):
        truth = events(.2)
        baseline = events(.2)
        proposed = events(.2, .23)
        labelled = label_new_candidates(truth, baseline, proposed)
        self.assertEqual(len(labelled), 1)
        self.assertEqual(labelled[0]["label"], 0)

    def test_exact_additional_matched_hat_labelled_true_once(self):
        truth = events(.2, .6)
        baseline = events(.2)
        proposed = events(.2, .6, .625)
        labels = label_new_candidates(truth, baseline, proposed)
        self.assertEqual([x["label"] for x in labels], [1, 0])

    def test_missing_original_prediction_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "removed existing"):
            label_new_candidates(events(.2), events(.2), events())

    def test_train_manifest_requires_exact_bytes_and_rights(self):
        with tempfile.TemporaryDirectory() as d:
            path = private_manifest(d)
            records, sha = read_train_manifest(path)
            self.assertEqual(len(records), 4)
            self.assertEqual(len(sha), 64)
            (Path(d)/"record_1.wav").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                read_train_manifest(path)

    def test_train_manifest_rejects_train_flag_lie(self):
        with tempfile.TemporaryDirectory() as d:
            path = private_manifest(d)
            obj = json.loads(path.read_text())
            obj["samples"][0]["upstream_split"] = "test"
            path.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, "Non-TRAIN"):
                read_train_manifest(path)

    def test_train_manifest_rejects_uncleared_rights(self):
        with tempfile.TemporaryDirectory() as d:
            path = private_manifest(d)
            obj = json.loads(path.read_text())
            obj["samples"][2]["rights"]["status"] = "pending"
            path.write_text(json.dumps(obj))
            with self.assertRaisesRegex(PermissionError, "rights"):
                read_train_manifest(path)

    def test_model_not_accepted_as_drum_option_without_subband(self):
        from midivolt.drums import transcribe_drum_wav
        model = fit_ranker(examples(), manifest_sha256=PINNED)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"silent.wav"
            from scipy.io import wavfile
            wavfile.write(p, 22050, np.zeros(22050,dtype=np.int16))
            with self.assertRaisesRegex(ValueError, "requires opt-in"):
                transcribe_drum_wav(p, hat_ranker_model=model)

    def test_score_stft_is_finite_on_synthetic_noise_hat(self):
        from midivolt.hat_candidate_ranker import score_onset
        model = fit_ranker(examples(), manifest_sha256=PINNED)
        hz = np.arange(0,11050,50)
        mag = np.full((len(hz),200),.001,dtype=float)
        mag[(hz>=5200)&(hz<10500),70:73] = 2
        result = score_onset(mag,hz,70,hop_seconds=.01,model=model)
        self.assertIsNotNone(result["ranker_probability"])
        self.assertIn(result["accepted"], (True,False))
        self.assertEqual(result["ranker_schema"], SCHEMA)


if __name__ == "__main__":
    unittest.main()
