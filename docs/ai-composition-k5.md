# AI Composition Engine — K5 structural quality gate and bounded retries

K5 extends **only** `midivolt-compose --strict-parts`. It does not alter
`main`, older `midivolt-compose` default generation, or approved source MIDI.

## Usage

```powershell
midivolt-compose --strict-parts --source melody.mid `
  --prompt "鋼琴、小提琴" --lock 0 `
  --python "C:\models\text2midi\.venv\Scripts\python.exe" `
  --checkout "C:\models\Text2midi" `
  --checkpoint "C:\models\assets\pytorch_model.bin" `
  --vocab "C:\models\assets\vocab_remi.pkl" `
  --t5-dir "C:\models\flan-t5-tokenizer" `
  --candidate candidate.mid --manifest plan.json `
  --seed 42 --min-structure-score 0.75 --retry-per-part 1

midivolt-review preview --manifest plan.json
midivolt-review apply --manifest plan.json --out approved.mid --approve
```

`--retry-per-part`: integer 0–3, default **1** in the strict CLI.
`--min-structure-score`: finite 0–1, default **0.75**.
The **Python orchestrator API** defaults to zero retries for backward
compatibility; explicitly pass `quality_retries=1` to enable it.

The scoring range 0..1 measures **MIDI event structure only**, with
human-readable counts and warning codes:

- exact duplicate pitch/start/end events (55% maximum penalty);
- notes outside *advisory* instrument register (35%);
- extremely short notes (20%);
- excessive event density (25%).

Penalties add and scores clamp to 0..1. These coefficients are **engineering
heuristics**, not calibrated musical-quality metrics. They cannot evaluate
melody, harmony, pleasing voicing, rhythmic expressiveness, style, emotion,
acoustic sound, transcription accuracy, or generated-note correctness.

Each requested role is generated independently, in the order selected by the
K3 planner. K4 GM/drum checks run first. Low-score and GM/drum mismatches
are retried up to the configured cap; retries use deterministic distinct
seeds when `--seed` is given. Model subprocess runtime failures, missing
assets and unexpected exceptions are **not swallowed or retried**.

On failure after the final attempt, MIDIVOLT raises an explicit error and
**does not publish a partial MIDI candidate**. The original file remains
untouched. On success the stdout JSON's `composition_plan` includes
`quality_policy` and `quality_attempts` entries with per-role seeds,
scores, warnings, acceptance and rejection reasons. JSON is visible in
stdout; it is not a signed quality certificate nor persisted into the
existing SHA-bound proposal manifest.

Performance implications: each retry causes an additional model call and
may increase total inference time/GPU usage. Text2midi may consistently
produce mixed/wrong GM program tracks. A structural score cannot fix such
models; repeated failure is a truthful rejection, never a forged track.

This module uses only MIDIVOLT-authored source and existing `pretty_midi`
dependency. Separate model weights/vocab and dataset terms must still pass
security/commercial-license review before commercial distribution.

## Validate

```shell
python -m pytest -q tests/test_part_quality.py tests/test_part_orchestrator.py tests/test_composition_strict_cli.py
python -m pytest -q tests
```

These are synthetic MIDI/provider tests. Real pretrained model, Windows,
Cubase and musical-perception validation remain outstanding.
