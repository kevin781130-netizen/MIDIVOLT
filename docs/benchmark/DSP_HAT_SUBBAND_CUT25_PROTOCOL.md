# MIDIVOLT Cut 25 — dual-subband candidate generation (pre-registered)

**Status:** Code frozen before any new official E-GMD Validation score.
Commercial release: **NO**, research candidate only.

## Motivation

Cut 24 directly replayed the same six Cut 23 Validation performances:
Conservative+shape and Conservative without the gate were IDENTICAL,
including GM42 TP=5, FP=2, FN=16 and zero candidate removals.
A post-filter cannot recover missing Hi-hat notes; it can only remove
notes. See [Cut 24 results](DSP_HAT_CUT24_ABLATION_RESULTS.md).

## New weight-free DSP candidate generator

Sources:
- [midivolt/hat_subband.py](../../midivolt/hat_subband.py)
- [midivolt/drums.py](../../midivolt/drums.py)

Only when explicitly enabled with
`transcribe_drum_wav(..., hat_subband_config=HatSubbandConfig())`:
1. Scan positive-onset spectral flux in **5.2–7.5 kHz** and
   **7.5–10.5 kHz** separately, with a robust local 0.5-second
   median/MAD and an extremely low but non-zero global floor.
2. Require two subband attack peaks within **25 ms**, each with
   minimum local attack contrast **1.7**.
3. Reject candidates that are not high-frequency dominant:
   high-band power share at least **0.16**, high/mid power ratio
   at least **1.0**, and PCM RMS >= **0.001**.
4. Enforce **55 ms** between new hats and 45 ms dedupe against
   all existing baseline GM42 events.
5. Append only *new* GM42 notes, leaving all original Kick, Snare,
   Hi-hat note timings and instrument pitches unchanged. Existing
   note velocity normalization may change when new events are
   added and is NOT a MIDI byte-identical output promise.
6. Without this option, the original DSP does not change and
   produces the original MIDI results.

This feature does not identify open hi-hat, ride, toms, or snare
articulation, and no absolute recall improvement is claimed yet.
All threshold constants are engineering hypotheses frozen before
the next Validation cohort is scored.

## Official Validation study: fresh 24-song cohort

Method:
[scripts/egmd_hat_subband_real.py](../../scripts/egmd_hat_subband_real.py),
scoring:
[midivolt/hat_subband_validation.py](../../midivolt/hat_subband_validation.py)

- **24 distinct official E-GMD v1.0.0 Validation songs**, selected by
  metadata only, before opening sound/reference MIDI.
- Acoustic Kit electronic-drum rendering, **16 beats + 8 fills**,
  35 seconds max per song, at least **4 different drummers**.
- Exclude all **12 source songs** already studied in the Cut 21
  and Cut 23 official Validation cohorts.
- No Train and no held-out Test samples. Official dataset is Google
  E-GMD CC BY 4.0; only permitted research evaluation, not bundled media
  or model-weight redistribution.
- Two identical scoring arms: original DSP Baseline and *that same*
  Baseline plus the new subband candidate generator.
- All instruments share the frozen 26-class ontology and **50 ms**
  one-to-one onset tolerance, no reference offset correction.
- Compare per-song GM42 TP/FP/FN, aggregate precision/recall/F1,
  all-drum precision/recall/F1 and runtime. Keep source WAV/MIDI
  SHA-256 and independent drummer counts, but NEVER upload raw media.

## Frozen qualification gates

**All conditions are mandatory** for a *research-only* candidate:

- At least **100 GM42 truth events** from **3 different positive songs**;
- At least **2 separate songs with zero annotated GM42 hits**;
- GM42 absolute recall gain >= **3 percentage points**;
- GM42 precision >= **0.60** and no more than **0.10** absolute
  lower than baseline;
- All-drum precision no more than **0.04** absolute lower;
- No new false GM42 events on zero-hat reference tracks;
- Never delete or shift baseline MIDI notes or add non-GM42 notes.

If the corpus fails coverage, the result is **insufficient evidence**
and the production DSP is retained. If any quality guard fails,
the production DSP is retained. Passing would still authorize only
a further independent research candidate, NOT Beta/commercial release.

## Verification

Synthetic regression tests:
- [test_hat_subband.py](../../tests/transcription/test_hat_subband.py)
- [test_hat_subband_validation.py](../../tests/transcription/test_hat_subband_validation.py)

These verify candidate generation, weak after loud hits, single-band noise,
snare dominance, duplicate removal, source partition isolation,
negative controls and unchanged default behavior. Synthetic F1 is not a
real-performing musician accuracy number.

CPU-only opt-in GitHub Action must run these tests before loading
selected official Validation WAV/MIDI via HTTP Range; raw E-GMD data is
not uploaded. Results and decision will be saved in a *separate* results
document without revising this preregistration. No automatic promotion
of the feature; the historical official Test F1 stays untouched.
