# MIDIVOLT Cut 28 — frozen official TRAIN model / unseen Validation evaluation

**Protocol frozen before model training, WAV inspection, or comparison scores.**
Version: `cut28-train-ranker-independent-validation-v1`.
Production DSP remains unchanged. Official TEST is never used.

## Motivation and locked prior evidence

Cut26 independently tested 24 E-GMD Validation performances. The
manually gated DSP recovered 46 correct extra GM42 notes while adding 48
false candidates, marginal Precision 48.94%, recall +1.28 pp;
both prespecified gates failed. Repeated manual threshold tuning on
these songs is forbidden.

The fully frozen list of **60** previously evaluated Validation source
performances is maintained in:
[midivolt/hat_ranker_independent_eval.py](../../midivolt/hat_ranker_independent_eval.py).
The authentic Cut26 plan is required as an exact SHA-256 file:
`7ca54be3db2a48f54f7bf71c6791327f5bec7a9aeeeeeb396d8e0fe87d5bfcd9`,
plus all 24 source IDs. The Cut26 artifact is documented here:
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40201094578.

## Non-score-based song selection, before audio or MIDI access

Official E-GMD v1.0.0 CSV is downloaded as a small, hashed source. The
first frozen selection plan includes BOTH populations:

| Dimension | TRAIN | Independent Validation |
|---|---|---|
| Official upstream split | **train only** | **validation only** |
| Original source-song identities | 24 | 12 |
| Styles | 16 beats + 8 fills | 4 beats + 8 fills |
| Render | Acoustic Kit (electronic Roland re-recording) | Same |
| Maximum metadata duration | 180 seconds | 180 seconds |
| Exclusions | All train/validation ID overlaps prohibited | 60 previously inspected Validation IDs |
| Diversity | >=4 TRAIN drummers | >=3 Validation drummers |
| Sampling | Fixed source ID/drummer/style seed | Separate fixed source ID/drummer/style seed |

Every selection uses original source IDs, never multiple kit renders
from one performance or information derived from F1 labels. For strict
reproducibility, the JSON preserves exact metadata order, selected
source IDs, and hashes of all downloaded WAVs and MIDI. If the chosen
Validation subset contains too few true GM42 or no-hat negative-control
songs, **the conclusion is insufficient coverage; do not resample
based on annotation content.**

The E-GMD publisher states CC BY 4.0 for v1.0.0 and gives 819 Train,
117 Validation and 123 Test unique sequences:
https://magenta.withgoogle.com/datasets/e-gmd .
This permits a documented research workflow; it does not certify
redistribution of external weights or completion of product counsel
review. Attribution: Google LLC; Callender, Hawthorne & Engel (2020).

## CPU-only training

New source:
[hat_candidate_ranker.py](../../midivolt/hat_candidate_ranker.py).
Reference-aware candidate labels:
[hat_ranker_training.py](../../midivolt/hat_ranker_training.py).
Actual private runner:
[scripts/egmd_hat_ranker_real.py](../../scripts/egmd_hat_ranker_real.py).

- Use original DSP and *raw* dual-subband candidate generator for each
  TRAIN WAV. Normalize reference Roland MIDI to standard GM.
- Match baseline GM42 to reference within 50ms FIRST; remove those
  matched ground-truth hits. Label only genuinely added candidate
  GM42 events against remaining truth, one-to-one within 50ms.
- Extract frozen five spectral features from the same candidate STFT
  used by inference. TRAIN-only normalization, log1p transformed input.
- Fit a deterministic logistic ranker with constant L2=0.10,
  900 iterations, learning rate 0.12, no calibration/tuning on
  Validation or TEST. Minimum >=4 TRAIN source songs contributing
  examples and >=10 positive/negative examples.
- Freeze decision threshold at **0.80** before evaluating results.
- Private JSON model stored in ephemeral CI runner only, never
  published as an artifact. The public artifact preserves the model
  SHA-256, TRAIN manifest SHA-256 and aggregate candidate counts.

## Independent Validation — same twelve WAVs for all three arms

1. Original shipping DSP baseline, no candidate generation.
2. Same baseline plus raw two-band GM42 proposals.
3. Same baseline plus the TRAIN-fitted learned ranker acting ONLY on
   newly proposed GM42 notes.

Matching uses the unchanged 50ms drum ontology scorer.
No note time-shifting/quantization; original Kick, Snare and standard
GM42 notes must remain in all output variants.

Predeclared acceptance **for further research only**:

- >=100 reference GM42 hits from >=3 positive recordings and >=2
  recordings containing no annotated GM42;
- GM42 recall >=+3 **absolute percentage points** over baseline;
- newly added candidate marginal Precision >=**60%**;
- aggregate GM42 Precision >=60%, drop <=10pp versus baseline;
- all-drum Precision drop <=4pp versus baseline;
- **no extra false GM42 on no-hat negative-control recordings**;
- strict Train/Validation source IDs and model/source hashes.

Fail any condition => **retain Baseline**. Pass all conditions =>
**research candidate, NOT automatic Beta/release promotion**. No
model weight redistribution or live acoustic drum microphone
accuracy claim is authorized.

## Execution & artifact privacy

Run on GitHub via a **single explicitly triggered** CPU-only workflow.
Unit tests first, restore the authentic historical Cut26 selection
artifact, verify its byte-level SHA, download official CSV, freeze
Train/Validation source selection, then fetch **only** selected WAV/MIDI
entries from the ~90GB official archive using HTTP Range.

The actual Train source WAV/MIDI, all source annotations, model
weights and transformed data MUST NOT be committed or uploaded.
The Actions artifact may contain **only** `source_selection_plan.json`
and `train_ranker_validation_results.json` with checksum references.
No ADT_STR/Basic Pitch checkpoints or noncommercial dependencies.

Relevant regression tests:
[test_hat_candidate_ranker.py](../../tests/transcription/test_hat_candidate_ranker.py)
and
[test_hat_ranker_independent_eval.py](../../tests/transcription/test_hat_ranker_independent_eval.py).
These synthetic tests establish software correctness, NOT E-GMD
accuracy. A separate results document is required after verified
real-data execution.
