# MIDIVOLT Cut 19 — first fair shared 26-class drum comparison

**Date:** 2026-10-25  
**Run:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40189713158  
**Artifact:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40189713158/artifacts/12596569101  
**Source:** official E-GMD v1.0.0, six human-played performances recorded via electronic Roland drum-kit samples, NOT live acoustic microphone recordings.

## Results: preserve both legacy and corrected-label interpretations

Both engines were evaluated on the same frozen six Test performances (four drummers, ~110.7 s, 881 drum reference events), with one-to-one onset matching within 50 ms. Same checkpoint/source code, WAV, original annotation MIDI SHA-256 and original score TP/FP/FN were independently rechecked.

| Metric | DSP | ADT_STR |
|---|---:|---:|
| **Legacy exact numeric-label F1** | 0.505035 | 0.450952 |
| **Shared 26-class ontology F1** | **0.505035** | **0.456808** |
| Shared-label precision | 0.795122 | 0.643299 |
| Shared-label recall | 0.370034 | 0.354143 |
| Shared-label TP | 326 | 312 |
| Shared-label FP | 84 | 173 |
| Shared-label FN | 555 | 569 |
| Shared-label per-song macro F1 | **0.463150** | 0.388468 |

The new ontology adds **4 true matches** to ADT_STR versus the old
numeric-label interpretation, with 4 fewer FP and 4 fewer FN. The DSP
score remains the same because this specific test selection and output
did not contain labels whose new shared class would create additional
matched onsets.

**Decision: DSP is still stronger on THIS six-sample electronic-kit
cohort; neither algorithm is a high-accuracy production-ready solution.**
Do not extrapolate this result to all drummers, acoustic microphones,
other Roland kit sounds, different sound engineering or commercial music.

## Per-class findings: the bottleneck is missed hits

| Shared class | DSP: TP/FP/FN | ADT_STR: TP/FP/FN | Comment |
|---|---|---|---|
| 36 Bass Drum 1 | 152 / 27 / 12 | 119 / 16 / 45 | DSP wins strict class-36 recall |
| 35 Acoustic Bass Drum | 0 / 0 / 0 | 0 / 45 / 0 | 35 is an actual **separate** published Kick class |
| 38 Acoustic Snare | 95 / 56 / 79 | 96 / 71 / 78 | Both miss many |
| 42 Closed Hi-hat | 79 / 1 / 382 | 92 / 2 / 369 | Dominant recall failure |
| 41 Merged Floor Tom | 0 / 0 / 8 | 2 / 5 / 6 | Very small sample count |
| 43 Pedal Hi-hat | 0 / 0 / 6 | 1 / 5 / 5 | Not GM43 Tom |
| 44 Open Hi-hat | 0 / 0 / 4 | 2 / 0 / 2 | Small sample count |
| 58 Claves | 0 / 0 / 0 | 0 / 18 / 0 | Vendor label Claves, NOT GM58 or Tom |

Reference Closed Hi-hat has 461 hits, of which DSP misses 382 and
ADT_STR misses 369. Correcting labeling is not sufficient: **the
main deficit is event recall**.

## Checkpoint/runtime validation

The actual loaded ADT_STR model, not only its training-source config,
reported:
`ADTOF_mapping = false` and
`output_namespace = adt_str_custom`.
The runner would have failed closed if the loaded checkpoint used a
different tokenizer. Model revision:
`a33c5c6b191a4ca1e0f6dc22140947485eb36ce8`.
Published model-weight SHA-256:
`f94d1773d929166e0a3f63d305975aa6667512f8a71d7706872e1f8b23ca930b`.
Source revision:
`77dbef225e7029478ebfb916f20c7a00274f0f12`.
Frozen 47-entry full GM -> 26-class source map SHA-256:
`72fea48cad294663e496cbec7fa6143d97dd0c40b02be7952d9f6fe1a66d90c7`.

The historical exact numeric-label scores and original MIDI are
preserved, not overwritten. Raw ADT_STR custom-label MIDI is **not**
standard General MIDI for Cubase/DAW playback. This ontology is only a
fair *benchmark target*, not a commercial MIDI export converter.

## Validation

The GitHub workflow run completed successfully, and these unit groups
passed before costly model inference:
- 13 replay-lock tests
- 10 source/score replay-attestation tests
- **14 new frozen-ontology tests**
- 10 existing ADT_STR interface and comparison tests

An additional commercial release gate was **not** performed.
Model-code/weights licensing, attribution and share-alike distribution
obligations remain unresolved.

## Known evidence limitations

- Six Test performances from 4 drummers are too few for market-grade
  confidence intervals or a definitive "best in the world" ranking.
- Source WAV uses a Roland electronic drumkit, not direct acoustic drum
  microphone recordings.
- Two original WAV/reference alignment QC values indicated a potential
  **-56/-57 ms** offset, and two additional clips were inconclusive.
  We did NOT shift MIDI notes, tune timing tolerances or discard clips.
- Some reduced ontology classes merge toms, rides and cymbals by
  upstream design; the 26-class F1 is NOT full-GM instrument F1.
- No new held-out sample is used to tune the detector.

## Next cut

Develop a separate **validation-split-only** Hi-hat recall experiment
with a predefined, commercially clean DSP parameter sweep and negative
control; compare explicit real-time and precision trade-offs without
touching held-out Test metrics. Also add an optional instrument-family
metric (Kick family only, clearly labeled) instead of silently
collapsing standard GM35/36 in MIDI outputs.

See [DRUM_ONTOLOGY_V1.md](DRUM_ONTOLOGY_V1.md) for protocol.
