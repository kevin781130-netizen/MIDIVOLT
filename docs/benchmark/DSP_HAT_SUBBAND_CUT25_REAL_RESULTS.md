# MIDIVOLT Cut 25 — Dual-subband candidate detector: measured E-GMD Validation

**Date:** 2026-10-25
**Decision:** **RETAIN PRODUCTION DSP BASELINE**. The new candidate path failed quality gates.
**Successful official Validation run:**
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40199811234
**Machine-readable result artifact:**
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40199811234/artifacts/12601716951

## Research population and pre-registration

24 DISTINCT official E-GMD v1.0.0 **Validation** performances;
**15 Beats + 9 Fills**, 5 drummers, Acoustic Kit electronic drum
rendering. All **12** previously studied Validation performance IDs
(Cut 21 and Cut 23) were excluded. Zero Test or Train sample leakage.

The preregistered E-GMD metadata-only duration feasibility correction
(35 seconds -> 90 seconds maximum, before any WAV access or model scores)
and all unchanged sensitivity / precision / coverage gates are documented
in [DSP_HAT_SUBBAND_CUT25_PROTOCOL.md](DSP_HAT_SUBBAND_CUT25_PROTOCOL.md).

1211 annotated Closed Hi-hat events (GM42) distributed over
**11 positive songs**; **13 zero-GM42 negative control** performances.
The min-coverage requirements were exceeded. This comparison has much
more positive evidence than the earlier 6-song, 21-event study but is
still only Roland/electronic-kit Validation, NOT studio acoustic mics.

The dataset metadata and chosen WAV/MIDI SHA-256 are preserved in the
result JSON, with attribution to Google's E-GMD v1.0.0 CC BY 4.0.
Raw copyrighted media and model weights were not uploaded.

## Actual measured outcome, fixed 50ms / shared 26-class scoring

| Metric | Baseline DSP | Baseline + dual-subband candidates |
|---|---:|---:|
| GM42 reference events | 1211 | 1211 |
| GM42 TP | 321 | **348** |
| GM42 FP | **126** | 276 |
| GM42 FN | 890 | **863** |
| **GM42 recall** | 0.265070 | **0.287366** |
| GM42 precision | **0.718121** | 0.557692 |
| GM42 F1 | **0.387214** | 0.379292 |
| All drum TP | 2036 | 2063 |
| All drum FP | **657** | 807 |
| All drum FN | 3740 | **3713** |
| All drum precision | **0.756034** | 0.718815 |
| All drum recall | 0.352493 | **0.357168** |
| **All drum F1** | **0.480812** | 0.477215 |
| Song macro F1 | **0.386192** | 0.385814 |
| Median DSP runtime per song | **0.07239s** | 0.08567s |

The optional subband path ADDED **177 distinct GM42 candidates**. Only
**27** of these resulted in extra correct matches; **150** were extra
false positives (15.3% marginal precision). The event-level prediction
was never allowed to remove or move baseline note onsets or add any
non-GM42 events.

In 13 tracks with NO annotated GM42, baseline generated 32 false GM42
hits and the dual-subband detector generated **69** (+37).
This independently contradicts any claim that the generator is a
product-quality improvement.

## Pre-registered gate outcome

- >=100 reference GM42 hits and >=3 positive songs: **PASS** (1211, 11)
- >=2 negative-control songs: **PASS** (13)
- >=3 percentage points absolute Hi-hat recall improvement: **FAIL**;
  observed +0.022296 (~+2.23 pp)
- Hi-hat precision >=0.60, and no more than -0.10 below baseline:
  **FAIL**; 0.557692 versus 0.718121 (drop ~0.1604)
- All-drum precision no more than -0.04 below baseline:
  PASS (drop ~0.0372)
- No new false GM42 in no-hat tracks: **FAIL** (+37)

The study result reported:
\`retain_production_baseline\`, blocked by
\`insufficient_closed_hi_hat_recall_gain\`,
\`closed_hat_precision_below_guardrail\` and
\`new_false_gm42_on_zero_hat_negative_controls\`.

**No code-level tuning or post-hoc threshold changes are authorized
using this official Validation cohort**. A further candidate must use
distinctly sourced development/validation audio with preregistered
controls. Keep the official Test split and historical Test F1
untouched.

## Implementation and verification

- New opt-in high-band candidate generator:
  [midivolt/hat_subband.py](../../midivolt/hat_subband.py).
- Existing DSP integration, disabled by default:
  [midivolt/drums.py](../../midivolt/drums.py).
- Independent 24-song evaluation:
  [midivolt/hat_subband_validation.py](../../midivolt/hat_subband_validation.py).
- Audio Range-only research runner:
  [scripts/egmd_hat_subband_real.py](../../scripts/egmd_hat_subband_real.py).
- 10 subband signal/deduplication unit tests and 10 validation
  score/negative-control tests, plus 6 existing DSP baseline unit tests
  passed in the actual successful Validation job. A separate completed
  unit workflow also passed 37 DSP regression tests.

Initial unit executions caught a broken NumPy call and an overly large
weak-onset global floor; both were repaired before official WAV scoring.
Initial Validation job failed safely in metadata-only selection when
the requested 35-second window left just 2 fresh Beats. A separate
metadata-only audit guided the explicitly versioned <=90-second
selection, BEFORE reading any results.

## Next engineering choice

The problem is now **candidate precision / sound-source discrimination**,
not the mere existence of candidate-generator recall. The new
subband detector demonstrably recovers some real hits but creates
~5.6 false hits per true recovered hit on this cohort.

Do NOT simply reduce the high-frequency gate or tune to these
published Validation songs. A plausible next clean-room,
commercial-friendly research direction is **learned-on-development-only
weak-onset candidate confidence** using interpretable high-vs-mid
attack energy, synchronous snare transients, short-time envelope decay
and kit-domain controls; evaluate on a third disjoint Validation set
or authorized external recording dataset. Keep baseline shipping
unchanged. Neither engine has reached Beta-level real-drum accuracy.
