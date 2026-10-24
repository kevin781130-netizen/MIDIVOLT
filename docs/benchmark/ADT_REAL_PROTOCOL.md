# ADT_STR pinned-checkpoint evaluation protocol (research lane)

This MIDIVOLT lane is deliberately separate from everyday CI and commercial
builds. The upstream ADT_STR source and checkpoint are NOT vendored.

## Official sources and exact revisions

- Source: https://github.com/pier-maker92/ADT_STR
- Source commit: 77dbef225e7029478ebfb916f20c7a00274f0f12
- Official model: https://huggingface.co/Pierfrancesco/adt-str
- Candidate Hub commit: a33c5c6b191a4ca1e0f6dc22140947485eb36ce8
  (from a third-party model provenance claim; runtime preflight MUST verify it)
- Intended variant: setting-tau-0.8
- Code license: upstream CC BY-SA 4.0; weight-specific permissions, modifications,
  exact attribution and distribution implications still require review.

## One-off testing policy

Workflow: .github/workflows/adt-real-benchmark.yml

Normal branch pushes are skipped. A test may be triggered using
workflow_dispatch once available on the default branch, or with a deliberate
feature-branch commit message including [adt-real-once].

The job preflights the revision/file list before installing expensive runtimes.
The job has a 35-minute timeout, pins upstream source revision and PyTorch
versions, runs on CPU, and uploads only WAV/MIDI/JSON test outputs. Never
upload Hugging Face model weights in CI artifacts.

## Data and scores

The generated input is 2.8 seconds of six synthetic drum events based on
tests/transcription/test_drums.py (kick, snare, closed hat; simultaneous hits).
The exact same WAV and reference MIDI are used for both engines.

Performance report contains:

- DSP wall time vs ADT_STR model download/load/inference wall time;
- each engine's F1 at 50 ms onset tolerance, exact GM pitch matching;
- per-class F1, false positives and false negatives;
- SHA-256 of the downloaded model weights, sample audio and reference MIDI;
- exact source and model commit revisions.

This is a pipeline reproducibility smoke, not representative accuracy across
real bands/genres. For a model selection decision, a separate held-out,
license-cleared **real performance** benchmark is still mandatory.

## Results

See GitHub Actions build artifacts. No real-model metrics should be published
until the job has completed successfully. Metadata/API failure must be
reported as a blocker, not construed as zero accuracy.

## Release safety

The external ADT_STR adapter continues to require an explicit
--research-only flag, and the commercial-gate path remains unchanged.
Even if the model is executable or has a high synthetic F1, that does
not mean all code, weights, checkpoint provenance, downstream
dependencies or share-alike obligations have been cleared for MIDIVOLT.
