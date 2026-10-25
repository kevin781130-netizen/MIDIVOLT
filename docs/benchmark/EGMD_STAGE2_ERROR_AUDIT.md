# Stage 2: six-song E-GMD held-out drum benchmark — error audit

2026-10-25. Original completed workflow:
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40148354653

Read-only evidence. **No threshold tuning, changing reference MIDI, note
remapping or rescoring was performed here.** The original Test split remains
held out. User-supplied comparison inputs, audio, and model weights are not
committed into the repository.

## Cohort

- E-GMD v1.0.0 Test, 6 different performances by 4 drummers,
  4 long groove beats + 2 short fills, 110.674 s total.
- Five primary musical styles, 60–138 BPM.
- Roland TD-17 "Acoustic Kit" render of human drumming.
- These are **not** microphone recordings of an acoustic drum kit.
- 881 exact-GM-pitch reference drum events.

## Original results, unchanged

| Metric | DSP v1 | ADT_STR |
|---|---:|---:|
| TP | 326 | 308 |
| FP | 84 | 177 |
| FN | 555 | 573 |
| Event-micro F1 | **0.505035** | 0.450952 |
| Song-macro F1 | **0.463150** | 0.369845 |
| Recall | 0.370034 | 0.349603 |
| Precision | 0.795122 | 0.635052 |
| Median inference/call time per excerpt | 0.0462 s | 49.9667 s |
| Full inference crashes | 0 | 0 |

**Interpretation:** DSP leads on these six samples, but *neither engine is
accurate enough* to claim high-quality drum-to-MIDI on real performances.
Very low recall means many genuine hits never become notes.

## Where the missing hits are

| GM pitch | Reference notes | DSP misses | ADT_STR misses |
|---|---:|---:|---:|
| 42 Closed Hi-hat | 461 | 382 | 369 |
| 38 Acoustic Snare | 174 | 79 | 78 |
| 40 Electric Snare | 50 | 50 | 50 |
| 36 Kick | 164 | 12 | 45 |
| 37 Side Stick | 8 | 8 | 8 |
| 43 High Floor Tom | 7 | 7 | 7 |

Hi-hat GM42 comprises 461/881 reference notes. DSP recalls only 79/461
(17.14%); ADT_STR 92/461 (19.96%). Solving Hi-hat is crucial, but
changing thresholds after looking at the official Test outcomes would
destroy the held-out benchmark's independence. Future parameter selection
must use a separate permitted **development/validation split**.

## Two distinct confounders

### 1. Audio / reference MIDI time alignment

The conservative audio-onset diagnostic flagged:

| Source performance | Status | Median WAV minus MIDI offset |
|---|---|---:|
| drummer8/eval_session/1 | Suspected offset | -55.960 ms |
| drummer1/eval_session/7 | Suspected offset | -57.224 ms |
| drummer3/session2/10 | Inconclusive (few confident transients) | N/A |
| drummer1/session1/18 | Inconclusive (few confident transients) | N/A |
| drummer7/session2/93 | No large offset detected | +2.819 ms |
| drummer7/session3/5 | No large offset detected | +14.303 ms |

At the benchmark's 50 ms onset tolerance, a real -56 ms systematic
offset would be consequential. The estimator uses only a small subset
of strong isolated onsets and is **not proof** of a systematic
offset. Independently verify recording alignment and model/reference
time origins before deciding whether rerunning a pre-registered,
corrected-protocol benchmark is justified. Do not silently move the
reference notes to increase F1.

### 2. Instrument-label schema

ADT_STR emitted 45 unmatched GM35 events while the reference has
45 missed GM36 events. It also emitted 18 unmatched pitch-58
events while the normalized reference has 7 missed pitch-43
events. These aggregate counts are **hypotheses of output/reference
label disagreement**, NOT evidence that any pair co-occurs at the
same onset. A model can instead be wrong about musical events
or timing.

GM35 and GM36 are different standard bass-drum labels.
Roland pitch58 requires explicit vendor/reference provenance: in
standard General MIDI, 58 is Vibraslap. Review the actual *upstream*
ADT_STR model decoder and the original MIDI note lists, then establish
a frozen drum-label specification **before** scoring new Test songs.

## Guardrails and disposition

New audit source: midivolt/drum_report_audit.py
(offline, standard library, exact-score consistency checks).
New tests: tests/transcription/test_drum_report_audit.py.

The audit checks:
- both engines saw exactly the same named Test performances;
- reported micro TP/FP/FN match per-song and per-GM-pitch totals;
- any broken/missing engine outputs and mismatched source identity fail closed;
- uncertainty in alignment is surfaced rather than corrected;
- label differences are presented as potential mapping cases, not silently
  changed pitches or score improvements.

**Gate: NO BETA QUALITY CLAIM.** Preserve DSP as a quick diagnostic
baseline. ADT_STR remains research-only until checkpoint licensing
and commercial deployment obligations have been reviewed.

## Recommended next implementation

1. Add a **non-destructive paired-onset label confusion analyzer**
   that opens actual predicted/reference MIDIs to verify potential
   GM35↔GM36 and Roland-vs-GM mismatches.
2. Resolve dataset time-origin evidence independently from held-out scores.
3. Build a validation-only Hi-hat recall experiment with a predeclared
   setting and unchanged Test report.

Do not compare CPU latencies as though they represent final GPU deployment
speed. ADT_STR cost includes preprocessing/inference and may vary by
song and warm-up.
