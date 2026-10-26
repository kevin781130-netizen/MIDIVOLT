# Cut 29 — expanded TRAIN ranker / drummer-disjoint internal holdout: actual results

**Date:** 2026-10-26.
**Successful actual CPU-only research run:**
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40266221080
**Machine-readable metrics-only artifact:**
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40266221080/artifacts/12626840381
**Decision: RETAIN ORIGINAL DSP BASELINE. The expanded ranker did not improve event-level results beyond the smaller ranker.**

## Critical population constraint found BEFORE any new scoring

Official E-GMD v1.0.0 metadata-only research run:
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40265553397

After excluding the 72 original source performances already evaluated
in Cuts 21, 23, 25, 26 and 28, eligible Acoustic Kit material was:

| Official upstream partition (per original performance ID) | Unused/eligible sources <=90s | Beats | Fills | Drummers |
|---|---:|---:|---:|---:|
| TRAIN | 699 | 196 | 503 | 9 |
| VALIDATION remaining | **40** | **0** | 40 | **2** |

This means the remaining untouched official Validation is NOT suitable
for balanced, independent GM42 Beat/Fill evaluation. Crucially, NO
previously inspected Validation source songs were secretly recycled,
no official Test content was accessed, and no score-based source
selection was used.

Instead this cut explicitly switched to **ORIGINAL TRAIN ONLY**,
using two completely withheld TRAIN drummers for an internal
group-held-out, exploratory research study. These scores must NOT
be advertised as official Validation or commercial accuracy.

## Pre-registered 96-source TRAIN experiment

The [frozen protocol](DSP_HAT_RANKER_CUT29_PROTOCOL.md) was committed
before any new WAV/MIDI scoring. Sources were selected entirely from
official public CSV metadata, original upstream split = **train**,
Acoustic Kit electronic drum rendering, <=90sec per song:

- **72 TRAIN fit recordings**: 48 Beat, 24 Fill.
- **Nested 24-song TRAIN training subset**: 16 Beat, 8 Fill,
  fully contained within the 72-source set.
- **24 source-song internal holdout**: 12 Beat, 12 Fill;
  all recordings from **drummer6 and drummer7**, entirely absent
  from BOTH model training datasets.
- One fixed classifier architecture for both models: NumPy-only
  5-feature logistic ranker, TRAIN-only normalization, fixed L2
  regularization 0.10, 900 steps, learning rate 0.12, and frozen
  acceptance threshold **0.80**.
- Four modes on the SAME 24 holdout WAV/reference MIDI pairs:
  original baseline DSP, raw dual-subband candidate generator,
  small 24-song-trained ranker, expanded 72-song-trained ranker.
- Exact 50ms one-to-one GM42 onset matching and the existing common
  26-class drum ontology. No candidate may remove/shift an existing
  note or add a non-GM42 drum pitch.
- Original E-GMD source SHA-256 hashes and model-file hashes recorded
  in private provenance. No WAV, reference MIDI, transformed features,
  or fitted checkpoint parameters committed or uploaded.

### Actual TRAIN fit population

| Population | Small model | Expanded model |
|---|---:|---:|
| Selected TRAIN performance count | 24 | 72 |
| Performance recordings with usable new candidates | **10** | **31** |
| New-candidate training examples | **124** | **361** |
| Incremental true GM42 candidate labels | 62 | 224 |
| Incremental false GM42 candidate labels | 62 | 137 |

The larger model has **2.91×** as many candidate examples and 3.1×
candidate-contributing original song performances. The data scaling
objective succeeded **as a data engineering result**.

## Actual drummer-disjoint TRAIN-internal holdout scores

24 original TRAIN internal holdout performances by drummer6 and
drummer7, **698 GM42 reference notes**, 15 tracks with some GM42
ground truth and 9 zero-GM42 negative controls.

| Measure | Baseline DSP | Raw generator | 24-song ranker | 72-song ranker |
|---|---:|---:|---:|---:|
| GM42 TP | 185 | **258** | 186 | 186 |
| GM42 FP | **75** | 185 | **75** | **75** |
| GM42 FN | 513 | **440** | 512 | 512 |
| GM42 precision | 0.711538 | 0.582393 | **0.712644** | **0.712644** |
| GM42 recall | 0.265043 | **0.369628** | 0.266476 | 0.266476 |
| GM42 F1 | 0.386221 | **0.452235** | 0.387904 | 0.387904 |
| All-drum TP | 1380 | **1453** | 1381 | 1381 |
| All-drum FP | **589** | 699 | **589** | **589** |
| All-drum FN | 3208 | **3135** | 3207 | 3207 |
| All-drum F1 | 0.420924 | **0.431157** | 0.421165 | 0.421165 |

### Candidate-only additions relative to the original DSP

| Incremental impact | Raw subband | Ranker trained on 24 | Ranker trained on 72 |
|---|---:|---:|---:|
| Added correct GM42 (TP delta) | 73 | 1 | 1 |
| Added false GM42 (FP delta) | 110 | **0** | **0** |
| Precision of new notes alone | 39.89% | **100% (only 1 event!)** | **100% (only 1 event!)** |
| Absolute GM42 recall increase | +10.46pp | +0.14pp | +0.14pp |
| Additional false GM42 across 9 zero-hat control tracks | **24** | 0 | 0 |
| Meets all internal gates | **NO** | **NO** | **NO** |

The raw generator increases recall substantially but introduces too
many false hi-hats. Both rankers eliminate false additions, at the
cost of removing almost every true extra note. **Event-level outcomes
are identical for small versus expanded ranker on this holdout.**

The proposed +3 percentage point incremental recall minimum is
NOT met (actual +0.1433pp). A Precision result of 1/1 should NEVER
be called statistical 100% accuracy.

## Conclusion and limitations

1. **Scaling TRAIN coverage succeeded**: 124 -> 361 examples,
   10 -> 31 contributing original TRAIN performances.
2. **Improvement in real event recall did not follow**:
   the small and expanded models produced exactly the same TP/FP/FN.
3. The fixed 0.80 learned-ranker admission rule remains extremely
   conservative; adjusting that threshold to improve these already
   viewed internal holdout scores would create contamination.
4. Because this was TRAIN-internal drummer-heldout research, it does
   NOT replace a fully new official Validation cohort, independent
   acoustic-mic corpus, commercial rights review, or Beta release UAT.
5. The remaining untouched official E-GMD Validation under this
   Acoustic Kit scope contains ONLY Fills by two drummers, so a new
   balanced evaluation must use an external rights-cleared corpus
   or carefully acquired new recordings (not the official Test set).

**Production DSP remains unchanged; the new learned rankers and raw
candidate generator remain opt-in research only.**

## Engineering verification and privacy

Successful run included **43 tests**:
10 new Cut29 drummer-disjoint data and integrity tests, 17 frozen
ranker TRAIN-only tests, 10 dual-band signal tests and 6 existing
baseline DSP tests. The actual 96 source-song research execution
succeeded after test gating. No ADT_STR weights or PyTorch needed.

The GitHub artifact contains exactly:
- `source_selection_plan.json`: metadata-selected source-song IDs,
  original drummer groups, dataset metadata SHA and protocol digest.
- `train_group_holdout_results.json`: aggregate/per-song scores,
  selected source file checksums, input lineage and **non-releasable**
  private model SHA-256 references.

Dataset provenance: E-GMD v1.0.0, Google LLC, CC BY 4.0,
Callender, Hawthorne and Engel (2020):
https://magenta.withgoogle.com/datasets/e-gmd .

**Next research decision:** On development TRAIN material only,
construct a within-TRAIN nested drummer-group cross-validation
to estimate candidate ranker threshold/calibration *without looking
at an evaluation group's labels*, then freeze the algorithm and obtain
a genuinely independent rights-cleared acoustic/multikit dataset
before any commercial Beta promotion.
