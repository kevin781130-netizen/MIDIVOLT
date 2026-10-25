# K9 — workstation evidence replay, performance and Cubase handoff

## Scope and status

This is a fully offline **post-processing audit** of an existing K8
`midivolt-compose-accept` result. It does not import, run or download any
upstream model; it never starts Cubase or submits music to a cloud API.
It is suitable for a developer to run *after* authentic local checkpoint
inference and *after* a manual Cubase roundtrip.

**No authentic pretrained model or Cubase GUI has been run in automated tests.**

## 1. Run the authentic K8 model gate on your own trusted Windows workstation

Use the pinned managed model environment and trusted checkpoint/vocabulary
hashes, as described in [K8](ai-composition-k8.md). Example completed
K8 artifact names:

- `melody.mid`: original source, not edited
- `candidate.mid`: AI-generated multi-part candidate, still **not approved**
- `proposal.json`: source/candidate SHA-bound review manifest
- `acceptance.json`: source/weights hashes, inference duration, per-role
  diagnostics and explicit failure-to-release flags

If inference fails, there will be no complete acceptance report. **Do not
fabricate or copy a mock acceptance JSON to imply that a real model ran.**
The document alone cannot cryptographically prove which process produced it.

## 2. Replay the entire acceptance report offline

```powershell
midivolt-compose-audit --acceptance acceptance.json --out audit.json
```

Audit reopens K8's source/candidate MIDI and proposal. It checks the
SHA-256 digests, locked original tracks and tempo/meta maps, note counts,
instrument type/GM programs, order/track labels, K5 structural metrics,
K6 optional harmonic metrics, and exact one-accepted-attempt-per-role audit
sequence. It additionally inspects the Standard MIDI File and requires
**Type 1**, preserving separate MIDI instrument parts.

The JSON includes:
- `accepted_roles`, `generated_notes`, `model_attempts_reported`
- `attempt_acceptance_ratio`: accepted parts / reported total attempts;
  **not** a statistical instrument-adherence benchmark across prompts
- `inference_elapsed_seconds_reported`: K8's total runtime, not GPU-only time
- `reported_seconds_per_generated_note`: illustrative throughput metric
- `roles`: original per-role track program, structural/harmony scores
- `smf`: MIDI conductor/meta/event profile
- explicit `commercial_release_ready=false`,
  `independent_real_model_execution_proven=false`,
  `actual_cubase_gui_operation_verified=false`

Accepted-role checks validate only MIDI metadata; music can still be
musically wrong or incompatible with some Cubase import configurations.
Recomputed metrics are heuristic and not a ground-truth musical judgment.

## 3. Cubase roundtrip (must be done by a human)

Inspect candidate and optionally export a separate Cubase-friendly SMF:

```powershell
midivolt-cubase check --input candidate.mid
midivolt-cubase prepare --input candidate.mid --out cubase-ready.mid --ppq 480
```

In Cubase, import **cubase-ready.mid** (or candidate.mid) as a Standard MIDI
File, inspect tempo/key and all separate instrument tracks, and export an
SMF to a **different file**, e.g. `cubase-return.mid`. Compare against
the **actual imported file**, not a different preparation stage:

```powershell
midivolt-cubase compare --reference cubase-ready.mid --returned cubase-return.mid --strict
midivolt-compose-audit --acceptance acceptance.json --cubase-return cubase-return.mid --out cubase-audit.json
```

The second command intentionally compares **candidate.mid** against the
returned file because it audits the K8 acceptance artifact. If you imported
the PPQ-converted `cubase-ready.mid`, its downsampling can cause strict
candidate↔return mismatches. Treat them as audit findings, not necessarily
errors; the direct `midivolt-cubase compare --reference cubase-ready.mid`
command is the appropriate SMF export fidelity test.

A returned MIDI path and matching events cannot prove the file actually
passed through Cubase. `cubase_application_import_verified` remains
**false** in K9's machine report even with an exact event match. Document
actual DAW version, import dialog options, screenshots, observed tracks,
tempo, and MIDI playback separately before manually approving a Beta.

## 4. Commercial sign-off stays independent

K8 model page permissive license labels do not settle MidiCaps, Lakh MIDI
song-level rights or distribution terms. A K9 success **never** implies
license clearance, absence of memorization or safe redistribution of outputs.

## 5. QA

```powershell
python -m pytest -q tests/test_composition_audit.py
python -m pytest -q
```

Tests construct **synthetic MIDI plus a JSON record** with a claimed-real
field solely to exercise verifier replay. They do **not** execute a genuine
pretrained checkpoint, prove independent model execution, or open Cubase.
The test suite also ensures tampered candidates, GM track identity, altered
quality metrics, dishonest note counts, modified manifests and attempts
are rejected; no audit output can overwrite an existing file.

K9 remains on Draft PR #9. `main` is not modified.
