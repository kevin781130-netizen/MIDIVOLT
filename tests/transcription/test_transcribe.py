"""Tests for the first pitched-stem Basic Pitch integration; no model download."""
from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

import pretty_midi

from midivolt.transcribe import detect_kind, discover, transcribe_stems


def wav(path: Path) -> None:
    """Create a valid short PCM WAV; mock inference tests MIDI IO and routing."""
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        stream.writeframes(b"\x00\x00" * 2205)


def fake_predict(path: Path, tempo: float, onset: float, frame: float, minimum_ms: float):
    result = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    instrument = pretty_midi.Instrument(program=0)
    # WAV leading silence is represented as absolute seconds in the returned note.
    start = 1.25 if "Bass" in path.name else 3.5
    instrument.notes.append(pretty_midi.Note(velocity=97, pitch=48, start=start, end=start + 0.5))
    instrument.pitch_bends.append(pretty_midi.PitchBend(pitch=200, time=start + 0.1))
    instrument.control_changes.append(pretty_midi.ControlChange(number=64, value=127, time=start + 0.2))
    result.instruments.append(instrument)
    return result


class StemTranscriptionTests(unittest.TestCase):
    def test_detect_filename_in_multiple_languages(self):
        self.assertEqual(detect_kind("A Song (Bass).wav"), "bass")
        self.assertEqual(detect_kind("S01 (Other).wav"), "other")
        self.assertEqual(detect_kind("ギター.wav"), "guitar")
        self.assertEqual(detect_kind("人聲.wav"), "vocal")
        self.assertEqual(detect_kind("鼓.wav"), "drums")
        self.assertIsNone(detect_kind("guitar_bass.wav"))
        self.assertIsNone(detect_kind("mystery.wav"))

    def test_batch_separate_and_merged_tracks_keep_absolute_seconds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src, dst = root / "stems", root / "midi"
            src.mkdir()
            for name in ("Song (Bass).wav", "Song (Guitar).wav", "Song (Drums).wav", "Song (Unknown).wav"):
                wav(src / name)

            report = transcribe_stems(src, dst, tempo=138.0, predictor=fake_predict)
            self.assertEqual(len(report["tracks"]), 2)
            self.assertEqual({x["reason"] for x in report["skipped"]}, {
                "drums_need_dedicated_engine",
                "unrecognized_or_ambiguous_stem_name",
            })
            bass = pretty_midi.PrettyMIDI(str(dst / "Song (Bass).mid"))
            guitar = pretty_midi.PrettyMIDI(str(dst / "Song (Guitar).mid"))
            multi = pretty_midi.PrettyMIDI(str(dst / "MIDIVOLT_multitrack.mid"))
            self.assertEqual(len(bass.instruments), 1)
            self.assertEqual(len(guitar.instruments), 1)
            self.assertEqual(len(multi.instruments), 2)
            self.assertEqual([x.name for x in multi.instruments], [
                "bass | Song (Bass)", "guitar | Song (Guitar)",
            ])
            self.assertEqual([x.program for x in multi.instruments], [33, 27])
            self.assertAlmostEqual(bass.instruments[0].notes[0].start, 1.25, places=3)
            self.assertAlmostEqual(guitar.instruments[0].notes[0].start, 3.5, places=3)
            self.assertAlmostEqual(multi.instruments[0].notes[0].end, 1.75, places=3)
            self.assertEqual(len(multi.instruments[0].pitch_bends), 1)
            self.assertEqual(len(multi.instruments[0].control_changes), 1)
            self.assertTrue((dst / "MIDIVOLT_report.json").is_file())

    def test_drums_only_fail_instead_of_mislabeling_pitches(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = Path(folder) / "stems", Path(folder) / "out"
            src.mkdir()
            wav(src / "Drums.wav")
            with self.assertRaisesRegex(ValueError, "dedicated engine"):
                transcribe_stems(src, dst, predictor=fake_predict)

    def test_refuses_overwrite_before_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = Path(folder) / "stems", Path(folder) / "out"
            src.mkdir()
            wav(src / "Bass.wav")
            transcribe_stems(src, dst, predictor=fake_predict)
            calls = []
            def spy(*args):
                calls.append(args)
                return fake_predict(*args)
            with self.assertRaises(FileExistsError):
                transcribe_stems(src, dst, predictor=spy)
            self.assertEqual(calls, [])

    def test_single_file_type_override(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = Path(folder) / "some-song.wav", Path(folder) / "output"
            wav(src)
            result = transcribe_stems(src, dst, stem_type="keys", predictor=fake_predict)
            self.assertEqual(result["tracks"][0]["stem_type"], "keys")
            midi = pretty_midi.PrettyMIDI(str(dst / "some-song.mid"))
            self.assertEqual(midi.instruments[0].program, 0)

    def test_directory_rejects_global_type_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wav(root / "Bass.wav")
            with self.assertRaisesRegex(ValueError, "single WAV"):
                discover(root, forced_type="bass")

    def test_invalid_tempo_fails_early(self):
        with self.assertRaisesRegex(ValueError, "tempo"):
            transcribe_stems(Path("irrelevant"), Path("out"), tempo=0, predictor=fake_predict)

    def test_reserved_output_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = Path(folder) / "MIDIVOLT_multitrack.wav", Path(folder) / "out"
            wav(src)
            with self.assertRaisesRegex(ValueError, "reserved output"):
                transcribe_stems(src, dst, stem_type="keys", predictor=fake_predict)


if __name__ == "__main__":
    unittest.main()
