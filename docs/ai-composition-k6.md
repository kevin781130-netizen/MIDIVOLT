# AI Composition Engine — Knife 6: optional symbolic harmony analysis

## What K6 adds

K6 adds explicit-context music theory diagnostics to K5's strict, separate-track
AI generation. Unlike K5's duplicate-note and density checks, it evaluates
declared tonality, chord symbols, large melodic leaps, and intervals against
*locked reference tracks*.

**No key or chord progression is guessed.** No external trained musical
correctness judge or harmonic listening model is bundled. All heuristics are
advisory by default. A user must explicitly request a harmony score threshold
to reject/retry; this may reject intentional dissonances or jazz alterations.

## CLI example

```powershell
midivolt-compose --strict-parts --source melody.mid `
  --prompt "鋼琴、小提琴" --lock 0 `
  --python "C:\models\text2midi\.venv\Scripts\python.exe" `
  --checkout "C:\models\Text2midi" `
  --checkpoint "C:\models\assets\pytorch_model.bin" `
  --vocab "C:\models\assets\vocab_remi.pkl" `
  --t5-dir "C:\models\flan-t5-tokenizer" `
  --harmonic-key "C major" --harmonic-chords "Cmaj7 Am7 Dm7 G7" `
  --beats-per-chord 4 --min-harmony-score 0.7 `
  --retry-per-part 1 --seed 42 `
  --candidate candidate.mid --manifest plan.json

midivolt-review preview --manifest plan.json
midivolt-review apply --manifest plan.json --out approved.mid --approve
```

For **advisory-only** diagnostics (recommended initially), omit
`--min-harmony-score` while keeping explicit `--harmonic-key` and/or
`--harmonic-chords`. Each generated part receives those constraints in
its model prompt; the generated MIDI is independently measured against them.

- `--harmonic-key`: accepts named tonic + `major` or `minor`,
  e.g. `C major`, `Bb major`, `F# minor`.
  `minor` means **natural minor**, not harmonic/melodic minor.
- `--harmonic-chords`: existing `music21` / `midivolt.theory.parse_chords`
  lead-sheet symbols. Does not infer or alter the original song's harmony.
- `--beats-per-chord`: quarter-note beat duration for every supplied chord,
  starting at song tick zero. Default 4; there is **no implied progression
  looping**, rubato/bar alignment detection or automatic meter-awareness.
- `--min-harmony-score`: opt-in 0..1 threshold. Requires a specified key
  and/or chords. Score is a heuristic, not musical quality or correctness.
- `--retry-per-part`: K5 limited retry count 0..3. Used for declared
  harmony threshold violations as well as GM/structure failures. GPU/model
  runtime crashes are not retried.

The score penalizes notes outside a declared scale (35% possible penalty),
sustained non-chord notes starting exactly on a chord's initial strong beat
(50%), and monophonic-style melodic leaps greater than an octave (10%).
These weights are deliberately conservative heuristics, **not evidence
of objectively good or bad composition**. Short non-chord notes and simple
passing tones are not hard-rejected. Overlap by sustained semitone with a
locked original pitched part is recorded **only as an advisory warning**,
not a forced rejection. Drum pitches skip tonal harmony analysis entirely.

Each per-role quality attempt now includes `harmony_metrics` and retains
the K5 `metrics` event-structure diagnostics, seed, and rejection reason.
The `quality_policy` includes declared key/chord symbols, beats-per-chord,
minimum score and whether harmony gating was enabled. The existing
`midivolt-review` approval remains mandatory; no generated output is
silently merged into `main` or the source MIDI.

**Limitations:** chord tones alone cannot prove voice leading, musical
phrasing, chord inversions, jazz passing tones, valid suspensions, harmonic
minor, modulation or correct instrumental performance. Since note onsets,
rather than full sustained overlap, determine chord membership, long held
notes across chord boundaries can be mischaracterized. Warning counters
are not musician-reviewed ground truth.

## Tests and release gate

```shell
python -m pytest -q tests/test_harmony_quality.py tests/test_composition_strict_cli.py
python -m pytest -q tests
```

The tests exercise the explicit-key grammar, chord parsing, beat-indexing,
non-chord tension vs short notes, non-looping progressions, warning-only
semitones/leaps, drums bypass, fail-closed input validation, bounded
retry and refusal to publish without separate human approval.

**Real trained-model inference, Windows, Cubase, commercial model rights
and trained musical evaluation are NOT validated by these fixture tests.**
No music21 API or model code is copied; the orchestration layer is MIDIVOLT
authored and reuses the existing dependency and model isolation boundaries.
