# MIDIVOLT — Real drum multi-song benchmark (v1)

## Status

The code now supports complete, **rights-reviewed** external benchmark manifests.
**No commercially approved real drum WAV + aligned GM MIDI pairs have been committed
or made available in this repository.** Consequently there is no measured
real-performance F1 for DSP versus ADT_STR. The existing 2.8-second synthetic
smoke is deliberately not used as a headline metric here.

## Collect the right material

Each test example must be an *isolated human-performed drum WAV*, with reference
**GM percussion** MIDI aligned from time zero and preserving leading silence.
Supply enough recordings across several songs, different performers and room
sounds. For evaluation of each instrument family you need actual reference
events for that instrument (a song described as "toms" without annotated tom
events does not measure tom transcription). Include:

- Kick/Double-kick (GM 35/36)
- Snare/rim/stick (GM 37/38/39/40)
- Closed/open/pedal Hi-hat (GM 42/44/46)
- Toms (GM 41/43/45/47/48/50)
- Ride (GM 51/53/59)
- Crash and cymbals (GM 49/52/55/57)
- Ghost notes, flams, overlapping hits, quiet dynamics, multiple tempi
  and mixed fills across different performances.

The evaluation scorer uses **exact GM pitch** and one-to-one event matching
within 50 ms. It never silently maps a Ride to a Crash to improve F1.
`GM_FAMILIES` are merely a coverage inventory; individual pitches keep
their own F1, and instrument families with no reference or predicted events
show as not covered.

## Data permissions

The WAV recording rights, musical performance/underlying work rights,
and the MIDI/event annotation rights are reviewed separately. Each sample
must have a named reviewer, specific license strings, attribution, written
evidence URL, and explicit permission for commercial benchmarking. All WAV and
MIDI bytes are SHA-256 pinned. The validator checks the **declaration**,
not the legal validity of the document — independent rights review remains
necessary.

No dataset/model is automatically downloaded. Keep audio, annotations, 
checkpoint weights, and any credentials **outside GitHub**.

## Prepare a manifest

Copy [drum_real_manifest.example.json](../../tests/benchmark/drum_real_manifest.example.json)
into a private local folder and fill the `samples` array. Fields under
`sample_fields_example` show the required format but are not data.
Remove that example section if desired.

Recommended folder layout:

    private_drum_bench/
      manifest.json
      audio/
        song_001_drums.wav
        song_002_drums.wav
      truth/
        song_001_drums.mid
        song_002_drums.mid

`audio_path` and `reference_midi_path` must be relative to the
manifest folder, and cannot escape it via `../` or symlinks.
All samples must belong to the held-out `test` split.
Use identical `source_song_id` for multiple takes/stems from one song
so reports can macro-average **by song**, not by file.

Get file hashes on Windows PowerShell:

    (Get-FileHash .audiosong_001_drums.wav -Algorithm SHA256).Hash.ToLower()
    (Get-FileHash .	ruthsong_001_drums.mid -Algorithm SHA256).Hash.ToLower()

## Run DSP across the actual samples

    python -m midivolt.drum_suite --manifest ./private_drum_bench/manifest.json --output ./reports/real_dsp --engines dsp

No Basic Pitch weight is necessary. Install the local transcription runtime
with `requirements-transcribe.txt` first.

## Compare ADT_STR against DSP

Install trusted, licensed, locally stored ADT_STR source/checkpoint separately,
following [ADT_STR.md](../transcription/ADT_STR.md). The model is **not**
commercially cleared and requires a research-only flag:

    python -m midivolt.drum_suite --manifest ./private_drum_bench/manifest.json --output ./reports/real_ab --engines dsp adt_str --adt-root /path/to/ADT_STR --adt-checkpoint /path/to/checkpoint --adt-python /path/to/python --research-only

The output file is `drum_suite_report.json` with:

- Per-sample F1, per-GM-pitch F1 and inference runtime for both engines.
- Per-song aggregated event counts and F1.
- **Song-macro F1** (each source song equal weight).
- **Event-micro F1** (all event counts combined).
- Latency median, nearest-rank p95 and real-time factor.
- Specific Kick, Snare, Hi-hat, Tom, Ride and Crash coverage.

You **must not** mix synthetic samples into real F1. Synthetic examples are
blocked by default; `--include-synthetic` admits them but still
creates completely separate `real_recording` and
`synthetic_rendered` summaries. Missing real data is reported
as `real_recordings_present: false`, never as a successful
real-recording accuracy measurement.

## Regression tests

    python -m unittest discover -s tests/transcription -p "test_drum_suite.py" -v

The tests only generate synthetic drum WAVs, validate false-license paths and
checksum failures, and exercise multi-song aggregation. They do not download
third-party recordings, MIDI or weights.

## Remaining gate

Real instrument-stem benchmarking is not complete until rights-cleared
recordings **actually exist** and are scored. At least a varied multi-song
held-out collection with every claimed drum-family represented is needed;
even that is not a statistically independent production quality guarantee.
Report the raw class-level errors; a high aggregate F1 can hide misses on
snares, cymbals, flams and ghost notes.
