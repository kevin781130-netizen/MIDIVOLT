# Cut 26 — Candidate-confidence independent E-GMD Validation: actual results

**Date:** 2026-10-25
**Source run:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40201094578
**Machine-readable original artifact:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40201094578/artifacts/12601269711
**Decision:** **RETAIN ORIGINAL DSP BASELINE**, do not promote confidence filter.

## Executed cohort and chain of custody

- 24 **new** official E-GMD v1.0.0 **Validation** performances;
  **12 beats, 12 fills, five drummers**.
- Previously evaluated 36 Validation performances excluded by exact
  original source IDs (Cuts 21/23/25); original Cut-25 selection plan
  SHA-256 was checked against the actual original GitHub ZIP:
  `ebbda038cbc8b4902ff2d05e8ac5bbc8288be179cad38a00246aa01df71e6fb7`.
- 3591 reference GM42 Closed Hi-hat hits across **11 positive tracks**,
  plus 13 independent tracks with NO reference GM42.
- Source Wave/MIDI pair SHA-256s and metadata selection were recorded.
  Only metric and selection JSON were uploaded, not WAV/MIDI/models.
- Original Google E-GMD data is CC BY 4.0 research material,
  electronically rendered Roland drum kit, **not acoustic microphone audio**.
- Exact same sample IDs, sample bytes and 50ms one-to-one drum scoring
  for three lanes: original DSP; raw dual-subband candidates; and
  raw dual-subband plus frozen confidence filter.
- No original official Test samples were scored or used to tune rules.

## Measured head-to-head

| Statistic | Production baseline | Raw dual-subband | Confidence-filtered |
|---|---:|---:|---:|
| All-drum TP | 4567 | 4726 | 4613 |
| All-drum FP | 2383 | 2502 | 2431 |
| All-drum FN | 12206 | 12047 | 12160 |
| All-drum precision | **0.657122** | 0.653846 | 0.654884 |
| All-drum recall | 0.272283 | **0.281762** | 0.275025 |
| **All-drum F1** | 0.385027 | **0.393817** | 0.387370 |
| Hi-hat TP | 835 | **994** | 881 |
| Hi-hat FP | **213** | 332 | 261 |
| Hi-hat FN | 2756 | **2597** | 2710 |
| Hi-hat precision | **0.796756** | 0.749623 | 0.771454 |
| Hi-hat recall | 0.232526 | **0.276803** | 0.245336 |
| **Hi-hat F1** | 0.359991 | **0.404312** | 0.372280 |
| Song-macro whole-drum F1 | 0.361940 | **0.364255** | 0.362944 |
| Median per-song DSP time | **0.1018s** | 0.13597s | 0.1362s |

### Candidate-only (marginal) precision — the critical metric

| Newly generated GM42 relative to baseline | Raw | Confidence |
|---|---:|---:|
| New correct GM42 notes | **159** | 46 |
| New wrong GM42 notes | 119 | **48** |
| Marginal new-note precision | 57.19% | **48.94%** |
| Absolute Hi-hat recall increase | +4.43 pp | +1.28 pp |

The confidence filter rejected **184 new generated events**
(113 true positive matches and 71 false positives). It successfully
removed many unwanted candidates but also lost too many true hats.
One-to-one matching and overlap may affect counts at the event level;
these are measured differential TP/FP against the same baseline.

### Negative control

Across **13** tracks with no reference GM42:
- Original baseline: **2** GM42 false positives.
- Raw generator: **16** GM42 false positives.
- Filtered generator: **2** GM42 false positives.

Thus the filtered version satisfies *no new false GM42 in zero-hat
passages*, which the raw candidate generator did not.

## Preregistered gate outcome

The study precommitted BEFORE scoring to:
- >=100 reference GM42, >=3 hat-positive songs, >=2 no-hat controls: **PASS**
  (3591 / 11 / 13)
- >=3pp absolute Hi-hat recall improvement: **FAIL** (only +1.28pp)
- >=60% marginal precision *on new candidates alone*: **FAIL** (48.94%)
- Full Hi-hat precision >=60% and no more than 10pp drop: **PASS**
- Full-drum precision no more than 4pp drop: **PASS**
- No added GM42 false positives on tracks with zero GM42 reference: **PASS**

**Gate result:** `retain_original_DSP_baseline`, blocked by
`insufficient_recall_improvement` and
`poor_marginal_precision_of_new_notes`.

Passing the other controls is NOT permission to ignore the failing
ones. Production code default is unchanged. New feature is opt-in
research only, not an approved Beta feature.

## What these results actually mean

The raw subband detector demonstrates real improved Hi-hat recall in
this particular cohort (159 additional matched hits), but adds
unacceptable false notes in no-hat passages. The new confidence filter
protects those negative controls but discards 113 of 159 recovered
true hits, showing why a single threshold-based rejection stage
cannot solve the recall/precision trade-off here.

Neither performance is a reliable commercial solution for real
acoustic drum microphone signals; all scores use electronic-kit data.

The next responsible experiment is a *development-trained,
held-out-validated* candidate-ranker or a non-weighted multi-class
instrument discriminator with a separately collected set of
annotated true/false candidate events and independent split by
performance/drummer. Do NOT tune five confidence thresholds on
these 24 already evaluated Validation songs. Reserve an entirely
disjoint Validation/Test domain for subsequent evaluation.

## Engineering verification

The successful GitHub run completed 40 related regressions:
- 12 acoustic-feature synthetic tests
- 12 independent-cohort safety and marginal precision tests
- 10 prior dual-subband DSP tests
- 6 baseline drum DSP tests

One earlier attempted run encountered a bad test fixture that
invented a new note inside a reject-only classifier; the safety
contract correctly rejected it. The fixture was corrected to use
a false note already proposed by the raw engine. The successful
research execution retained code and data provenance.

Only CPU NumPy/SciPy/pretty_midi and remote official ZIP range reader
were used; no proprietary or research-only ADT_STR weights were loaded.
