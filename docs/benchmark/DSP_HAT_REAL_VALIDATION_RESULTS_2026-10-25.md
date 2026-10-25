# MIDIVOLT Cut 21 — Real E-GMD Validation-only Hi-hat sensitivity study

Date: 2026-10-25  
Completed CPU-only job: https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40192447040  
Research JSON artifact: https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40192447040/artifacts/12597917889

**Status: Validation completed. Production DSP baseline retained.**

## Cohort and independent split

- Official **E-GMD v1.0.0 Validation split ONLY** (not official Test and not Train).
- 6 human-performed electronic-kit WAV/reference MIDI pairs, 4 drummers,
  4 grooves and 2 fills, about **70.39 seconds** total.
- Kit: Roland TD-17 Acoustic Kit (electronic-drum rendering); NOT live
  acoustic kit microphone audio. Source has 44.1kHz 24-bit samples.
- 491 scored drum reference events, of which **174** are the shared
  ontology class 42 (Closed Hi-hat).
- Official E-GMD paper by Callender, Hawthorne and Engel (2020),
  dataset **CC BY 4.0** by Google LLC:
  https://magenta.withgoogle.com/datasets/e-gmd
- Dataset research permission was marked explicitly as **automated
  official source-license verification**. This was NOT a human legal
  review, does NOT clear model weights, and does NOT authorize
  redistributing bundled WAV/MIDI with MIDIVOLT.

The planned six source performances were selected from metadata
**before any inference**, with no score-driven resampling.

Frozen four-setting revision: `hat-validation-presets-v1-locked`  
Settings SHA-256:
`54da24f40b6bf370c522d9645fad44033e7d1cf83136b74d874555f8dc71b36e`

All settings preserve standard GM42 output, independent Kick/Snare
thresholds, original time origins, and the 50ms one-to-one onset
scoring used in the existing shared 26-class ontology.

## Actual measured Validation scores

| Metric | Baseline | Conservative | Moderate | Aggressive |
|---|---:|---:|---:|---:|
| All-drum TP | 179 | 181 | 185 | 187 |
| All-drum FP | 83 | 85 | 88 | 88 |
| All-drum FN | 312 | 310 | 306 | 304 |
| **All-drum F1** | **0.475432** | 0.478203 | 0.484293 | 0.488251 |
| All-drum precision | **0.683206** | 0.680451 | 0.677656 | 0.680000 |
| All-drum recall | 0.364562 | 0.368635 | 0.376782 | **0.380855** |
| Closed Hi-hat TP | 34 | 36 | 40 | **42** |
| Closed Hi-hat FP | **12** | 14 | 17 | 17 |
| Closed Hi-hat FN | 140 | 138 | 134 | **132** |
| **Closed Hi-hat recall** | 0.195402 | 0.206897 | 0.229885 | **0.241379** |
| Closed Hi-hat precision | **0.739130** | 0.720000 | 0.701754 | 0.711864 |
| Closed Hi-hat F1 | 0.309091 | 0.321429 | 0.346320 | **0.360515** |
| Song-macro F1 | 0.462247 | 0.463323 | 0.464993 | **0.468014** |

DSP runtime per excerpt median: approximately 0.019–0.023 seconds.

## Pre-registered safety gates and decision

The preset may become an independent development candidate only if:
- absolute Closed Hi-hat recall improvement >= **0.02**;
- Closed Hi-hat precision stays >= **0.60**, and drops by <= **0.12**
  versus baseline;
- all-drum precision drops by <= **0.05**;
- at least **six distinct Validation songs**;
- includes an excerpt with **no reference Closed Hi-hat notes**;
- candidate must not increase false Closed Hi-hat predictions on
  such negative-control excerpts.

Negative-control results (3 Validation samples with no GM42 truth):

| Preset | False GM42 hits on no-hat passages |
|---|---:|
| Baseline | **0** |
| Conservative | **0** |
| Moderate | 2 |
| Aggressive | 2 |

The Conservative setting fails the pre-registered **+0.02 recall gain**
threshold (actual +0.011495). Moderate and Aggressive pass the
aggregate precision/recall gates but **both fail negative control**.

### Final frozen choice

**RETAIN BASELINE. No parameter changes adopted.**

The aggressive setting improves Closed Hi-hat recall by about 4.60
absolute percentage points, but introduces false hi-hats in explicit
no-hat passages. Calling it an improvement without disclosing this
failure would overstate MIDI transcription quality.

The prior *separate official Test* outcome stays untouched:
DSP 26-class event F1 0.505035 on six completely different Test
performances. It is NOT recomputed/tuned on this Validation experiment.

## Verification and repository scope

The one-off GitHub CPU job succeeded through every stage:
- 6 old DSP baseline unit tests,
- 15 new Hi-hat guard/negative-control tests,
- 9 source-split/licensing/metadata tests,
- official CSV download, Range-only selected WAV/MIDI extraction,
- four DSP Validation passes,
- artifact upload with plan+scores only.

**30 unit tests passed.** No PyTorch/ADT_STR/Basic Pitch weights
were installed. No raw third-party WAV/MIDI data were added to the
repository or uploaded as artifacts.

## Next engineering decision

Threshold-only DSP changes did not satisfy the quality bar.
The next meaningful improvement is a *new classifier feature* trained
or calibrated on a separate development subset, e.g. attack spectral
shape and hi-hat versus snare/cymbal distinction, with independent
negative controls. Pre-register the candidate, evaluate only on
Validation, freeze it, and test once on genuinely held-out Test.

The data is too small to claim general acoustic drum transcribing
quality or to approve commercial Beta; ADT_STR model-weight
distribution rights remain separately unresolved.
