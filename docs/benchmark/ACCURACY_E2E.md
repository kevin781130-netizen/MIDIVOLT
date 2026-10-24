# MIDI Note Accuracy: First End-to-End Baseline

Run date: 2026-10-24  
GitHub Actions evidence: https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40090533832

## Scope

The first real Basic Pitch inference test ran an actual neural-network model
using a real PCM WAV file generated programmatically from three **synthetic**,
single-note keyboard tones. There were no human performances, separated stems,
or commercial reference dataset assets in this test.

- WAV: 4.25 seconds, 22,050 Hz, mono, 16-bit PCM.
- Ground truth: 3 MIDI notes, pitches 60, 64 and 67, with known starts/ends.
- Transcription: Basic Pitch using Python 3.10; onset threshold 0.35,
  frame threshold 0.25, minimum note 100 ms.
- Output: separate pitched-stem MIDI, merged multitrack MIDI, JSON reports.
- MIDI tempo setting: 120 BPM, **no quantization**.
- Runtime dependency note: NumPy 2.x broke this build's TensorFlow Lite
  loading; fixed by pinning NumPy >=1.23.5,<2.0.

## Observed results on this single synthetic waveform

| Metric | Value |
|---|---:|
| Reference notes | 3 |
| Predicted notes | 4 |
| Onset true positives | 3 |
| False positives | 1 |
| False negatives | 0 |
| Precision | 0.750000 |
| Recall | 1.000000 |
| Onset F1 at 50 ms | 0.857143 |
| Strict onset-and-offset F1 | 0.857143 |
| Mean absolute onset error | 8.065 ms |
| Mean absolute offset error | 45.391 ms |
| Model-inference time (CPU CI) | 15.588 seconds |

The additional MIDI note was pitch 60, starting at about 1.219 s and ending
at about 1.335 s, near the tail of the first ground-truth note. The evaluator
now reports possible tail fragments separately from onset duplicates and
octave-error candidates, without falsely counting them as correct notes.

**Do not extrapolate this F1 to the quality of a real instrument/vocal take,
other timbres, polyphonic passages, or full songs.** Synthetic note generation
tests the pipeline and supplies a known-answer probe, not a statistically
significant benchmark. CPU CI inference time cannot be compared with other
published benchmark speeds without matching hardware and conditions.

## Score an actual pitched WAV transcription

When you have an independently aligned reference MIDI for a *single stem*:

    python -m midivolt.evaluate --reference ./references/Bass.mid --predicted ./output/Bass.mid --output ./output/Bass.metrics.json

The evaluator measures:

- note-onset precision/recall/F1 at 50 ms;
- strict note-onset-and-offset F1, with offset tolerance
  max(50 ms, 20% of reference-note duration);
- diagnostic onset F1 at 100 ms;
- mean absolute onset and offset errors in milliseconds;
- matching-note onset/offset biases;
- unmatched reference and predicted note lists;
- octave, duplicate-onset and split-tail-fragment **candidates**.

The note matcher uses one-to-one maximum cardinality matching and indexed
candidate lookup by pitch and onset. It does not score instrument identity:
never combine separate-stem MIDI reference tracks unless the instrument track
mapping has already been confirmed. The evaluator refuses drums: percussion
events must use a dedicated kit-piece-aware metric.

## Run repeatable smoke in GitHub Actions

Workflow: .github/workflows/benchmark-safety.yml

The normal unit job validates scorer logic without loading the model.
The Basic Pitch end-to-end job installs requirements-transcribe.txt,
generates its own WAV/reference MIDI, runs a real model inference,
computes F1 and timing diagnostics, and publishes the smoke artifacts
under the name midivolt-basic-pitch-smoke. No third-party audio is downloaded.

This does not validate automatic stem separation, human-performed
instrument recognition, or commercial licensing for other models/datasets.

## Next benchmark gate

To claim a model is accurate enough for MIDIVOLT commercial beta, collect
commercially cleared human-reference recordings of drums, bass, guitar,
piano/keys and vocal at diverse tempi and techniques; score each pitched
stem independently; add a drum-specific evaluator; report per-song and
macro-averaged results on a held-out test set. Record failed inference jobs,
hardware and runtime, too.
