# MIDIVOLT drum ontology v1 — fair common-label comparison (Cut 19)

Status: fixed source-derived taxonomy, research benchmark only.

## Why

The old E-GMD result reported DSP F1 0.505035 versus ADT_STR F1
0.450952 based on **raw numeric MIDI pitches**. Those numbers are not a
fair ranking: DSP/reference used full GM, while ADT_STR used a 26-class
*reduced numeric pitch vocabulary* but wrote the raw class IDs inside a
pretty_midi `is_drum=True` instrument.

Upstream exact source pinned:
https://github.com/pier-maker92/ADT_STR/blob/77dbef225e7029478ebfb916f20c7a00274f0f12/utils/mapping_utils.py

Its published `GM_standard_midi_to_Gm_custom_Mapping` is copied
**verbatim**, without tuning based on held-out E-GMD results, to:
[midivolt/drum_ontology.py](../../midivolt/drum_ontology.py).

## Frozen common scoring labels

Reference E-GMD Roland-specific notes are first normalized to GM using
the existing independently documented Roland mapping. Then:

- Ground-truth GM: original GM pitch -> published ADT_STR 26-class pitch.
- DSP output GM: original GM pitch -> published ADT_STR 26-class pitch.
- ADT_STR: original *vendor-reduced* pitch -> same published 26-class
  identity value, **ONLY** if the real loaded checkpoint's tokenizer
  confirms `ADTOF_mapping is False`.

Non-exhaustive important equivalences:

| Full General MIDI pitch | Name | Reduced class ID | Name |
|---|---|---:|---|
| 35 | Acoustic Bass Drum | 35 | Acoustic Bass Drum |
| 36 | Bass Drum 1 | 36 | Bass Drum 1 |
| 43, 45 | High Floor Tom / Low Tom | 41 | Floor Tom |
| 44 | Pedal Hi-hat | 43 | Pedal Hi-hat |
| 46 | Open Hi-hat | 44 | Open Hi-hat |
| 47, 48 | Two Mid Toms | 45 | Mid Tom |
| 49, 57 | Crash Cymbal 1/2 | 46 | Crash Cymbal |
| 51, 53, 59 | Ride variants | 48 | Ride Cymbal |
| 58 | GM Vibraslap | 53 | Vibraslap |
| 75, 76, 77 | Claves / wood blocks | 58 | Claves |

**Numerical class 58 is Claves, NOT GM58.** Reduced class 43 is Pedal
Hi-hat, NOT GM43 Tom. The earlier GM58→GM43 hypothesis was semantically
invalid and is not used to justify any score adjustment. GM35 and GM36
remain separate Kick classes, even though both sound like a Kick.

## Exact evaluation contract

1. Preserve raw WAV, source MIDI and raw model MIDI; never mutate them.
2. Normalize ONLY in-memory copies of note *labels* to the shared frozen
   26-class ontology. Preserve onset timestamps and velocities.
3. One-to-one same-class matching within 50 ms, identical tolerance for
   both models. No note quantization, source time-shift or output correction.
4. Include distinct TP, FP, FN, precision, recall and F1 per reduced class.
5. Publish per-song macro F1 and all-event micro F1 separately.
6. Keep historical `scores` and `performance_by_engine` **unchanged**
   as legacy numeric-label evidence; put new results in
   `ontology_scores` and `performance_by_engine_ontology`.
7. Fail closed if any GM pitch is not covered by the published 47-entry
   source table, an ADT_STR custom label is outside 35–60, or the loaded
   checkpoint does not explicitly declare `ADTOF_mapping=False`.
8. Persist source SHA and a deterministic SHA-256 of the 47-entry map.

**This is a fair comparison only for the shared reduced 26-class
task.** It is not a full-GM drum-instrument accuracy measure or a
working DAW export map. The classes merge some toms, rides and cymbals
and preserve 35 versus 36, intentionally.

## Known result limitations

Previous six-song E-GMD batch has 6 independent performances (~111 s)
from 4 electronic-kit performers. Some WAV/MIDI onset alignment is
flagged at -56/-57 ms or inconclusive. These are human performances
rendered by an electronic Roland drum kit, *not* direct microphone
recordings of acoustic drums. Class-map normalization alone cannot
resolve alignment problems or demonstrate commercial beta quality.

The output is research-only. ADT_STR model/weights licensing and
share-alike distribution implications remain unresolved.

## Run (without committing third-party WAV/MIDI/weights)

The pinned research script `scripts/egmd_mini_real.py` computes BOTH
legacy and common-ontology scores during inference. It verifies the
actual loaded ADT_STR tokenizer setting before scoring.

The original six-song artifact + model/checkpoint + WAV/MIDI hashes
can be locked as documented in
[EGMD_STAGE2_REPLAY_LOCK.md](EGMD_STAGE2_REPLAY_LOCK.md).

Do not update the taxonomy based on the official held-out TEST score.
If an ontology change is ever needed, version it, test on independent
development/validation material, and treat new TEST evaluation as a
separate protocol.
