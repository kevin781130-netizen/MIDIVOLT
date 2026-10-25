# E-GMD mini pilot — real human performance, electronic drum-kit audio

This pilot is **not** the production benchmark. It automatically measures a
small number of official E-GMD held-out TEST performances on the same
Roland TD-17 "Acoustic Kit" rendered audio, using DSP and pinned ADT_STR
weights. These are recorded electronic drum-kit sounds from human MIDI
performances — NOT direct microphone recordings of acoustic drums.

## Why a bounded remote ZIP reader?

The official E-GMD v1.0.0 WAV+MIDI archive is ~90 GB compressed.
The pilot uses HTTP Range and the remotezip Python library to list
the ZIP central directory and fetch **only three exact WAV/MIDI pairs**.

Before attempting a ZIP operation, the script requests `Range: bytes=0-0`
and **requires HTTP 206 plus Content-Range**. If the origin ignores Range,
the tool refuses to continue. It never substitutes a full-archive download.
Each WAV/MIDI entry is individually capped at 28 MiB uncompressed.

Canonical Google Magenta source and license:
https://magenta.tensorflow.org/datasets/e-gmd

Full archive URL:
https://storage.googleapis.com/magentadata/datasets/e-gmd/v1.0.0/e-gmd-v1.0.0.zip

Metadata CSV URL:
https://storage.googleapis.com/magentadata/datasets/e-gmd/v1.0.0/e-gmd-v1.0.0.csv

Dataset published under **CC BY 4.0** by Google LLC; attribution and
specific release/version identification are required. This research run
does not automatically certify commercial deployment, since ADT_STR
checkpoint terms still require rights review.

## Exact selection

- Original upstream Test split only, never train/validation.
- `kit_name = Acoustic Kit` (an acoustic-sounding kit rendered by TD-17).
- Up to 22 seconds per excerpt, selected from the shortest performances
  while round-robin sampling different musical styles.
- Three different `source_song_id` values (not three alternative renders
  of one performance).
- Preserve original onset times, no timing correction or threshold tuning.
- Pin E-GMD metadata CSV SHA-256 and extracted WAV/MIDI SHA-256.
- References are normalized in-memory from Roland-specific to standard
  General MIDI drum notes where known, without modifying original files.

## Models and scores

Research workflow:
[egmd-mini-research.yml](../../.github/workflows/egmd-mini-research.yml)

Actual runner:
[scripts/egmd_mini_real.py](../../scripts/egmd_mini_real.py)

- DSP: MIDIVOLT weight-free transient detector.
- ADT_STR: exact source commit `77dbef225e7029478ebfb916f20c7a00274f0f12`;
  Hugging Face model revision `a33c5c6b191a4ca1e0f6dc22140947485eb36ce8`;
  model weight SHA-256
  `f94d1773d929166e0a3f63d305975aa6667512f8a71d7706872e1f8b23ca930b`.

The script scores exact GM pitch one-to-one matches with 50 ms onset
tolerance, including per-pitch F1 and each individual performance's
precision/recall/errors. It also reports song-macro and event-micro
metrics, separate latency, and alignment quality diagnostics.

If an engine fails to run on a clip, the clip is scored as zero
true positives with every reference note counted as a false negative;
it will not be silently omitted from aggregated scores.

## Security and reproducibility

The GitHub Actions job runs ONLY with explicit workflow dispatch or a
commit message containing `[egmd-real-once]`.
It validates ZIP Range support before installing the expensive model runtime.
The runner never uploads WAV/MIDI bytes, third-party checkpoints,
or private credentials. Only selection-plan, metric and error JSON files are
kept as short-lived artifacts.

No external samples are stored in MIDIVOLT Git history.
The commercial-release gate remains unchanged.

## How to interpret

Even when this succeeds, **3 clips is a diagnostic pilot**, not a
statistically meaningful generalization estimate. A true model selection
requires many held-out performances, different drummers and drumkits,
ghost notes, flams, hi-hat openness and ride/crash/tom coverage; and
separate live acoustic drum microphone recordings.

If the run fails because Google Storage lacks HTTP Range, the correct
result is **no E-GMD scores**, not synthetic substitutes.
