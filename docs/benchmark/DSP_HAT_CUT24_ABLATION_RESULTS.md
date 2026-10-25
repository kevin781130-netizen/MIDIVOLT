# Cut 24 — Conservative shape filter ablation: measured outcome

**Date:** 2026-10-25  
**Verified workflow:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40197797514  
**Raw research JSON:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40197797514/artifacts/12599838909

## Research design (retrospective, not independent confirmation)

Exactly the six source performances already studied in [Cut 23](DSP_HAT_SHAPE_CUT23_REAL_RESULTS.md), from E-GMD v1.0.0 **Validation**, were extracted with the official E-GMD HTTP Range reader. The original selection JSON SHA-256 `4a3ddeb8c0e4b75a15a65a06e5e78574afa2352d0a287092f223481b52139d6e`, six source IDs and previous Conservative+shape TP/FP/FN were checked against the authentic original GitHub artifact. Research rights follow the official Google E-GMD CC BY 4.0 metadata; no third-party WAV/MIDI or model weights were uploaded.

Both arms used the **identical Conservative sensitivity parameters**, identical audio/reference MIDI, identical 26-class scoring, identical 50 ms onset tolerance, and identical production DSP implementation. Only `hat_shape_gate=None` versus `hat_shape_gate=HatShapeGate()` changed.

This is an *ablation on previously examined data*, NOT a fresh generalization result or a new tuning run. The only scope is attribution of the previous Conservative+shape result.

## Verified measured result

| Metric | Conservative unfiltered | Conservative+shape |
|---|---:|---:|
| Whole-drum TP / FP / FN | 198 / 64 / 481 | 198 / 64 / 481 |
| Whole-drum Precision | 0.755725 | 0.755725 |
| Whole-drum Recall | 0.291605 | 0.291605 |
| **Whole-drum F1** | **0.420829** | **0.420829** |
| Closed Hi-hat TP / FP / FN | **5 / 2 / 16** | **5 / 2 / 16** |
| Closed Hi-hat Precision | 0.714286 | 0.714286 |
| Closed Hi-hat Recall | 0.238095 | 0.238095 |
| Closed Hi-hat F1 | 0.357143 | 0.357143 |
| False GM42 on 5 zero-hat reference clips | 0 | 0 |

**Per-song MIDI event differences: zero, including no GM42 removals.** Conservative+shape replays the original Cut-23 aggregate results exactly. New feature fails to explain the earlier single-extra-true-hit improvement versus Baseline. The improvement is attributable to **Conservative sensitivity**, not the spectral gate, on this fixed cohort.

The 29 unit tests passed (8 retrospective ablation, 11 spectral-shape, 10 original shape-comparison regressions). GitHub Actions used a single opt-in CPU-only run; no Torch or ADT_STR model installed.

## Technical interpretation

This is a **rejection-only gate** after initial Hi-hat candidate detection. With fixed detector candidates it mathematically **cannot increase recall**; it can only remove predictions, potentially improving Precision while risking the loss of genuine hits. In this cohort, it removed **zero** events and therefore improved neither Precision nor Recall. A different or larger corpus might exercise the gate, but it has no measured value so far.

The six tracks contained only **21** Closed Hi-hat reference events from one song (other five were negative controls). No causal generalization or Beta-quality claim is justified. The last official Test DSP score remains unchanged; **production Baseline remains unchanged**.

## Next engineering focus

To *increase* Hi-hat recall, build a **new candidate-generating subband onset path** (rather than another post-filter), focusing on low-level hats overlapping kick/snare, and verify on a genuinely independent Validation cohort rich in Closed Hi-hat. Freeze the research method before scoring, include zero-hat false-positive controls, and preserve commercial-clean weight-free DSP as the product baseline. Do not retune on the same six Validation recordings again.
