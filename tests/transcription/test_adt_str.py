"""Experimental ADT_STR adapter tests: no checkpoints or PyTorch are installed."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pretty_midi

from midivolt.adt_str import transcribe_adt_str
from midivolt.compare_drums import compare, evaluate_drums
from midivolt.transcribe import transcribe_stems


def midi(*events, is_drum=True):
    output = pretty_midi.PrettyMIDI(initial_tempo=138)
    track = pretty_midi.Instrument(program=0, is_drum=is_drum)
    for pitch, onset in events:
        track.notes.append(pretty_midi.Note(
            pitch=pitch, velocity=100, start=onset, end=onset + 0.1
        ))
    output.instruments.append(track)
    return output


class ModelBridgeTests(unittest.TestCase):
    def test_model_cannot_run_without_explicit_research_flag(self):
        with self.assertRaisesRegex(PermissionError, "research-only"):
            transcribe_adt_str(
                Path("missing.wav"), tempo=138,
                repo_root=Path("missing"), checkpoint=Path("missing"),
            )

    def test_model_must_exist_locally_and_never_auto_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Drums.wav").write_bytes(b"RIFF")
            with self.assertRaisesRegex(ValueError, "inference.py"):
                transcribe_adt_str(
                    root / "Drums.wav", tempo=138, research_only=True,
                    repo_root=root, checkpoint=root,
                )

    def test_mocked_upstream_inference_preserves_notes_and_gm_percussion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = root / "adt"
            checkpoint = root / "weights"
            upstream.mkdir()
            checkpoint.mkdir()
            (upstream / "inference.py").write_text("# trusted local script\n", encoding="utf-8")
            audio = root / "Drums.wav"
            audio.write_bytes(b"RIFF")

            def mock_runner(command, *, cwd, check, capture_output, text, timeout):
                self.assertEqual(command[1], str(upstream / "inference.py"))
                self.assertEqual(command[command.index("--checkpoint") + 1], str(checkpoint))
                output_folder = Path(command[command.index("--output_path") + 1])
                midi((36, 0.25), (38, 0.90), (42, 1.30)).write(
                    str(output_folder / "Drums.mid")
                )
                return subprocess.CompletedProcess(command, 0, "ok", "")

            output, info = transcribe_adt_str(
                audio, tempo=138, research_only=True, repo_root=upstream,
                checkpoint=checkpoint, runner=mock_runner,
            )
            self.assertEqual(info["detected"], 3)
            self.assertEqual(info["license_gate"], "research_only")
            self.assertEqual(info["gm_pitch_histogram"], {"36": 1, "38": 1, "42": 1})
            self.assertTrue(output.instruments[0].is_drum)
            self.assertAlmostEqual(output.instruments[0].notes[0].start, 0.25, places=3)

    def test_bad_upstream_midi_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = root / "adt"
            upstream.mkdir()
            checkpoint = root / "weights"
            checkpoint.mkdir()
            (upstream / "inference.py").write_text("# mocked\n", encoding="utf-8")
            audio = root / "Drums.wav"
            audio.write_bytes(b"RIFF")

            def mock_runner(command, **kwargs):
                output_folder = Path(command[-1])
                midi((60, 0.25), is_drum=False).write(str(output_folder / "Drums.mid"))
                return subprocess.CompletedProcess(command, 0, "ok", "")

            with self.assertRaisesRegex(RuntimeError, "drum-only"):
                transcribe_adt_str(
                    audio, tempo=138, research_only=True,
                    repo_root=upstream, checkpoint=checkpoint, runner=mock_runner,
                )

    def test_main_stem_pipeline_rejects_unreviewed_adt_by_default(self):
        with self.assertRaisesRegex(PermissionError, "research-only"):
            transcribe_stems(
                Path("missing"), Path("output"),
                drum_engine="adt-str",
            )

    def test_integration_routes_research_model_without_pitched_predictor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Drums.wav").write_bytes(b"RIFF")
            expected = midi((36, 0.25), (42, 1.30))

            with patch("midivolt.adt_str.transcribe_adt_str",
                       return_value=(expected, {
                           "engine": "adt_str", "license_gate": "research_only",
                       })) as stub:
                report = transcribe_stems(
                    root / "Drums.wav", root / "out",
                    stem_type="drums", drum_engine="adt-str",
                    research_only=True, adt_root=root, adt_checkpoint=root,
                )
            stub.assert_called_once()
            self.assertEqual(report["engine"], "adt_str")
            self.assertEqual(report["tracks"][0]["engine"], "adt_str")
            merged = pretty_midi.PrettyMIDI(str(root / "out" / "MIDIVOLT_multitrack.mid"))
            self.assertEqual(len(merged.instruments), 1)
            self.assertTrue(merged.instruments[0].is_drum)
            self.assertEqual(len(merged.instruments[0].notes), 2)


class ComparisonTests(unittest.TestCase):
    def test_per_pitch_f1_with_errors_and_simultaneous_hits(self):
        truth = midi((36, 0.25), (42, 0.25), (38, 0.90))
        estimated = midi((36, 0.27), (42, 0.26), (36, 0.28), (49, 1.20))
        result = evaluate_drums(truth, estimated)
        self.assertEqual(result["micro"]["tp"], 2)
        self.assertEqual(result["micro"]["fp"], 2)
        self.assertEqual(result["micro"]["fn"], 1)
        self.assertEqual(result["per_gm_pitch"]["36"]["tp"], 1)
        self.assertEqual(result["per_gm_pitch"]["42"]["tp"], 1)
        self.assertEqual(result["per_gm_pitch"]["38"]["fn"], 1)

    def test_research_candidate_better_only_on_this_clip(self):
        reference = midi((36, 0.25), (42, 0.25), (38, 0.90))
        dsp = midi((36, 0.25), (42, 0.25))
        ai = midi((36, 0.25), (42, 0.25), (38, 0.90))
        result = compare(reference, dsp, ai)
        self.assertEqual(result["comparison"]["higher_f1_on_this_clip"], "adt_str")
        self.assertEqual(result["adt_str"]["micro"]["f1"], 1.0)

    def test_drum_evaluator_rejects_pitched_instrument(self):
        with self.assertRaisesRegex(ValueError, "percussion"):
            evaluate_drums(midi((36, 0.25)), midi((36, 0.25), is_drum=False))

    def test_overlapping_duplicate_drums_not_double_counted(self):
        result = evaluate_drums(
            midi((36, 0.25)),
            midi((36, 0.25), (36, 0.26)),
        )
        self.assertEqual(result["micro"]["tp"], 1)
        self.assertEqual(result["micro"]["fp"], 1)


if __name__ == "__main__":
    unittest.main()
