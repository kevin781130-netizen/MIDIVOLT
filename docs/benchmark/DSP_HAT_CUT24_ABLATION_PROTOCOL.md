# Cut 24 — Conservative Shape A/B Attribution Protocol

**Purpose:** determine whether the spectral-shape gate caused the apparent Conservative+shape benefit in the already-evaluated Cut-23 E-GMD Validation recordings. This is a **retrospective ablation**, not independent confirmation, parameter search, or an opportunity to switch MIDIVOLT's production default.

## Frozen controls before execution

- Source: exact 6 E-GMD v1.0.0 Validation tracks from the successful [Cut-23 run](https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40195937126), not Train or Test. All six selected source IDs and byte-level original `validation_selection_plan.json` SHA-256 `4a3ddeb8c0e4b75a15a65a06e5e78574afa2352d0a287092f223481b52139d6e` must match.
- The same WAV and reference MIDI are used for both arms, after verifying downloaded asset hashes against their own manifest. Source selection and previous score summary are restored from the actual prior Actions artifacts.
- Both arms use **exact same Conservative sensitivity** from the original study. The **only** changed dimension is `hat_shape_gate=None` versus `HatShapeGate()`. No retuning.
- Check the reproduced Conservative+shape TP/FP/FN is exactly identical to the archived original Cut-23 `hat_shape_results.json`. If not, refuse all attribution claims.
- Quantify per-song GM42 event removals; verify that gate **cannot add** any notes or remove any non-GM42 notes. Count TP, FP, FN, Precision, Recall, F1 for both arms and the five no-GM42 reference tracks.
- No false confidence: these six recordings were used for the earlier study. Thus **regardless of the ablation outcome, no automatic feature promotion or Beta quality claim is permitted**.
- No pretrained model, no third-party raw WAV/MIDI artifact upload, no full E-GMD 90 GB ZIP download. CPU-only, explicitly one-off GitHub job.

The research runner is [`midivolt/hat_shape_ablation.py`](../../midivolt/hat_shape_ablation.py), 8 targeted offline tests are in [`tests/transcription/test_hat_shape_ablation.py`](../../tests/transcription/test_hat_shape_ablation.py). GitHub job: [`hat-conservative-ablation.yml`](../../.github/workflows/hat-conservative-ablation.yml).

### Decision criterion

If **both arms produce the same matched GM42 notes, misses and false hits**, the spectral feature did not cause the reported increase on this cohort; improvement came from threshold adjustment. If the filter removes false positives and/or correct hits, report both sides of the trade-off without moving the original Test baseline. Any apparent causal result still requires a larger *independent* Validation or acoustic recording cohort before product release.
