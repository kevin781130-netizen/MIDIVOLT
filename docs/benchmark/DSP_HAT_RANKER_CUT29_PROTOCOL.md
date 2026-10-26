# Cut 29 — Training-data scaling with drummer-disjoint holdout

Date: 2026-10-26.
**Method frozen BEFORE any new WAV/MIDI or model results.**
Research-only, weight-free DSP + Train-fitted logistic ranker.

## Metadata feasibility gate

Following the successful official Cut 28 (24 TRAIN fitting recordings,
186 new candidates of which 89 positive and 97 negative; only 10
recordings contributed candidates), model ranker 0.80 accepted just 3
incremental correct GM42 notes and recovered +0.35pp absolute recall
on 12 official previously-unseen Validation tracks. It failed the
preregistered +3pp gate; keep production baseline.

Previous Validation songs already scored in Cuts 21, 23, 25, 26, 28:
6 + 6 + 24 + 24 + 12 = **72 original performances**.

One SOURCE-METADATA-ONLY job, run before evaluating further data:
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40265553397
confirmed (E-GMD v1.0.0, official Acoustic Kit render):

| Partition after excluding 72 previously scored Validation songs | <=90sec unique sources | Beats | Fills | Drummers |
|---|---:|---:|---:|---:|
| TRAIN | 699 | 196 | 503 | 9 |
| Available VAL | **40** | **0** | 40 | **2** |

At longer 180sec ceiling, available VAL remains 40, ALL Fills
from TWO drummers. A new large, balanced, drummer-diverse official
Validation for GM42 cannot be obtained under these constraints.
**Do not secretly reuse the 72 previously scored Validation clips,
borrow any official TEST, or call a pool of only Fills a representative
holdout for commercial Hi-hat accuracy.**

## Explicit experiment design: original TRAIN-internal evaluation

Code:
[midivolt/hat_ranker_cut29_group_holdout.py](../../midivolt/hat_ranker_cut29_group_holdout.py)
and [scripts/egmd_ranker_cut29_real.py](../../scripts/egmd_ranker_cut29_real.py).

- Source: ONLY original E-GMD v1.0.0 **TRAIN**, Google LLC
  CC BY 4.0. No Validation/Test WAVs, annotation MIDI or weights.
- Select on public CSV metadata, BEFORE downloading or examining any
  WAV/MIDI, with fixed seed
  `midivolt-cut29-drummer-holdout-preselected-v1`.
- **72** TRAIN fit recordings: 48 Beats + 24 Fills, Acoustic Kit,
  each up to 90 seconds.
- A nested, independently metadata-selected **24** out of those 72
  (16 Beats + 8 Fills) trains the SMALL ranker.
- The EXPANDED ranker trains on the entire 72-song set.
- **24 held-out original TRAIN** recordings (12 Beats + 12 Fills)
  from exactly **two whole drummers** entirely absent from BOTH
  training sets. Total 96 unique source performances.
- Choose the held-out drummer pair deterministically from metadata
  combinations that meet beat/fill quotas and leave >=4 TRAIN
  drummers. All source IDs, styles, duration metadata and drummer IDs
  are pinned to source_selection_plan.json before any sound access.
- Fit both rankers with identical architecture, frozen 5 features,
  L2=.10, 900 iterations, learning rate=.12, threshold=.80.
- Require >=4 candidate-contributing TRAIN source performances,
  >=10 positive and >=10 negative candidate events per model.
  The real evaluated number of contributing sources is reported.
- Evaluate on the SAME 24 drummer-disjoint TRAIN holdout recordings:
  unchanged DSP, raw candidate generator, 24-song ranker, 72-song
  ranker. Event F1 uses frozen 26-class drum ontology and 50ms
  one-to-one onset matching; report GM42 precision/recall, marginal
  new-note precision, actual added TP/FP and no-GM42 controls.
- Retain old quality guards as **exploratory internal checks**:
  >=100 GM42 true hits, >=3 positive tracks, >=2 no-hat controls,
  +3pp recall, >=60% marginal new-note precision, overall hat
  precision >=60% and within 10pp of baseline, all-drum precision
  within 4pp, NO new FP on negative controls.
- Fail insufficient coverage rather than resampling based on labels.
  Even passing internal checks is NOT official Validation, NOT
  independent commercial evaluation, NOT permission to auto-enable
  the model and NOT Beta readiness.

**Causality qualification:** Different model sizes share a nested
training cohort and identical optimizer; this is evidence about
*training-set scaling on these held-out TRAIN drummers only*. It does
not prove gains in acoustic studio recordings or an external domain.
If larger model helps training-only holdout, seek entirely NEW
rights-approved recordings, preferably mic-recorded acoustic drums,
before any production promotion.

The small/large model weights, reference MIDI and WAV files stay only
in private ephemeral job storage. Metrics JSON and public metadata
source IDs and SHA-256s alone may be uploaded. Official E-GMD source
CC BY 4.0 declaration:
https://magenta.withgoogle.com/datasets/e-gmd
(Attribution: Google LLC; Callender, Hawthorne & Engel 2020).

Offline tests:
[tests/transcription/test_hat_ranker_cut29_group_holdout.py](../../tests/transcription/test_hat_ranker_cut29_group_holdout.py)
validate exact song identity, split gate, drummer non-leakage,
nested cohort selection, guardrails and no non-GM42 modifications.
Any genuine results require a SEPARATE report and the linked
successful CPU-only job; synthetic test counts are not real metrics.
