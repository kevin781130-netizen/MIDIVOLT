"""Validation-only hat recall: old DSP unchanged, no Test tuning, fail-closed rights."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pretty_midi
from scipy.io import wavfile

from midivolt.drums import HatDetectionConfig, transcribe_drum_wav
from midivolt.hat_validation import (
    PRESETS, _recommend, evaluate_validation_pairs, preset_sha256,
    validate_validation_manifest,
)
from midivolt.compare_drums import evaluate_drums
from test_drums import synthetic_drums


def midi(*events):
    instance = pretty_midi.PrettyMIDI(initial_tempo=128)
    tr = pretty_midi.Instrument(program=0, is_drum=True)
    for p, at in events:
        tr.notes.append(pretty_midi.Note(
            pitch=p, start=at, end=at + 0.09, velocity=90
        ))
    instance.instruments.append(tr)
    return instance


def local_pair(root: Path):
    wav = root / "validation_drums.wav"
    ref = root / "validation_drums.mid"
    synthetic_drums(wav)
    midi((36, 0.25), (42, 0.52), (38, 0.9),
         (36, 1.3), (42, 1.3), (42, 2.1)).write(str(ref))
    return {
        "source_song_id": "validation_drummer/performance1",
        "upstream_split": "validation",
        "audio_domain": "electronic_kit_recording",
        "reference_midi_mapping": "roland_td11_to_gm",
        "audio_path": wav.name,
        "reference_midi_path": ref.name,
        "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
        "midi_sha256": hashlib.sha256(ref.read_bytes()).hexdigest(),
        "rights": {
            "status": "approved", "research_evaluation_allowed": True,
            "audio_license": "synthetic_fixture_owned",
            "midi_license": "synthetic_fixture_owned",
            "evidence_url": "https://example.org/synthetic-test",
            "reviewer": "self-generated test fixture, NOT real E-GMD",
        },
    }


def manifest(root: Path, entries) -> Path:
    path = root / "validation.json"
    path.write_text(json.dumps({
        "schema_version": "1", "dataset": "E-GMD v1.0.0",
        "samples": entries,
    }), encoding="utf-8")
    return path


def score(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * p * r / (p + r) if p + r else 0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 6), "recall": round(r, 6), "f1": round(f1, 6)}


class HatValidationTests(unittest.TestCase):
    def test_default_hat_config_matches_unmodified_dsp(self):
        with tempfile.TemporaryDirectory() as t:
            wav = Path(t) / "drums.wav"
            synthetic_drums(wav)
            a, _ = transcribe_drum_wav(wav)
            b, details = transcribe_drum_wav(wav, hat_config=HatDetectionConfig())
            self.assertEqual(
                [(n.pitch, n.start, n.velocity) for n in a.instruments[0].notes],
                [(n.pitch, n.start, n.velocity) for n in b.instruments[0].notes],
            )
            self.assertEqual(details["counts"], {"kick": 2, "snare": 1, "hat": 3})

    def test_presets_are_frozen_distinct_and_baseline_untouched(self):
        self.assertEqual(tuple(PRESETS), ("baseline", "conservative", "moderate", "aggressive"))
        self.assertEqual(PRESETS["baseline"], HatDetectionConfig())
        self.assertEqual(len(set(PRESETS.values())), len(PRESETS))
        self.assertEqual(len(preset_sha256()), 64)

    def test_invalid_hat_parameter_rejected(self):
        for config in (
            {"peak_fraction_scale": 0.0},
            {"flux_noise_multiplier": float("nan")},
            {"min_high_power_share": 0.95},
            {"min_rms": -1.0},
        ):
            with self.assertRaisesRegex(ValueError, "HatDetectionConfig"):
                HatDetectionConfig(**config)

    def test_test_partition_forbidden_even_when_rights_approved(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            pair = local_pair(root)
            pair["upstream_split"] = "test"
            with self.assertRaisesRegex(ValueError, "TEST/train"):
                validate_validation_manifest(manifest(root, [pair]))

    def test_train_partition_forbidden(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            pair = local_pair(root)
            pair["upstream_split"] = "train"
            with self.assertRaisesRegex(ValueError, "TEST/train"):
                validate_validation_manifest(manifest(root, [pair]))

    def test_pending_rights_block_before_dsp_runs(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            pair = local_pair(root)
            pair["rights"]["status"] = "pending"
            with self.assertRaisesRegex(PermissionError, "rights approval"):
                validate_validation_manifest(manifest(root, [pair]))

    def test_modified_audio_checksum_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            pair = local_pair(root)
            pair["wav_sha256"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                validate_validation_manifest(manifest(root, [pair]))

    def test_modified_midi_checksum_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            pair = local_pair(root)
            pair["midi_sha256"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                validate_validation_manifest(manifest(root, [pair]))

    def test_double_counted_kit_render_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            pair = local_pair(root)
            with self.assertRaisesRegex(ValueError, "Duplicate/missing source song"):
                validate_validation_manifest(manifest(root, [pair, pair]))

    def test_synthetic_audio_validation_pipeline_runs_four_presets(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = validate_validation_manifest(manifest(root, [local_pair(root)]))
            report = evaluate_validation_pairs(records)
            self.assertTrue(report["production_default_unchanged"])
            self.assertTrue(report["heldout_test_scores_unaffected"])
            self.assertEqual(report["evaluation_partition"], "official_upstream_validation_only")
            self.assertEqual(set(report["summary_by_preset"]), set(PRESETS))
            self.assertEqual(report["summary_by_preset"]["baseline"]["closed_hi_hat"]["tp"], 3)
            self.assertEqual(report["summary_by_preset"]["baseline"]["closed_hi_hat"]["fn"], 0)
            self.assertEqual(report["recommendation"]["status"], "insufficient_validation_coverage")
            self.assertEqual(report["negative_control"]["song_count"], 0)
            # Synthetic fixture only; never imply this is an official E-GMD result.

    def test_six_song_no_hat_negative_control_is_not_assumed_safe(self):
        base = midi((42, 0.25), (38, 0.65))
        records = [
            {"song_id": f"validation-{i}", "wav": f"validation-{i}", "truth": base}
            for i in range(6)
        ]
        def mock_transcriber(wav, *, hat_config):
            return midi((42, 0.25), (38, 0.65)), {}
        out = evaluate_validation_pairs(records, transcriber=mock_transcriber)
        self.assertEqual(out["sample_count"], 6)
        self.assertEqual(out["negative_control"]["song_count"], 0)
        self.assertEqual(out["recommendation"]["status"],
                         "needs_no_closed_hat_negative_control")

    def test_negative_control_fails_candidate_with_new_false_hat_notes(self):
        records = [{
            "song_id": "control", "wav": "control",
            "truth": midi((38, 0.25)),
        }]
        ten_hats = [(42, 0.2 + j * 0.13) for j in range(10)]
        for i in range(5):
            records.append({
                "song_id": f"validation-{i}", "wav": f"validation-{i}",
                "truth": midi(*ten_hats),
            })
        def mock_transcriber(wav, *, hat_config):
            if wav == "control":
                if hat_config == PRESETS["baseline"]:
                    return midi(), {}
                return midi((42, 0.65)), {}
            visible = 3 if hat_config == PRESETS["baseline"] else 7
            return midi(*ten_hats[:visible]), {}
        out = evaluate_validation_pairs(records, transcriber=mock_transcriber)
        self.assertEqual(out["negative_control"]["song_count"], 1)
        self.assertEqual(out["negative_control"]["false_gm42_predictions_by_preset"]["baseline"], 0)
        self.assertEqual(out["negative_control"]["false_gm42_predictions_by_preset"]["conservative"], 1)
        self.assertEqual(out["recommendation"]["status"],
                         "negative_control_failure_retain_baseline")

    def test_precision_gate_prevents_false_positives_from_winning(self):
        base = {"closed_hi_hat": score(3, 0, 7), "total": score(10, 2, 10)}
        conservative = {"closed_hi_hat": score(5, 0, 5), "total": score(12, 2, 8)}
        noisy = {"closed_hi_hat": score(9, 10, 1), "total": score(16, 15, 4)}
        values = {
            "baseline": base,
            "conservative": conservative,
            "moderate": noisy,
            "aggressive": noisy,
        }
        selected = _recommend(values)
        self.assertEqual(selected["status"], "validation_candidate_only")
        self.assertEqual(selected["preset"], "conservative")
        self.assertTrue(any("hat_precision_guard" in c["blocked_by"]
                            for c in selected["candidates"] if c["preset"] == "moderate"))

    def test_no_improvement_preserves_baseline(self):
        baseline = {"closed_hi_hat": score(3, 0, 7), "total": score(10, 2, 10)}
        data = {name: baseline for name in PRESETS}
        result = _recommend(data)
        self.assertEqual(result["status"], "retain_baseline")

    def test_empty_manifest_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            with self.assertRaisesRegex(ValueError, "at least one"):
                validate_validation_manifest(manifest(root, []))


if __name__ == "__main__":
    unittest.main()
