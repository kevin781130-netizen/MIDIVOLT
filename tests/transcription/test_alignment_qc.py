"""WAV/MIDI alignment diagnostics smoke; no dataset or model downloads."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pretty_midi
from scipy.io import wavfile

from midivolt.alignment_qc import inspect_alignment


def alignment_fixture(directory: Path, lag_ms: float):
    sr = 22050
    length = 2.1
    wave = np.zeros(round(sr * length))
    reference = pretty_midi.PrettyMIDI()
    notes = pretty_midi.Instrument(program=0, is_drum=True)
    starts = [0.22, 0.42, 0.62, 0.82, 1.02, 1.22, 1.42, 1.62]
    for onset in starts:
        notes.notes.append(pretty_midi.Note(
            pitch=38, velocity=85, start=onset, end=onset+0.10,
        ))
        source = onset + lag_ms / 1000
        offset = round(source * sr)
        n = round(0.045 * sr)
        seconds = np.arange(n) / sr
        attack = np.minimum(1, seconds / 0.003)
        burst = np.sin(2*np.pi*310*seconds) * np.exp(-seconds / 0.014) * attack
        wave[offset:offset+n] += burst
    reference.instruments.append(notes)
    out = directory / "reference_drums.wav"
    wavfile.write(str(out), sr, np.round(wave * 18000).astype(np.int16))
    return out, reference


class AlignmentQualityTests(unittest.TestCase):
    def test_no_artificial_shift_and_no_reference_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            path, midi = alignment_fixture(Path(d), 0)
            start = midi.instruments[0].notes[0].start
            result = inspect_alignment(path, midi)
            self.assertEqual(result["status"], "no_large_offset_detected")
            self.assertLess(abs(result["median_audio_minus_midi_ms"]), 12)
            self.assertEqual(midi.instruments[0].notes[0].start, start)

    def test_flags_uniform_large_wav_delay_without_correcting_it(self):
        with tempfile.TemporaryDirectory() as d:
            path, midi = alignment_fixture(Path(d), 42)
            result = inspect_alignment(path, midi)
            self.assertEqual(result["status"], "suspected_offset", result)
            self.assertLess(abs(result["median_audio_minus_midi_ms"] - 42), 12)
            self.assertEqual(midi.instruments[0].notes[0].start, 0.22)

    def test_empty_midi_returns_insufficient_events(self):
        with tempfile.TemporaryDirectory() as d:
            path, _ = alignment_fixture(Path(d), 0)
            blank = pretty_midi.PrettyMIDI()
            blank.instruments.append(pretty_midi.Instrument(program=0, is_drum=True))
            result = inspect_alignment(path, blank)
            self.assertEqual(result["status"], "insufficient_events")

    def test_silent_wav_does_not_claim_timing_accuracy(self):
        with tempfile.TemporaryDirectory() as d:
            path, midi = alignment_fixture(Path(d), 0)
            wavfile.write(str(path), 22050, np.zeros(22050*2, dtype=np.int16))
            result = inspect_alignment(path, midi)
            self.assertEqual(result["status"], "insufficient_audio_transients")


if __name__ == "__main__":
    unittest.main()
