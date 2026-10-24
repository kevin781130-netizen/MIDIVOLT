"""End-to-end Basic Pitch smoke on an actual PCM WAV through the real model.

The waveform is PROGRAMMATICALLY SYNTHESIZED from known reference MIDI.
It does NOT substitute for evaluating commercially-cleared human performances.
Run explicitly with MIDIVOLT_RUN_E2E=1; unit CI otherwise skips model loading.
"""
from __future__ import annotations

import json
import math
import os
import struct
import tempfile
import unittest
import wave
from pathlib import Path

import pretty_midi

from midivolt.evaluate import evaluate
from midivolt.transcribe import transcribe_stems


SAMPLE_RATE = 22050
PATTERN = (
    (60, 0.35, 1.28),
    (64, 1.56, 2.52),
    (67, 2.85, 3.85),
)


def generate_reference_and_audio(wav_path: Path, reference_path: Path):
    """Render fixed notes with harmonic energy to 16-bit, mono PCM."""
    reference = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=0, name="keys | Smoke (Keys)")
    for pitch, start, end in PATTERN:
        inst.notes.append(pretty_midi.Note(velocity=95, pitch=pitch, start=start, end=end))
    reference.instruments.append(inst)
    reference.write(str(reference_path))

    frames = bytearray()
    for sample_index in range(round(4.25 * SAMPLE_RATE)):
        t = sample_index / SAMPLE_RATE
        amplitude = 0.0
        for pitch, start, end in PATTERN:
            if start <= t < end:
                local = t - start
                fade = min(1.0, local / 0.035, (end - t) / 0.055)
                frequency = pretty_midi.note_number_to_hz(pitch)
                phase = 2.0 * math.pi * frequency * local
                amplitude += max(0.0, fade) * (
                    0.31 * math.sin(phase)
                    + 0.10 * math.sin(2.0 * phase)
                    + 0.045 * math.sin(3.0 * phase)
                )
        sample = round(max(-1.0, min(1.0, amplitude)) * 32767)
        frames.extend(struct.pack("<h", sample))

    with wave.open(str(wav_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(frames)


@unittest.skipUnless(os.environ.get("MIDIVOLT_RUN_E2E") == "1", "Real-model smoke is opt-in")
class BasicPitchIntegrationSmoke(unittest.TestCase):
    def test_synthesized_wav_through_real_model_and_score(self):
        # Create temporary input and report; optionally export only generated
        # non-copyrighted smoke artifacts to GitHub Actions.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inp = root / "Smoke (Keys).wav"
            ref = root / "reference.mid"
            out = root / "out"
            generate_reference_and_audio(inp, ref)

            report = transcribe_stems(
                inp, out, tempo=120.0, onset=0.35,
                frame=0.25, minimum_note_ms=100,
            )
            self.assertEqual(len(report["tracks"]), 1)
            self.assertTrue((out / "Smoke (Keys).mid").is_file())
            merged = pretty_midi.PrettyMIDI(str(out / "MIDIVOLT_multitrack.mid"))
            predicted = pretty_midi.PrettyMIDI(str(out / "Smoke (Keys).mid"))
            self.assertEqual(len(merged.instruments), 1)
            self.assertGreater(sum(len(i.notes) for i in predicted.instruments), 0)

            metrics = evaluate(pretty_midi.PrettyMIDI(str(ref)), predicted)
            for key in ("note_onset", "strict_note_onset_offset", "diagnostic_onset_100ms"):
                self.assertGreaterEqual(metrics[key]["f1"], 0.0)
                self.assertLessEqual(metrics[key]["f1"], 1.0)
            self.assertEqual(metrics["reference_notes"], len(PATTERN))
            self.assertNotEqual(metrics["settings"]["quantized"], True)
            self.assertLessEqual(
                max(n.end for i in predicted.instruments for n in i.notes),
                4.8,
                "Predicted notes unexpectedly extend well beyond the input waveform",
            )

            artifact = os.environ.get("MIDIVOLT_SMOKE_ARTIFACT_DIR")
            if artifact:
                directory = Path(artifact)
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "metrics.json").write_text(
                    json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
                )
                (directory / "transcribe_report.json").write_text(
                    json.dumps(report, indent=2) + "\n", encoding="utf-8"
                )
                inp.replace(directory / inp.name)
                ref.replace(directory / ref.name)
                (out / "Smoke (Keys).mid").replace(directory / "predicted.mid")
                (out / "MIDIVOLT_multitrack.mid").replace(directory / "multitrack.mid")


if __name__ == "__main__":
    unittest.main()
