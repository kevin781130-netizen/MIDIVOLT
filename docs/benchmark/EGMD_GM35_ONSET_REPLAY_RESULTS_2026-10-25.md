# Cut 18 — Real MIDI onset replay and ADT_STR drum vocabulary finding

Date: 2026-10-25  
Source run: https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40186815434  
Artifact: https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40186815434/artifacts/12596770562  
Original frozen benchmark: https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40148354653

## Execution and dataset identity

The six original **E-GMD v1.0.0 held-out TEST performances** were replayed on
Linux CPU with the pinned ADT_STR setting-tau-0.8 checkpoint. The original
GitHub artifact ZIP was obtained in the job and verified **before** model
inference. All of the following checks passed:

- Original selection-plan byte-level SHA-256 and official metadata CSV hash
  reproduced.
- Exact six source-song IDs and original order reproduced.
- Every independently Range-extracted WAV and original MIDI SHA-256 matched
  the previous job.
- Pinned upstream source revision and model-weight SHA-256 matched.
- **All per-song DSP and ADT_STR TP/FP/FN were identical** to original run.
- Every newly generated onset-pair diagnostic reproduced that song's original
  exact-pitch matched TP/FP/FN.

Original unchanged score:

| Metric | DSP | ADT_STR |
|---|---:|---:|
| TP | 326 | 308 |
| FP | 84 | 177 |
| FN | 555 | 573 |
| exact-label micro F1 | 0.505035 | 0.450952 |

These are preserved **historical scores from a mixed label namespace**,
not an apples-to-apples comparison of the correct instrument vocabulary.
Do not recommend one engine as universally more accurate using this F1.

## Real event onset pairing, not aggregate count coincidence

Each ADT_STR prediction was matched first to same-label truth within 50 ms
under the original scoring policy. Only previously **unmatched** notes were
then compared across proposed labels, one-to-one.

| Original TEST performance | GM35→36 actual pairs | Old same-song maximum | Audio/MIDI alignment QC |
|---|---:|---:|---|
| drummer3/session2/10 | 3 | 3 | insufficient confident events |
| drummer7/session2/93 | 12 | 14 | no large offset detected (+2.819 ms) |
| drummer8/eval_session/1 | 9 | 11 | suspected -55.960 ms |
| drummer1/eval_session/7 | 9 | 13 | suspected -57.224 ms |
| drummer7/session3/5 | 0 | 0 | no large offset detected (+14.303 ms) |
| drummer1/session1/18 | 0 | 0 | insufficient confident events |
| **Total** | **33** | **41** | Only 12 of 33 events from alignment-QC-clear clips |

GM35→36 real-time overlap is strongly suggested in some songs, and most
candidate pairs have low onset timing error, but this **does not establish
instrument identity or authorize a re-label**. Null-shift controls reduce
some coincidence explanations but are not a substitute for an independent
timbre/decoder audit.

GM58→43 produced **0 actual same-song onset pairs**, confirming the
earlier zero theoretical same-song upper bound. The hypothesis is not
supported on these six performances.

## Critical new finding — ADT_STR note values are NOT a complete GM namespace

Official ADT_STR upstream at the **exact pinned source revision**
`77dbef225e7029478ebfb916f20c7a00274f0f12`:

- `modules/midi_tokenizer.py`: token decoder emits model *custom* pitch
  numbers directly when `ADTOF_mapping` is false.
- `configs/train/setting-tau-0.8.yaml`:
  `tokenizer.ADTOF_mapping: false` at the pinned source revision.
- `utils/mapping_utils.py`: original GM percussion codes are converted
  into a reduced internal vocabulary. In that vocabulary **35/36 remain
  separate Kick classes**; **58 denotes Claves**, rather than standard
  GM58 Vibraslap or GM43 Tom. Many other kit pieces have reduced IDs,
  e.g. pedal/open hi-hat, crash, ride and merged tom classes.
- `adt_transcriber.py`: `save_midi` writes the decoded pitch numbers
  into the resulting `pretty_midi` drum instrument **without first
  converting the custom vocabulary back into full GM**.

Official code references:
- https://github.com/pier-maker92/ADT_STR/blob/77dbef225e7029478ebfb916f20c7a00274f0f12/modules/midi_tokenizer.py
- https://github.com/pier-maker92/ADT_STR/blob/77dbef225e7029478ebfb916f20c7a00274f0f12/utils/mapping_utils.py
- https://github.com/pier-maker92/ADT_STR/blob/77dbef225e7029478ebfb916f20c7a00274f0f12/configs/train/setting-tau-0.8.yaml
- https://github.com/pier-maker92/ADT_STR/blob/77dbef225e7029478ebfb916f20c7a00274f0f12/adt_transcriber.py

We have NOT independently recorded the actual local checkpoint's
`tokenizer.ADTOF_mapping` at runtime in the previous score artifact,
so that particular checkpoint setting should still be asserted in the
next instrument-vocabulary-aligned evaluation.

**Consequences:**

1. The earlier "GM58→GM43 tom mistake" hypothesis was conceptually
   misframed: vendor custom pitch58 corresponds to Claves, not GM58.
2. The original exact numeric-pitch F1 does not fairly compare the
   ADT_STR custom-label MIDI and standard-GM E-GMD reference/DSP MIDI.
3. Directly exporting a custom-label ADT_STR note 58 as "GM drum 58"
   to a DAW will *render a different instrument* (Vibraslap in GM).
   This is a real output-interoperability issue requiring a documented
   mapping/namespace gate before commercial use.

## Decision and next independent benchmark

- Original scores and original MIDI data remain unchanged, and no mapping
  is applied to held-out Test results in this cut.
- Do not silently map all GM35 to GM36; both are valid separate Kick
  categories in the upstream taxonomy. Family-level onset evaluation
  could legitimately compare kick recall as an *additional* metric.
- **Next** establish a shared, fully documented drum-class ontology:
  GM source/reference and MIDIVOLT DSP predictions vs ADT_STR vendor
  26-class labels. Validate on a separate development split, freeze the
  mapping and metrics, then evaluate the Test split once with both
  exact-GM legacy and ontology-matched results kept side by side.
- ADT_STR licensing/weights commercial approval remains unresolved.

The artifact ZIP contains only the six-source selection plan,
replay provenance, JSON evaluation, and paired-onset count diagnostics;
no third-party WAV, MIDI or weights were redistributed.
