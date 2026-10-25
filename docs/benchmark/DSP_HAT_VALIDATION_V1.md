# Cut 20 — DSP Closed Hi-hat recall: independent Validation only

Status: **engineering implementation committed, no real Validation metrics yet**.
The old official Test DSP result (**F1 0.505035**, 382 missed
GM42 Closed Hi-hat notes in the six-song electronic-kit benchmark)
is a *diagnostic motivation* ONLY. Do not optimize sensitivity against
those exact Test recordings, and do not claim F1 improvement before
independent data are actually processed.

## What changed

DSP source: [midivolt/drums.py](../../midivolt/drums.py)

The optional frozen `HatDetectionConfig` changes **only the closed
Hi-hat onset threshold and spectral acceptance**. Bass drum and snare
thresholds are untouched.

The no-argument production baseline remains the same:
- high-band flux fraction threshold multiplier: **1.00**
- 60th-percentile flux noise multiplier: **3.00**
- high spectral power share lower bound: **0.12**
- high/mid spectral power ratio lower bound: **2.50**
- RMS lower bound: **0.001**
- note pitch remains standard GM **42**
- no quantization, no additional note classes.

New file [midivolt/hat_validation.py](../../midivolt/hat_validation.py)
locks the following candidates BEFORE observing any Validation outcomes:

| Preset | Peak fraction scale | Flux noise multiplier | Min high share | Min high/mid |
|---|---:|---:|---:|---:|
| baseline | 1.00 | 3.00 | 0.12 | 2.50 |
| conservative | 0.85 | 2.65 | 0.11 | 2.20 |
| moderate | 0.70 | 2.25 | 0.09 | 1.90 |
| aggressive | 0.55 | 1.75 | 0.07 | 1.50 |

All presets retain an RMS threshold of 0.001; changing other drum
types, event times or source datasets is forbidden inside this study.
The preset map has a deterministic SHA-256.

## Evaluation population

The study uses ONLY official **E-GMD v1.0.0 Validation** performers
and their pinned WAV/reference MIDI, never Train or the six held-out
Test performances used in previous MIDIVOLT benchmark reports.

Plan generator:
[scripts/egmd_hat_prepare.py](../../scripts/egmd_hat_prepare.py)

The metadata-only planning command does **not** download a model
or the 90 GB dataset:

    python -m scripts.egmd_hat_prepare \
      --csv ./private_e_gmd/e-gmd-v1.0.0.csv \
      --output ./private_e_gmd/hat_validation \
      --count 6 \
      --fills 2

If original official Validation metadata contains enough suitable
performances, this selects **4 beats and 2 fills** with deterministic
sampling across drummers/styles. Selection depends only on public CSV
metadata, never prediction scores. If insufficient Validation
candidates exist, the operation correctly fails rather than silently
borrowing Train/Test.

Once an official WAV+MIDI pair is needed, use the same official
remote ZIP Range approach as previous E-GMD runs:

    python -m scripts.egmd_hat_prepare \
      --csv ./private_e_gmd/e-gmd-v1.0.0.csv \
      --output ./private_e_gmd/hat_validation \
      --count 6 \
      --fills 2 \
      --extract-range

HTTP 206 is mandatory; it refuses the host if it does not support
partial reads. Per-pair WAV and reference MIDI SHA-256 values are
computed. The generated file
`validation_manifest_PENDING_REVIEW.json` intentionally starts
with `rights.status=pending` and
`rights.research_evaluation_allowed=false`.

The evaluator will **not run** until an authorized human rights
reviewer checks the official CC BY 4.0 source/attribution,
the recording/MIDI permissions, then explicitly changes both fields,
providing their real reviewer identity.

Run approved local files:

    python -m midivolt.hat_validation \
      --manifest ./private_e_gmd/hat_validation/validation_manifest.json \
      --output ./private_e_gmd/hat_validation/results.json

Output stays in the private folder; do NOT upload third-party WAV,
annotation MIDI or weights to the repository.

## Predeclared selection criteria

Primary goal: improve exact GM42 Closed Hi-hat recall, while
preventing hallucinations and damaging overall drum quality.

A proposed Validation preset must have:

- At least **+0.02 absolute Hi-hat recall** versus DSP default;
- Hi-hat Precision no worse than **baseline minus 0.12**, and at
  least **0.60**;
- All-drum Precision no worse than **baseline minus 0.05**;
- At least **6 independent Validation songs**;
- At least one *negative control* sample with **zero reference GM42**
  hits; adding any GM42 false positives on those controls blocks
  the candidate.

F1, TP/FP/FN and runtime are reported for EVERY preset, including the
original baseline. Missing controls or insufficient samples give an
explicit **cannot-select-a-preset** result. Any qualified candidate
still stays development-only; the production default is **never
changed automatically**.

Main scoring uses the already frozen source-derived **26-class drum
ontology** for both reference and DSP (GM42 maps to shared class 42),
preserving exact 50 ms onset matching. This remains an electronic-kit
Validation experiment; not a universal acoustic drum claim.

## Tests and known limitations

- [test_hat_validation.py](../../tests/transcription/test_hat_validation.py):
  old default equivalence, preset validation, synthetic WAV pipeline,
  SHA checks, Train/Test isolation, missing rights, Precision guards,
  minimum song coverage and negative controls.
- [test_hat_validation_metadata.py](../../tests/transcription/test_hat_validation_metadata.py):
  held-out Test isolation, deterministic upstream Validation sampling,
  versioned plan and missing-stratum rejection.

**Synthetic fixtures are ONLY software regression tests**. They must
not be quoted as real E-GMD Validation accuracy. No new expensive
GitHub Actions workflow is triggered by this cut on
`feat/drum-audit-20261025`.

### Next evidence gate

After a rights-reviewed real Validation cohort is available, execute
the actual DSP-only comparison and review per-song GM42 TP/FP/FN.
Require a negative-control passage and stable Precision. Then freeze
the chosen setting and protocol before ONE independent Test
evaluation, never tuning on that Test output.
