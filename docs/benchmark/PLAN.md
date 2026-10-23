# Audio-to-MIDI Benchmark Plan

Status: **Specification only — no model has been selected or declared production-ready.**

## Goal

Choose a fast, accurate, commercially deployable transcription engine for each already-separated audio stem and produce clean, time-aligned, editable multitrack MIDI.

## Scope

Evaluate these stem classes independently:

- **drums** — drum events, kit-piece labels, onset and velocity.
- **bass** — monophonic/polyphonic bass notes, onset, offset, pitch and velocity.
- **guitar** — single-note lines, chords, strums and sustained notes.
- **keys** — piano/electric piano/synth keyboard, including polyphony.
- **vocal** — sung melody; backing vocals are a separate optional class.

Do not mix results from synthetic stems and real recordings into one headline score. Report each domain separately.

## Dataset rules

1. A scored sample MUST have reference MIDI aligned to the exact audio render/recording.
2. Keep all stems from the same song/source in a single split to prevent train/test leakage.
3. Preserve the original timeline. Do not trim leading silence independently from WAV and reference MIDI.
4. Record sample rate, channels, duration, source family, instrument class, tempo if known, and provenance.
5. Mark synthetic/rendered audio and real recordings separately.
6. Before downloading or redistributing a dataset, record its audio, MIDI/annotation, and dataset terms independently. A dataset is not cleared for commercial use merely because its repository is public.
7. Never use a test-set song to tune thresholds or post-processing.

## Candidate evaluation lanes

- **Local permissive baseline:** Spotify Basic Pitch (Apache-2.0 code; audit model/artifact and dependency terms before release).
- **Commercial API reference:** Klangio API, subject to provider terms, pricing, retention/privacy, and output-use review.
- **Drums:** evaluate a dedicated drum transcription model such as ADT_STR only after code, checkpoint, training-data and output-license review.
- **Research-only candidates:** YourMT3/YourMT3+ and MuScriptor may be benchmarked in an isolated research lane, but must not enter the commercial build until code, weights, training data, and redistribution terms are cleared.
- Add other candidates only with a pinned version, documented hardware and license evidence.

## Metrics

### Notes and timing

- Note precision, recall and F1 with pitch matching and **50 ms onset tolerance**.
- Strict note F1 requiring both onset and offset: onset tolerance 50 ms; offset tolerance max(50 ms, 20% of reference-note duration).
- Also report onset-only F1 at 100 ms as a diagnostic, never as the sole score.
- Polyphonic frame-level precision/recall/F1 at a documented frame hop (default 10 ms).
- Report per-instrument and per-song results; macro-average across songs so long tracks do not dominate.

### Instrument-specific

- Drums: event F1 at 50 ms and 100 ms; report kit-piece classification separately from onset detection.
- Pitched stems: note F1, pitch errors, octave errors, and note fragmentation/merging.
- Velocity: MAE and correlation where reference velocities are available.
- Pitch bend: event/curve error only when the reference contains meaningful pitch-bend data.
- Timeline: onset drift at the beginning, middle and end of each file.

### Speed and resources

Record audio duration, wall-clock inference time, real-time factor (inference_seconds / audio_seconds), cold-start and warm-run times separately, CPU/GPU model, GPU VRAM peak, RAM peak, and whether upload/queue/post-processing time is included.

Run each sample three times for local engines where practical. Report median and p95 latency. For hosted APIs, separately report upload, queue, inference/response and total wall-clock time when observable.

## Fair comparison protocol

1. Pin engine version, checkpoint hash, runtime, parameters and hardware.
2. Resample only as required by the engine; log the exact transform.
3. Keep input gain and channel handling consistent; do not normalize one candidate differently without recording it.
4. Give every engine the same audio and the same held-out reference set.
5. Score raw model output first. Score post-processed output in a separate column.
6. No hidden manual correction. Any human-edit pass must be timed and reported separately.
7. Report failed jobs and unsupported inputs; do not silently omit them.

## Commercial clearance gate

Before any candidate enters a release build, create a record for:

- source-code license and required notices;
- model/checkpoint license and commercial-use permission;
- training-data and benchmark-data terms;
- third-party dependencies and model download terms;
- hosted API contract, billing, data retention, and customer-audio privacy;
- redistribution, attribution, share-alike, copyleft and network-service obligations.

**No candidate is commercially cleared until all applicable fields have evidence and an explicit pass decision.** This is an engineering checklist, not legal advice.

## Initial acceptance gates

Do not choose a winner from published scores alone. Use these initial gates, then adjust only before looking at held-out results:

- Every stem class has a separate report.
- All results are reproducible from a pinned manifest/config.
- MIDI timeline remains aligned with the input stem.
- Both raw and post-processed metrics are retained.
- No unresolved license blocker for the intended deployment model.
- Compare accuracy against latency and resource use; do not trade away note accuracy silently for speed.

## Required report

For each candidate and stem class, emit:

- version/checkpoint and license status;
- sample count, source-domain breakdown and failure count;
- onset F1@50 ms, strict note F1, frame F1, and relevant instrument metrics;
- median/p95 seconds per minute of audio and peak RAM/VRAM;
- raw versus post-processed scores;
- known failure cases and a clear pass, research-only, or blocked decision.

The benchmark manifest schema lives in [manifest.json](./manifest.json).
