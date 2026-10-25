# MIDIVOLT Cut 26 — preregistered Hi-hat candidate confidence audit

Status: **research code only** until the separate new-cohort results exist.
Original production DSP: UNCHANGED. The official Test split and results
are NOT touched.

## Objective and cause

Cut 25 evaluated 24 independent official E-GMD Validation performances:
- 1211 annotated Closed Hi-hat events;
- raw dual-subband proposal recovered +27 true GM42 while adding +150 FP;
- baseline GM42 precision 71.81%, proposal 55.77%;
- no-hat negative-control FP rose from 32 to 69;
- raw proposal was **REJECTED** and must not become a release default.

The new system separates **proposing a sound** from **accepting a new MIDI
note**, and it never removes any original production DSP note.

### Source code

- [candidate confidence](../../midivolt/hat_candidate_confidence.py):
  weight-free, no statistical fitting or copyrighted embedded training data.
- [dual-band candidate integration](../../midivolt/hat_subband.py):
  optional confidence=HatCandidateConfidence(), only after new candidates
  have passed the existing dual-subband coincidence/RMS checks.
- [existing DSP integration](../../midivolt/drums.py):
  only enabled with BOTH `hat_subband_config=HatSubbandConfig()`
  and `hat_candidate_confidence=HatCandidateConfidence()`.
- [scoring](../../midivolt/hat_candidate_confidence_validation.py):
  frozen three-arm comparative assessment and candidate-only TP/FP counts.
- [real audio runner](../../scripts/egmd_hat_confidence_real.py):
  private audio use with per-WAV/MIDI SHA validation and metadata-only
  selection before any inference.

Frozen candidate features (NOT tuned on previously scored E-GMD):
- >=2.0 new-attack high-band versus mid-band power;
- >=0.32 high-band spectral flatness (noise-like attack);
- >=0.22 5.2–7.5 kHz versus 7.5–10.5 kHz energy balance;
- >=2.0 onset contrast against the preceding 50ms;
- <=0.62 high-band energy ratio 80–150ms after onset.
- Local STFT data only, finite/within range checks; insufficient
  onset history/tail is a rejected *new candidate*, not a modified note.

These rules can only **discard new proposals**; the original GM36, GM38
and GM42 note onsets, note counts and instrument pitches are unaffected
(velocity normalization of original notes may still change when new notes
are added, as the original DSP currently computes it from all events).

## Independent official Validation cohort

Official Google E-GMD v1.0.0, electronic-kit recording, CC BY 4.0 for
research evaluation; NOT acoustic mic validation and not model/weight
commercial release clearance.

- Exactly 24 fresh official **Validation** source songs, **12 beats +
  12 fills**, maximum duration 180 seconds, at least four drummers.
- Exclude ALL 36 songs from Cuts 21, 23 and 25. The prior Cut-25 plan
  is verified by its SHA-256:
  `ebbda038cbc8b4902ff2d05e8ac5bbc8288be179cad38a00246aa01df71e6fb7`.
- Select deterministically from official public metadata, before
  downloading any new selected WAV/MIDI, no annotation-driven sampling.
- Run EXACTLY three arms on the SAME selected WAVs:
  (1) production Baseline;
  (2) Baseline + raw dual-subband generator;
  (3) Baseline + identical generator + frozen confidence rejection.
- One-to-one GM42 onset tolerance 50ms under existing reduced common
  drum taxonomy. Summarize per-track TP/FP/FN, whole-drum micro scores,
  Hi-hat TP/FP/FN, changes to negative controls, runtime and provenance.
- Fail closed if confidence adds notes or removes any baseline notes.
- No official Train/Test MIDI evaluated or used to set gates.

## Predeclared pass/fail conditions

To label a result a *research-only candidate*, require ALL:
- at least 100 reference GM42 events, three GM42-positive tracks and
  two zero-GM42 control tracks;
- **>=+3 percentage points** absolute GM42 recall gain over Baseline;
- **>=60% marginal precision on NEW candidates alone**
  (`extra TP / (extra TP+extra FP)`), NOT the overall precision of
  already-correct baseline notes;
- overall GM42 precision >=60% and no worse than baseline minus 10 pp;
- all-drum precision no worse than baseline minus 4 pp;
- no new GM42 false notes on zero-GM42 control songs.

Even if all pass, no automatic promotion to MIDIVOLT's default.
The result is still based on a small electronic-kit Validation cohort.
For commercial Beta, perform independently rights-cleared direct
acoustic drum microphone validation and model-license review.

## Test/CI policy

- No ADT_STR or Basic Pitch checkpoint download.
- CPU-only NumPy, SciPy, pretty_midi, HTTP Range ZIP source reader.
- No Actions routine fan-out; one opt-in job only, turned off for
  further pushes after this study.
- Upload only selection-provenance JSON and score JSON, NEVER the WAV,
  MIDI ground truth, prediction MIDI or model weights.
- Keep earlier rejected model scores unchanged, including the failed
  +27 TP / +150 FP outcome.

Tests:
[test_hat_candidate_confidence.py](../../tests/transcription/test_hat_candidate_confidence.py)
and
[test_hat_candidate_confidence_validation.py](../../tests/transcription/test_hat_candidate_confidence_validation.py).
