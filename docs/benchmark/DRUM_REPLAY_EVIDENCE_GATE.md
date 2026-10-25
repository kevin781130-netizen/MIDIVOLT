# MIDIVOLT — Cut 16: freeze-and-replay GM35/36 evidence

Status: **offline provenance and score verification passed**, real *new* ADT_STR
inference not run in this cut. GitHub Actions deliberately not triggered.

## Why this gate exists

Original E-GMD six-song benchmark (successful):
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40148354653

The original ZIP artifact contains `research_metrics.json` and
`selection_plan.json`, **NOT predicted note-onset MIDI sequences**.
It is impossible to prove a GM35 prediction is the same underlying
kick as a missing GM36 truth from these summaries alone.

Original, unchanged results:
- DSP: TP 326 / FP 84 / FN 555, event-micro F1 = 0.505035
- ADT_STR: TP 308 / FP 177 / FN 573, event-micro F1 = 0.450952
- GM35→36: 45 unmatched predictions and 45 missing references,
  but the *same-song* maximum is only **41 pairs**.
- GM58→43: unmatched GM58 events are on **different songs**
  from the missing GM43 reference notes. Same-song upper bound **0**.

The GM35→36 number 41 is NOT a count of actually matched onset
timestamps; possible actual matches range from **0 to 41**.

## New code

- `midivolt/drum_replay_evidence.py`: compares a newly inferred
  research report to a historical report. Works on JSON or the
  *unmodified downloaded GitHub artifact ZIP*; no network, no Torch.
- `tests/transcription/test_drum_replay_evidence.py`: 10 local unit
  tests for SHA-256 provenance, exact model revision, altered sample
  identity, F1 drift, timing uncertainty and missing evidence.
- `scripts/egmd_mini_real.py`: opt-in `--baseline-report` now
  creates `drum_label_replay_evidence.json` when a new inference
  has returned actual MIDI-onset pair diagnostics.
- The research workflow's *optional output artifact list* contains
  that new JSON. No third-party WAV, MIDI or model checkpoints are
  uploaded through the evidence facility.

## Phase 1: verify historical score provenance without a model

Download the **original six-song research-results ZIP** from
the linked GitHub run, then:

    python -m midivolt.drum_replay_evidence \
      --original ./midivolt-egmd-six-results.zip \
      --output ./reports/drum_replay_readiness.json

Output should say `awaiting_actual_predicted_MIDI_onsets`.
This is a **correct result**, not a failed AI accuracy calculation.

## Phase 2: perform an independently authorized new replay

Install the same trusted, pinned ADT_STR source/checkpoint runtime
and required remote E-GMD sample reader from the previous research
protocol. This downloads only selected E-GMD clips with HTTP Range,
not the 90 GB archive.

    python -m scripts.egmd_mini_real \
      --output ./reports/egmd_replay \
      --upstream-root /path/to/ADT_STR \
      --max-samples 6 \
      --min-duration 8 \
      --max-duration 35 \
      --min-drummers 3 \
      --short-fills 2 \
      --baseline-report ./midivolt-egmd-six-results.zip \
      --research-only

This invocation executes the REAL pinned model and adds
`drum_label_replay_evidence.json` to the new model's normal scores.
**This command has not been run during this cut.** Running it
requires actual access to the external WAV archive and model weights;
this conversation's local runtime has no outbound network.

## Strict comparability rules

The replay checker refuses to claim comparable MIDI-onset evidence if:
- E-GMD held-out source-song IDs, WAV SHA-256 or MIDI SHA-256 changed;
- the model revision/checkpoint metadata changed;
- the selected source-list fingerprint changed;
- an engine is missing or reports an inference failure;
- the source is an acoustic microphone recording rather than E-GMD
  electronic-kit audio;
- the exact-GM TP/FP/FN changed for any engine/song.
- the per-song MIDI onset diagnostic disagrees with that song's
  exact-GM score.

If rerun TP/FP/FN differ, it reports
`not_comparable_replay_drift` instead of declaring a winner.
Any candidate from a sample with suspected/inconclusive time alignment
is flagged as **not confidently aligned** even if some onsets coincide.
Event coincidence does not itself prove instrument identity.

## Decision gate

Do **not** auto-map GM35 to GM36 yet. First establish actual
time-aligned event pairing on replays, then independently review the
ADT_STR output decoder and General MIDI kit specification.
GM58→GM43 is already contradicted by the original same-song counts.

Preserve the original Test-set F1 and never use held-out Test data
for tuning thresholds. Commercial checkpoint clearance is not complete.
