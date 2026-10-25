# AI Composition Engine — Knife 3: natural-language instrument planning

## Scope

`midivolt-plan` is a deterministic, no-network **planning-only** command.
It parses instrument requests in Traditional Chinese, Simplified Chinese and
English into distinct MIDI track specifications. It **never invokes a model**
or generates MIDI. It never changes the source file.

Example:

```shell
midivolt-plan --source melody.mid --lock 0 --prompt "請加入鼓、貝斯、鋼琴與弦樂，不要吉他，保留主旋律" --out track-plan.json
```

Sample fields in `track-plan.json`:

```json
{
  "schema_version": 1,
  "type": "midivolt_composition_plan",
  "locked_tracks": [0],
  "parts": [
    {"role": "drums", "is_drum": true, "gm_program_hint": null},
    {"role": "bass", "is_drum": false, "gm_program_hint": null},
    {"role": "piano", "is_drum": false, "gm_program_hint": 0},
    {"role": "strings", "is_drum": false, "gm_program_hint": 48}
  ],
  "excluded_roles": ["guitar"],
  "needs_program_selection": ["bass"],
  "requires_human_approval": true,
  "generated_midi": false
}
```

Sample above is an **abridged schema illustration**. Actual `parts`
also contain labels, explicit instrument-choice indicators and a role-specific
instruction preserving the user's full request; actual output includes
`original_prompt` and `original_track_count`.

When no output path is specified, JSON is printed to stdout. Existing output
files cannot be overwritten. The input MIDI must contain at least one track
and at least one explicitly locked source track is required. Invalid locks
fail closed.

The planner knows drum kit, bass, piano, guitar, keyboards/synth, string
ensemble, violin, viola, cello, woodwind ensemble, flute, oboe, clarinet,
and bassoon. Named individual strings/woodwinds suppress their generic
ensemble request to prevent duplicate track planning. Contradictory instrument
inclusions/exclusions are rejected. Ambiguous keyboard, guitar, generic bass,
and generic woodwind GM instrument choices are left unset (null), for human
selection rather than fabricated. GM hints use 0-based program numbering.
Drum is a separate `is_drum=true` role, not a GM pitched program.

## Safety & next step

**Not yet connected to live per-part model orchestration.**
`midivolt-compose` from Knife 2 is unchanged and still cannot guarantee
correct instrument-by-instrument generation. No model output is relabeled
as a requested instrument merely because a prompt said so. Once approved,
a later development slice can add one-part-per-request execution with
GM/drum event validation and per-track review before any acceptance.

No external music libraries, cloud LLM keys or weights are required for the
planner core. Existing MIDIVOLT dependencies are used only to load the source
MIDI in the CLI. Any actual model integration must separately clear its code,
weights, training-data, and model-use licensing conditions.

## Verify

```shell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_composition_planner.py
python -m pytest -q tests
```

Tests cover traditional/simplified Chinese and English, exclusions and lists,
substring collisions (bassoon vs bass; embassy vs bass), named string/woodwind
part granularity, contradictions, bounds/locks and CLI non-overwrite behavior.
Passing fixture tests does not prove model inference or Cubase acceptance.
