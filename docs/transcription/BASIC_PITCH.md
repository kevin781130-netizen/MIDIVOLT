# WAV stems → MIDI: Spotify Basic Pitch baseline

Status: working *pitched-stem baseline*, not a benchmark winner or commercial clearance of all bundled model assets.

This feature converts each **already-isolated** WAV to a separate MIDI file and writes one **multi-instrument MIDI file** with distinct tracks. It does not separate a mixed recording into instruments, and it does not identify strings/woodwinds inside an "Other" stem.

## Installation (recommended Python 3.11)

Basic Pitch documents Windows, Linux and macOS support; verify your Python/runtime combination before installing production packages.

Windows PowerShell:

    py -3.11 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements-transcribe.txt

macOS/Linux:

    python3.11 -m venv .venv
    .venv/bin/python -m pip install -r requirements-transcribe.txt

For macOS Apple Silicon, follow Basic Pitch's documented runtime-specific guidance.

## Convert a folder

Keep all original stems aligned to the same song start (including leading silence). Example WAV names:

    stems/
      Song (Drums).wav
      Song (Bass).wav
      Song (Guitar).wav
      Song (Keys).wav
      Song (Vocal).wav

Windows PowerShell:

    .\.venv\Scripts\python.exe -m midivolt.transcribe --input .\stems --output .\midi --tempo 138

macOS/Linux:

    .venv/bin/python -m midivolt.transcribe --input ./stems --output ./midi --tempo 138

Expected output:

    midi/
      Song (Bass).mid
      Song (Guitar).mid
      Song (Keys).mid
      Song (Vocal).mid
      MIDIVOLT_multitrack.mid
      MIDIVOLT_report.json

**Drums.wav is intentionally skipped.** The report states why. MIDI files use the original note times in seconds; the --tempo value sets the MIDI beat grid and **does not shift or quantize the note events**. Stems with offset audio start times cannot be automatically realigned here.

## Single WAV with unknown filename

    python -m midivolt.transcribe --input "recording.wav" --output "./midi" --stem-type guitar

Supported filename keywords include drums, bass, guitar, keys, piano, synth, vocal, and other, plus selected Chinese and Japanese variants. Unidentified or ambiguous file names are skipped and recorded in the report. Use --stem-type only for a single WAV.

You may tune the basic transcription thresholds:

    python -m midivolt.transcribe --input ./stems --output ./midi --tempo 138 --onset-threshold 0.5 --frame-threshold 0.3 --min-note-ms 127.7

Repeated runs refuse to overwrite existing files. Add --overwrite only after inspecting the current output. A transcription failure stops the batch; intermediate results are staged before publication.

## What the current baseline does NOT do

- Drum stems are skipped by default; --drum-engine dsp enables an experimental kick/snare/closed-hat heuristic, not full drum transcription.
- It does **not** split one "Other" stem into violin, cello, flute, etc.
- It does **not** beat-quantize or correct performance drift; no timing offsets are silently introduced.
- It does **not** guarantee accurate chord/note onsets or offsets, remove duplicate MIDI notes, or suppress octave/harmonic false positives.
- General MIDI playback programs are assigned from filenames for convenience; they are **not** AI instrument classification.
- Reproducible numerical accuracy requires separate held-out audio/reference-MIDI benchmarking. No such score is claimed for this implementation.

## Licensing

Our adapter lives in MIDIVOLT. Basic Pitch's repository declares Apache-2.0 for code. Before a commercial build, separately pin and review installed package version, bundled checkpoint/model assets, indirect dependencies, and relevant notices. The dataset-license gate in the benchmark folder is independent from the model-license gate.

## Tests

The baseline tests use synthetic WAV fixtures and a fake predictor, so CI does not install large AI runtimes:

    python -m pip install "pretty_midi>=0.2.10,<0.3"
    python -m unittest discover -s tests/transcription -p "test_*.py" -v

The full Basic Pitch inference is not exercised by these unit tests; run an end-to-end smoke test with real audio on the target machine before commercial release.
