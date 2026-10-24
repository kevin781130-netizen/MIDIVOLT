"""Real synthesized PCM drum WAV → independently routed GM MIDI smoke tests.

These tests verify basic event detection and timeline handling, not accuracy
on human drum performances or commercial readiness.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pretty_midi
from scipy import signal
from scipy.io import wavfile

from midivolt.drums import transcribe_drum_wav
from midivolt.transcribe import transcribe_stems


SAMPLE_RATE = 22050
PATTERN = [
    ("kick", 0.25),
    ("hat", 0.52),
    ("snare", 0.90),
    ("kick", 1.30),
    ("hat", 1.30),
    ("hat", 2.10),
]
PITCH = {"kick": 36, "snare": 38, "hat": 42}


def synthetic_drums(path: Path, *, samplerate: int = SAMPLE_RATE) -> None:
    """Write six time-aligned hit events, including simultaneous kick and hat."""
    rng = np.random.default_rng(93)
    x = np.zeros(round(2.8 * samplerate), dtype=np.float64)
    for kind, t in PATTERN:
        n = round(0.18 * samplerate)
        local = np.arange(n) / samplerate
        if kind == "kick":
            frequency = 65.0 + 50 * np.exp(-local / 0.035)
            phase = 2 * np.pi * np.cumsum(frequency) / samplerate
            burst = np.sin(phase) * np.exp(-local / 0.045)
        elif kind == "snare":
            filt = signal.butter(4, [340, 3500], fs=samplerate, btype="bandpass", output="sos")
            burst = signal.sosfilt(filt, rng.normal(size=n)) * np.exp(-local / 0.042)
        else:
            filt = signal.butter(4, [5500, min(10200, samplerate * 0.48)],
                                 fs=samplerate, btype="bandpass", output="sos")
            burst = signal.sosfilt(filt, rng.normal(size=n)) * np.exp(-local / 0.03)
        start = round(t * samplerate)
        x[start:start + n] += 0.8 * burst / max(0.01, np.max(np.abs(burst)))
    wavfile.write(str(path), samplerate, np.round(np.clip(x, -1, 1) * 30000).astype(np.int16))


def check_hits(test, instrument):
    test.assertTrue(instrument.is_drum)
    events = sorted((note.pitch, note.start) for note in instrument.notes)
    expected = sorted((PITCH[kind], time) for kind, time in PATTERN)
    test.assertEqual(len(events), len(expected), f"Unexpected drum events: {events}")
    for (pitch, found), (expected_pitch, wanted) in zip(events, expected):
        test.assertEqual(pitch, expected_pitch)
        test.assertLessEqual(abs(found - wanted), 0.035)


class DrumTests(unittest.TestCase):
    def test_synthetic_drum_wav_detects_all_three_classes_and_overlap(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Song (Drums).wav"
            synthetic_drums(path)
            midi, diagnostic = transcribe_drum_wav(path)
            self.assertEqual(diagnostic["counts"], {"kick": 2, "snare": 1, "hat": 3})
            self.assertEqual(diagnostic["detected"], 6)
            check_hits(self, midi.instruments[0])

    def test_drums_only_batch_produces_separate_and_merged_percussion_midi(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "Song (Drums).wav"
            dest = Path(folder) / "midi"
            synthetic_drums(source)
            report = transcribe_stems(source, dest, stem_type="drums", drum_engine="dsp", tempo=138)
            self.assertEqual(report["engine"], "drum_dsp_v1")
            self.assertEqual(report["tracks"][0]["note_count"], 6)
            self.assertEqual(report["tracks"][0]["engine"], "drum_dsp_v1")
            separate = pretty_midi.PrettyMIDI(str(dest / "Song (Drums).mid"))
            merged = pretty_midi.PrettyMIDI(str(dest / "MIDIVOLT_multitrack.mid"))
            self.assertEqual(len(merged.instruments), 1)
            check_hits(self, separate.instruments[0])
            check_hits(self, merged.instruments[0])

    def test_mixed_folder_retains_drums_and_pitched_separate_tracks(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "stems"
            source.mkdir()
            synthetic_drums(source / "Song (Drums).wav")
            synthetic_drums(source / "Song (Bass).wav")

            def fake_pitched_predict(*args):
                midi = pretty_midi.PrettyMIDI(initial_tempo=138)
                track = pretty_midi.Instrument(program=0)
                track.notes.append(pretty_midi.Note(pitch=48, velocity=100, start=0.35, end=0.65))
                midi.instruments.append(track)
                return midi

            output = Path(folder) / "result"
            report = transcribe_stems(source, output, drum_engine="dsp", tempo=138,
                                      predictor=fake_pitched_predict)
            self.assertEqual(len(report["tracks"]), 2)
            merged = pretty_midi.PrettyMIDI(str(output / "MIDIVOLT_multitrack.mid"))
            self.assertEqual(len(merged.instruments), 2)
            self.assertEqual([x.is_drum for x in merged.instruments], [False, True])
            self.assertEqual([x.name for x in merged.instruments],
                             ["bass | Song (Bass)", "drums | Song (Drums)"])
            self.assertEqual(merged.instruments[0].notes[0].start, 0.35)

    def test_silent_audio_emits_zero_notes_without_inventing_hits(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Drums.wav"
            wavfile.write(str(path), SAMPLE_RATE, np.zeros(SAMPLE_RATE, dtype=np.int16))
            result, diagnostic = transcribe_drum_wav(path)
            self.assertEqual(diagnostic["detected"], 0)
            self.assertEqual(len(result.instruments[0].notes), 0)

    def test_drum_midi_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "Song (Drums).wav"
            synthetic_drums(source)
            with self.assertRaisesRegex(ValueError, "dedicated engine"):
                transcribe_stems(source, Path(folder) / "out", stem_type="drums")

    def test_rejects_bad_threshold(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Drums.wav"
            synthetic_drums(path)
            with self.assertRaisesRegex(ValueError, "min_peak_fraction"):
                transcribe_drum_wav(path, min_peak_fraction=1.1)


if __name__ == "__main__":
    unittest.main()
