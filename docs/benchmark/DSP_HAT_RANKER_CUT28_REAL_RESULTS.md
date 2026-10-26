# MIDIVOLT Cut 28 — REAL E-GMD TRAIN fit and 12 previously unseen Validation recordings

Date: **2026-10-26**
**Successful full execution:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40259036930
**Metrics-only artifact:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40259036930/artifacts/12623249966
**Decision:** RETAIN ORIGINAL DSP BASELINE; learned ranker is research-only.

## Why this is a true independent Validation result

- All samples were selected using the official E-GMD v1.0.0 CSV metadata
  BEFORE any new WAV/MIDI were opened or training examples constructed.
- 24 distinct official **TRAIN** performances were chosen for fitting;
  12 distinct official **Validation** performances for scoring.
- Exact source-song IDs from the previous **60** Validation
  performances (Cuts 21, 23, 25, 26) were excluded.
- Historical Cut26 actual selection-plan SHA-256 was verified against
  the original run artifact:
  \`7ca54be3db2a48f54f7bf71c6791327f5bec7a9aeeeeeb396d8e0fe87d5bfcd9\`.
- The Validation subset spans **3 drummers**, has **867 annotated
  Closed Hi-hat GM42 reference events** from **6 GM42-positive songs**,
  and 6 songs with **no GM42 reference** (negative controls).
- All 3 inference arms ran on precisely the same 12 WAV/MIDI pairs
  using standard one-to-one same-label onset matching within 50 ms.
- No official TEST data were opened or scored. No threshold or feature
  setting was changed after viewing new Validation scores.

Source dataset: Google LLC E-GMD v1.0.0, CC BY 4.0:
https://magenta.withgoogle.com/datasets/e-gmd .
Human drumming rendered on a Roland electronic kit, not acoustic
drum microphones; therefore these metrics do NOT represent general
studio acoustic-kit transcription accuracy. Attribution:
Callender, Hawthorne and Engel (2020).

## Genuine TRAIN fitting

- Selected TRAIN performances: **24**
- Songs contributing at least one new-candidate training example: **10**
- New incremental candidate events extracted from TRAIN: **186**
- Positive new GM42 event labels: **89**
- Negative new event labels: **97**
- Frozen five-feature, NumPy logistic regression, TRAIN-only mean/scale,
  L2=0.10, 900 iterations, learning rate=0.12,
  fixed score threshold **0.80**.
- Original TRAIN manifest SHA-256:
  \`338b13ad177404531933bbdb9a4ad1eb4028b8c105786b0d3460ad58f53d222d\`
- Actual private TRAIN-fitted model-parameter JSON SHA-256
  (from normalized dictionary):
  \`5b29a080fd6c70696578435ee138f8986aa23e24df941e4c43b2693abc3ffea2\`

The fitted weights and ALL third-party training audio/MIDI were
kept in temporary runner storage, never uploaded or added to GitHub.
Only score JSON and source-selection/provenance JSON were uploaded.
This is not yet a commercially cleared checkpoint package.

## Actual unseen Validation metrics — 867 GM42 notes

| Metric | Original DSP | Raw dual-subband generator | TRAIN-fitted ranker |
|---|---:|---:|---:|
| GM42 TP | 113 | **122** | 116 |
| GM42 FP | **10** | 35 | **10** |
| GM42 FN | 754 | **745** | 751 |
| GM42 precision | 0.918699 | 0.777070 | **0.920635** |
| GM42 recall | 0.130334 | **0.140715** | 0.133795 |
| GM42 F1 | 0.228283 | **0.238281** | 0.233635 |
| All-drum TP | 1404 | **1413** | 1407 |
| All-drum FP | **775** | 800 | **775** |
| All-drum FN | 3786 | **3777** | 3783 |
| All-drum precision | 0.644332 | 0.638500 | **0.644821** |
| All-drum recall | 0.270520 | **0.272254** | 0.271098 |
| All-drum F1 | 0.381056 | **0.381737** | 0.381715 |
| Song-macro whole-drum F1 | 0.358174 | 0.357631 | **0.358409** |

### New note precision and no-GM42 controls

| New relative to production DSP | Raw generator | TRAIN-fitted ranker |
|---|---:|---:|
| Added matching GM42 TP | 9 | 3 |
| Added GM42 FP | 25 | **0** |
| Retained new candidate notes | 34 | 3 |
| Marginal new-candidate precision | **26.47%** | **100% (3/3 only)** |
| Absolute GM42 recall gain | +1.04 percentage points | **+0.35 percentage points** |

On **6 no-GM42 Validation songs**, false-GM42 event counts:
- Production Baseline: **0**
- Raw generator: **17**
- Trained ranker: **0**

**Critical interpretation:** Ranker 100% marginal Precision came from
only THREE correctly accepted extra notes, not a statistically
meaningful large positive sample. Calling this model "100% accurate"
would be false. The ranker is too conservative to achieve meaningful
incremental recall.

## Frozen pass/fail decision

| Preregistered research gate | Outcome |
|---|---|
| >=100 GM42 truth, >=3 positive tracks, >=2 zero-GM42 controls | PASS (867, 6, 6) |
| GM42 recall gain >=+3.00 absolute percentage points | **FAIL (+0.35 pp)** |
| New-note marginal precision >=60% | PASS but only 3 examples |
| GM42 precision >=60% and no more than -10pp drop | PASS |
| All-drum precision no more than -4pp drop | PASS |
| No new false GM42 on zero-hat controls | PASS |

Automated decision in authentic JSON:
\`retain_production_baseline\`,
blocked by \`insufficient_recall_gain\`.

**No product default changed. No Beta release recommendation.**
Do not now re-tune the logistic decision threshold to maximize these
12 inspected Validation songs. Any next model needs a new, prospectively
declared development experiment and entirely untouched downstream
Validation/Test evidence. The next model's score quality also needs
validation across kit renders and direct acoustic microphone datasets.

## Engineering verification and traceability

The final successful GitHub Actions run completed **55 tests**:
17 Train-only ranker, 10 independent Validation and prior-song
exclusion tests, 12 acoustic confidence feature tests, 10 subband
candidate tests, 6 original DSP compatibility tests.

An initial run was rejected at the import stage due to an outdated
test helper import; this was fixed before accessing any real source
WAV and independently tested again. The successful job completed
both actual TRAIN fitting and the separate Validation study.

Public ZIP artifact sha256:
\`66fe590b7b9b989698fb5e5128c062bab26e97a65aafa50c2d4cdfe1b9df5a0f\`.
It contains ONLY \`source_selection_plan.json\` and
\`train_ranker_validation_results.json\`. No audio/MIDI or model
weights are included.
