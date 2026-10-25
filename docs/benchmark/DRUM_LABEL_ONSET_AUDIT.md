# E-GMD drum MIDI: paired-onset GM label audit (Cut 15)

This tool answers a much narrower question than "is the AI better?":

**When ADT_STR predicts GM35 / GM58 and the reference contains GM36 /
GM43, are those *unmatched* notes actually close in time?**

Aggregate FP/FN counts are insufficient to answer that question.
The previous E-GMD six-song GitHub artifact includes summary JSON and
selection metadata, but **does not contain the original ADT_STR output
MIDI files**. Those are necessary for a real onset-pair conclusion.

## Results already established (unmodified)

Original six-song job:
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40148354653

- DSP: 326 TP, 84 FP, 555 FN; exact-pitch F1 = 0.505035
- ADT_STR: 308 TP, 177 FP, 573 FN; exact-pitch F1 = 0.450952
- Unmatched ADT_STR pitch 35 predictions: 45; missed GM36 truth: 45
- Unmatched ADT_STR pitch 58 predictions: 18; missed GM43 truth: 7

**Equal counts for GM35 vs GM36 do not prove that these are the same
onsets or the same musical instrument.** GM35/36 are both legitimate
kick labels; GM58 is Vibraslap in standard General MIDI, and a
Roland-specific pitch-58 tom mapping must be separately established.

## New paired-onset analysis

Source: [midivolt/drum_label_pairs.py](../../midivolt/drum_label_pairs.py)

Inputs: two actual, same-performance, unquantized MIDI files:
the **normalized-to-GM** reference MIDI and predicted ADT_STR MIDI.

Command:

    python -m midivolt.drum_label_pairs \
      --reference ./ground_truth/Drums_normalized.mid \
      --predicted ./model_outputs/adt_str.mid \
      --output ./reports/label_pairs.json \
      --tolerance-ms 50

Hypotheses (predicted pitch → reference pitch), all suggestions only:

- GM35 → GM36: kick family conventions.
- GM58 → GM43: potential Roland-specific tom label discrepancy.
- GM40 → GM38: alternative snare articulation.
- GM44 → GM42: pedal vs closed Hi-hat distinction.

The matcher uses the actual note onsets in seconds, never MIDI tick
distance; the reference and prediction must have the same absolute
time origin. It reserves **every original exact-GM match first**.
For each candidate pair it selects from the remaining predicted and
reference notes only and performs one-to-one maximum-cardinality
matching within 50 ms. Duplicate predicted notes cannot count twice
toward the same reference hit.

The output includes the number of candidate pairs, proportion of
extra/missed notes explained by the hypothesis, onset mean absolute
error and signed bias. Two artificial shifts (+137 and +283 ms) count
likely coincidental matches as an additional skeptical control.
With at least three low-offset, above-control matches it can mark
"suggestive_onset_evidence", but it always marks
"proves_same_instrument: false": onsets alone cannot establish timbre,
instrument identity or decoder licensing semantics.

**No pitch is changed, no MIDI exported from this diagnosis, and
no official F1 is recomputed with a candidate mapping.**

## Integration for the next permitted research execution

[scripts/egmd_mini_real.py](../../scripts/egmd_mini_real.py) now
computes a "label_timing_diagnostic" for each engine/song at the
moment the actual predicted MIDI and reference MIDI are available.

If model inference fails, it still includes an all-miss diagnostic
and retains the failed status. Report artifacts should include
aggregate counts and timing summaries, **not private source WAV/MIDI
or model weights**.

No new GitHub Actions job or automatic model download was added in
this cut. A new real-model execution is deliberately opt-in, and the
original six-song benchmark is preserved unchanged.

## Evidence still needed

Because the old job did not retain predictions, today's audit
**cannot retrospectively prove or disprove actual GM35↔36 and GM58↔43
onset coincidence** from its summary JSON alone.

Before adopting any note remapping:
1. Re-run an explicitly authorized test on the same pinned audio,
   unchanged source, model revision and reference protocol.
2. Inspect the per-song paired-onset counts for each candidate.
3. Compare to false coincidences in repetitive grooves and to the
   reference WAV/MIDI timing uncertainty (up to about 56 ms was flagged).
4. Check ADT_STR's drum-class decoder and Roland note mapping against
   publisher documentation, then define a frozen, reviewed output schema.
5. Validate any algorithm changes on a separate validation split;
   maintain the official Test split as held-out evidence.

This is **research only**; ADT_STR licensing, its exact checkpoint
provenance, and any commercial distribution implications remain
unresolved.
