# MIDIVOLT — AI Composition Knife 4: strict per-part generation

## What is actually implemented

`midivolt-compose --strict-parts` calls the existing, separately provisioned
local Text2midi subprocess **once per explicitly requested instrument role**.
Each model invocation must return exactly one pitched GM instrument track, or
one correctly marked GM drum track. If it returns the wrong type, extra tracks,
no notes, a wrong program, invalid percussion pitches, or an over-budget
sequence, the candidate is rejected. **This is not a trained instrument
recognizer or a semantic guarantee that the audible phrase sounds like the
requested instrument.** The validation checks MIDI metadata, note-range and
the already existing arrangement-lock invariants.

Requests are parsed by the Knife 3 `make_composition_plan`; per-role instructions
are passed to the generator. One instrument part is accepted only if it has
the exact expected GM program. For ambiguous requests, the user explicitly
chooses a GM program: bass 32–39, guitar 24–31, keyboard/synth 0–7 or 80–103,
woodwinds 68–79. Known violin=40, viola=41, cello=42, piano=0, string ensemble=48,
flute=73, oboe=68, clarinet=71 and bassoon=70 do not need assignments.
Drums require `is_drum=true` and percussion pitch range 35–81; they cannot
be faked by setting a pitched program number to 0.

New tracks remain separate, prefixed `MIDIVOLT AI | NN <Role>`, with each
generated musical beat mapped onto the unchanged source tempo map. Locked
original tracks, their notes and automation are untouched.
Every role is validated before the **in-memory** candidate is appended.
If later role generation fails, no partial candidate is published to disk.
Existing source, candidate and manifest paths cannot be overwritten.

**Important:** Excluding an instrument means **do not generate a new part**;
it does not erase any corresponding existing source track.

## Usage

A real inference attempt requires the same independently installed, trusted
Text2midi model, environment and local assets described in
`docs/ai-composition-k2.md`. The command does not download weights.

```powershell
midivolt-compose --strict-parts `
  --source melody.mid --prompt "請加鼓、貝斯、鋼琴、小提琴、中提琴、大提琴，不要吉他" `
  --lock 0 --program bass=32 `
  --python "C:\models\text2midi\.venv\Scripts\python.exe" `
  --checkout "C:\models\Text2midi" `
  --checkpoint "C:\models\assets\pytorch_model.bin" `
  --vocab "C:\models\assets\vocab_remi.pkl" `
  --t5-dir "C:\models\flan-t5-tokenizer" `
  --candidate candidate.mid --manifest plan.json --seed 42

midivolt-review preview --manifest plan.json
midivolt-review apply --manifest plan.json --out approved.mid --approve
```

`--strict-parts` is opt-in. Legacy `midivolt-compose` calls without this
flag use the prior all-tracks generation mode unchanged. The output plan and
hash-bound review manifest do **not** approve the candidate; an explicit
`midivolt-review apply --approve` is still required.

## Limits / commercial release gate

- Text2midi may return mixed or incorrect instruments; strict mode will
  reject those candidates instead of silently renaming them. It may be
  impractical with a model that cannot condition on exact GM program and
  separate drum channels.
- Pitch ranges/GM identifiers do not validate note accuracy, rhythm, chord
  harmony, audio quality or the true intended sound of a track.
- Each part launches the existing model inference process; throughput and GPU
  memory behavior must be measured with *actual* trusted checkpoints.
- The code uses only MIDIVOLT's existing dependencies and model subprocess
  boundary. Redistribution and commercial usage of external weights,
  training data, vocab pickles and external models require independent
  approvals. `vocab_remi.pkl` is executable-on-load and must be trusted.
- Candidate MIDI is written before hash-manifest creation, so a filesystem
  failure during manifest creation may leave an unapproved orphan candidate,
  never an approved output. Reject and regenerate; do not overwrite.
- Windows/Cubase VST3 and authentic local model inference are **not** proven
  by synthetic test fixtures.

## Tests

```shell
python -m pytest -q tests/test_part_orchestrator.py tests/test_composition_strict_cli.py
python -m pytest -q tests
```

The tests use fake deterministic providers to exercise six separate voices,
preservation of source tracks/tempo, explicit GM selection and refusal of
wrong programs, wrong drums, extra tracks, stale outputs and missing human
approval. Real model/DAW acceptance is a separate work item.
