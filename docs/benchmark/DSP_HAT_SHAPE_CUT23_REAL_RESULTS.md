# Cut 23 — Fresh E-GMD Validation: Hi-hat Spectral Shape A/B

**2026-10-25 | real CPU-only run succeeded:**  
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40195937126  
**Metrics-only GitHub artifact:**  
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40195937126/artifacts/12599836462

## Execution provenance

- Dataset: official **E-GMD v1.0.0 VALIDATION**, human-played MIDI rendered by an electronic Roland drumkit; **not** live acoustic microphone recordings.
- 6 new performance IDs / 3 distinct drummers / 4 beats and 2 fills / approximately **96.081 seconds**.
- Every original song ID from the historical Cut-21 Validation artifact was excluded. The actual published old-artifact ZIP was downloaded and compared to the pinned frozen exclusion set **before** retrieving any new WAV.
- Official Test and Train partitions were never used.
- Only six selected WAV/MIDI pairs fetched from the large ZIP using HTTP byte ranges; no entire 90 GB archive.
- No Torch, ADT_STR, Basic Pitch, model checkpoints, or media samples are uploaded in the metrics artifact.
- 54 related unit tests passed: existing DSP 6, previous hat Validation 15, metadata/split 12, new spectral feature 11, new comparison 10.
- Fixed four-arm configuration fingerprint: `0c3fc2ddba0314151a2fe3154228862b2fd4214914ff2f08b5702bba11eae8d5`.
- [Research plan frozen before inference](DSP_HAT_SHAPE_CUT23_PREREGISTRATION.md).

## Real results

There were **679 drum reference events**, but **only 21** GM42 Closed Hi-hat truth events. **Five of six** recordings contain no GM42 reference notes, so this cohort is excellent for false-hat negative controls but **very weak for estimating hat recall across performers**.

| Metric | Baseline | Moderate, no shape | Moderate + shape | Conservative + shape |
|---|---:|---:|---:|---:|
| All-drum TP | 197 | 199 | 199 | 198 |
| All-drum FP | 64 | 65 | 65 | 64 |
| All-drum FN | 482 | 480 | 480 | 481 |
| All-drum **micro F1** | 0.419149 | 0.422057 | 0.422057 | 0.420829 |
| All-drum Precision | 0.754789 | 0.753788 | 0.753788 | **0.755725** |
| Closed Hi-hat TP | 4 | 6 | 6 | 5 |
| Closed Hi-hat FP | 2 | 3 | 3 | 2 |
| Closed Hi-hat FN | 17 | 15 | 15 | 16 |
| Closed Hi-hat Recall | 0.190476 | **0.285714** | **0.285714** | 0.238095 |
| Closed Hi-hat Precision | 0.666667 | 0.666667 | 0.666667 | **0.714286** |
| Closed Hi-hat F1 | 0.296296 | **0.400000** | **0.400000** | 0.357143 |
| Macro per-song F1 | 0.395314 | 0.396960 | 0.396960 | 0.396247 |
| Extra GM42 FP in negative controls | **0** | 1 | 1 | **0** |

All timings CPU-only; median per clip approximately 0.018–0.020s. The test onset matching tolerance is 50ms, ontology is fixed (GM42 remains class 42), and no events were quantized.

## Pre-registered decision

The frozen gates required at least +0.02 absolute Hi-hat Recall without significant global/hat Precision loss, **and zero extra false GM42 in tracks that contain no reference GM42**.

- Moderate without shape: +0.095238 Recall, but **fails** false-hat negative control (+1).
- Moderate with shape: **identical aggregate scores** to moderate unfiltered (raw note-for-note prediction equality was not retained); fails the same negative control (+1). Spectral rejection provided **no demonstrated improvement** here.
- Conservative with shape: +0.047619 Recall, no extra negative-control false hats, Precision guardrails preserved. Meets the frozen gates and becomes a **Validation-only candidate**.
- **Official DSP production baseline stays unchanged**, even though a candidate passed.

### Crucial causal limitation

The study did **not** include a separate `conservative_unfiltered` arm. Consequently we **cannot attribute** the Conservative+shape gain to the shape feature instead of simply choosing Conservative threshold settings. Treat the candidate as *tentative* and not a new product improvement.

Further, only 21 reference hats in one track means the stated Recall gain is **one additional true note** (4→5) and is statistically fragile. Do not generalize to acoustic drum recordings, multiple drumkits, different drummers, or commercial beta accuracy. The five no-hat samples cannot improve recall reliability.

**Next engineering gate:** Perform a separate, transparent **post-hoc ablation** adding Conservative (no shape) to this existing Validation cohort as an attribution check, clearly NOT as a new pre-registered model selection score; and pre-register a **new label-coverage-aware**, disjoint Validation cohort before evaluating any future classifier change. Neither historical Test F1 nor official release claims should be modified.

## Licensing

Original official E-GMD data is CC BY 4.0 subject to required attribution and terms. The workflow performs only internal research evaluation with an explicit recorded source-license verification; it is not legal clearance for redistributing original WAV, annotated MIDI, proprietary samples, or ADT_STR model weights.
