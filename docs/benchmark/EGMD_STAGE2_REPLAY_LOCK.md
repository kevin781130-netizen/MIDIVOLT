# Cut 17 — E-GMD Stage 2 replay: fail-closed pre-inference source lock

Date: 2026-10-25
Branch: `feat/drum-audit-20261025`
Normal GitHub Actions: **not triggered**.

## Historical evidence verified

Original six-excerpt E-GMD run:
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40148354653

The genuine original run ZIP has both `selection_plan.json` and
`research_metrics.json`; the plan's raw SHA-256 matches the digest
recorded in the score report. Six original WAV/MIDI pairs were pinned
in the report, together with the ADT_STR checkpoint SHA-256 and model
revision. No actual model-output MIDI note-time files were archived.

Original ZIP SHA-256:
`46b4d8938a9a966bb3a06b9a1d05dfbea643b7976292641843312d5807899043`

Original selection-plan SHA-256:
`5bf54c51379c6a0a48d84e3b65bb71174eab2dbb7c167140251eefc61de480bc`

Original metadata CSV SHA-256:
`80677e8fb00e973f33cb91ddaaf7f0cffe55359f9a76c1833ce56c84d1d92c64`

ADT_STR checkpoint SHA-256:
`f94d1773d929166e0a3f63d305975aa6667512f8a71d7706872e1f8b23ca930b`

The original Test performance cohort and exact WAV/MIDI hashes are
also captured in the downloadable `midivolt_egmd_stage2_replay_lock_readiness.json`
generated in this task; no third-party media or model weights were included.

## What changed

New module `midivolt/egmd_replay_lock.py` loads the historical ZIP and:
1. Independently recomputes raw selection-plan SHA-256.
2. Confirms its Test-only selection, original audio and MIDI file identities,
   source-song ordering, and per-file SHA-256 strings are present.
3. Validates selected metadata **before making HTTP Range ZIP requests**.
4. Validates newly extracted E-GMD WAV/MIDI hashes **before fetching or loading
   the 289 MB ADT_STR model**.
5. Verifies model/checkpoint revision and digest against the original report.
6. Fails closed on any difference.

Integration: `scripts/egmd_mini_real.py --baseline-report ./original-six-results.zip`.

Passing the lock means file identities are consistent with the old report;
it **does not** prove that audio and MIDI onsets are aligned or that any
GM35 output is the same musical hit as a missing GM36 label.

## How to run without using GitHub Actions

First preserve a local copy of the original GitHub ZIP artifact,
which has limited retention. On a trusted machine with the official
E-GMD Range reader and ADT_STR environment installed:

    python -m scripts.egmd_mini_real \
      --output ./egmd_replay \
      --upstream-root /path/to/ADT_STR \
      --max-samples 6 \
      --short-fills 2 \
      --min-duration 8 \
      --max-duration 35 \
      --min-drummers 3 \
      --baseline-report ./midivolt-egmd-six-results.zip \
      --research-only

The program saves `replay_lock_preflight.json` before model inference.
After successful inference it attempts
`drum_label_replay_evidence.json`, which compares old/new per-song
TP/FP/FN and pairs actual MIDI onsets. If scores drift, comparable mapping
claims are blocked rather than silently inventing a better F1.

## Tests actually executed

13 local `unittest` cases passed on a replica of the committed
standard-library lock module: unchanged fixture, changed metadata, wrong
source-song identity, changed WAV/MIDI hashes, mismatched checkpoint SHA,
incorrect source split/domain, and corrupt original ZIP digest.
An additional live-data-free smoke read the original GitHub ZIP and
confirmed its internal plan, model and source-hash invariants.

No new GitHub Actions run was initiated. The full integrated script
and actual ADT_STR replay remain **unexecuted in this cut**.

## Release interpretation

- DSP/ADT_STR prior exact-pitch F1 remains unchanged.
- Actual GM35→GM36 onset coincidences remain unknown.
- Neither this lock nor high-similarity MIDI onsets grant model
  commercial distribution rights or justify changing the held-out F1.
