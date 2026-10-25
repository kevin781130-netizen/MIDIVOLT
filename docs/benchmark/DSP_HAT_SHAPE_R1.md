# Cut 22 — Closed Hi-hat spectral-shape filtering (research candidate)

**Status:** Implementation and offline regression tests committed.
**Real-data performance:** NOT MEASURED. **Production DSP:** UNCHANGED.
**E-GMD official Test F1:** UNCHANGED.

Previous independent Validation (Cut 21) had 6 recordings and 174 Closed
Hi-hat reference events. The threshold-only aggressive setting found 8
more hats than baseline, but produced false GM42 hits on no-hat control
songs. Baseline was retained. See
[DSP_HAT_REAL_VALIDATION_RESULTS_2026-10-25.md](DSP_HAT_REAL_VALIDATION_RESULTS_2026-10-25.md).

## New independent, untrained feature

[hat_shape.py](../../midivolt/hat_shape.py) computes from the *existing*
STFT at each Hi-hat candidate, without external models, weights or
sample templates:

1. **High-band spectral flatness** (noise-like transient versus pitched
   ring in 5.2–10.5 kHz).
2. **Attack contrast** (high-band onset energy compared with preceding
   ~50 ms, to reject sustained cymbal wash).
3. **High-band tail-to-attack energy ratio** (80–150 ms after onset,
   to penalize sustained cymbals rather than short Closed Hi-hats).

The frozen unoptimized, hypothesis-level gate requires:

| Spectral feature | Frozen bound |
|---|---:|
| Minimum flatness | 0.22 |
| Minimum attack contrast | 1.60 |
| Maximum tail/attack ratio | 0.66 |

These are *engineering hypotheses*; not trained or optimized using E-GMD
held-out Test F1 or the previously seen Validation cohort. The feature
deliberately declines extremely late events without enough decay
history. That may reduce recall and must be measured rather than
described as a guaranteed quality improvement.

The application in [drums.py](../../midivolt/drums.py) is explicitly
\`hat_shape_gate=HatShapeGate()\` with any chosen
\`hat_config\`. Passing no \`hat_shape_gate\` leaves the old DSP detector
output unchanged. Kick and Snare spectral criteria and thresholds
remain untouched. GM42 remains the Hi-hat pitch; no DAW mapping changed.

## Frozen A/B study on a NEW Validation cohort

[hat_shape_validation.py](../../midivolt/hat_shape_validation.py)
predeclares four candidate arms, with the same event-level 50 ms
scoring and existing 26-class benchmark vocabulary:

| Arm | Hat sensitivity | Spectral shape gate |
|---|---|---|
| baseline | original | off |
| moderate_unfiltered | moderate from Cut 21 | off (false-positive control) |
| moderate_shape | identical moderate threshold | **on** |
| conservative_shape | conservative threshold | **on** |

No candidate or threshold may be adjusted after looking at the next
Validation results. The next dataset must contain **at least six new
official Validation performances** and at least one track with **no
GM42 reference**. The same predeclared guards from Cut 21 apply:
absolute recall gain >=0.02, Hi-hat precision >=0.60 and no worse
than baseline −0.12, all-drum precision no worse than baseline −0.05,
and **zero increase of false GM42 on the negative controls**. Even if
a shape candidate passes, it is a research candidate only; never
automatically switch the product's DSP default.

## Strict disjoint-source selection

The first official Validation run is archived at:

https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40192447040

Retrieve its \`validation_selection_plan.json\` (the same JSON is also
inside the archived \`midivolt-hat-validation-results-cut21.zip\`).
The previous source performance IDs are:

- drummer3/session1/39
- drummer7/session2/102
- drummer9/session1/12
- drummer1/session1/145
- drummer1/session2/100
- drummer7/session2/120

The new metadata sampler excludes these **by original performance ID**,
not just by kit filename, so alternate renders of old songs cannot
slip into the new study.

Create a *new* Validation selection without WAV downloads:

    python -m scripts.egmd_hat_prepare \
      --csv ./private_e_gmd/e-gmd-v1.0.0.csv \
      --output ./private_e_gmd/hat_shape_r1 \
      --exclude-plan ./previous_validation/validation_selection_plan.json \
      --count 6 --fills 2

After reviewing the official E-GMD CC BY 4.0 grant and required source
attribution, optionally extract only those six selected WAV/MIDI pairs
using HTTP Range (not the full 90 GB archive):

    python -m scripts.egmd_hat_prepare \
      --csv ./private_e_gmd/e-gmd-v1.0.0.csv \
      --output ./private_e_gmd/hat_shape_r1 \
      --exclude-plan ./previous_validation/validation_selection_plan.json \
      --count 6 --fills 2 --extract-range \
      --official-cc-by-research-review

The second command records **automated research-source verification**,
not a human legal sign-off, and explicitly does not clear distribution
rights to bundled media or ADT_STR weights.

Then run the CPU-only, **real** A/B:

    python -m midivolt.hat_shape_validation \
      --manifest ./private_e_gmd/hat_shape_r1/validation_manifest_SOURCE_LICENSE_REVIEWED.json \
      --selection-plan ./private_e_gmd/hat_shape_r1/validation_selection_plan.json \
      --output ./private_e_gmd/hat_shape_r1/hat_shape_r1_results.json

All metric outputs are local; the tool refuses previous Validation,
Test and Train sample IDs, missing rights declarations, mismatched
SHA-256 bytes and missing negative-control confidence.

## Tests and caveats

- [test_hat_shape.py](../../tests/transcription/test_hat_shape.py):
  broadband burst, tonal ring, sustained noise wash, missing tail
  history, invalid arrays, no-feature default compatibility and
  unchanged Kick/Snare under opt-in gating.
- [test_hat_shape_validation.py](../../tests/transcription/test_hat_shape_validation.py):
  disjoint source IDs, frozen four-arm test, negative control, insufficient
  material, and no silent production promotion.
- [test_hat_validation_metadata.py](../../tests/transcription/test_hat_validation_metadata.py):
  previous selection exclusion, Test plan rejection.

Run targeted tests locally, without GitHub Actions:

    python -m unittest discover -s tests/transcription -p 'test_hat_shape.py' -v
    python -m unittest discover -s tests/transcription -p 'test_hat_shape_validation.py' -v
    python -m unittest discover -s tests/transcription -p 'test_hat_validation_metadata.py' -v

**No new real E-GMD study and no Actions were run in this cut.**
Synthetic feature tests (including manually constructed STFTs) prove
only that the code behaves as specified, not that commercial music
transcription accuracy improved.

## Next decision

On the **new**, rights-reviewed Validation cohort, determine whether
shape gating recovers extra GM42 hits while eliminating false hits
from no-hat passages. If it fails even the predefined controls,
abandon this hypothesis rather than lowering a threshold until the
same source set yields attractive F1.

Never claim DAW-ready high-accuracy drum transcription based on this
alone; an independent direct-mic acoustic set, more kit coverage,
checkpoint licensing and finished multitrack integration remain.
