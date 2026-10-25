# MIDIVOLT Cut 27 — development-trained GM42 candidate ranker

**Stage:** Train-only ranker foundation and testable end-to-end private
TRAIN WAV/MIDI workflow. **No official E-GMD TRAIN recordings have yet
been used to fit or validate a distributable model in this cut.**
No new real-musician F1, Beta claims, or commercial checkpoint rights.

## Problem and strict safeguards

Cut 26 independently assessed 24 new E-GMD Validation performances
(3,591 annotated Closed Hi-hat notes): baseline F1 0.359991; raw new
candidate arm 0.404312; hand-tuned confidence arm 0.372280. The
confidence filter removed 113 additional true hits to prevent 71 FPs,
and scored only 48.94% marginal new-event precision. It was rejected.
**Those Validation/official Test recordings cannot be used to fit
weights, feature normalization, training labels, calibration or the
selection of a score threshold.**

## New production-compatible components

- [midivolt/hat_candidate_ranker.py](../../midivolt/hat_candidate_ranker.py):
  NumPy-only, deterministic five-feature logistic ranker; L2
  regularization 0.10, 900 fixed iterations, gradient step 0.12;
  train-only normalization; frozen threshold **0.80**. This is a
  candidate *score*, not a clinically/statistically calibrated
  probability from independent validation.
- [midivolt/hat_ranker_training.py](../../midivolt/hat_ranker_training.py):
  extract features from the same dual-subband proposed notes that
  would reach inference. First match the existing baseline GM42
  predictions against the ground-truth MIDI within 50ms, remove
  **already-explained truth**, and only then match new candidates
  one-to-one. Do not call the same hat both a baseline match and
  a new true positive.
- [scripts/train_hat_ranker.py](../../scripts/train_hat_ranker.py):
  CPU-only TRAIN WAV+MIDI reader and private model writer.
  Per-WAV/MIDI SHA-256, version, source performance identity,
  Roland-to-GM MIDI mapping and internal research permissions must
  pass before training.
- [midivolt/hat_subband.py](../../midivolt/hat_subband.py) and
  [midivolt/drums.py](../../midivolt/drums.py):
  opt-in independent ranker, rejecting only **new** GM42 notes.
  Existing DSP defaults, pitches and start/end timestamps stay
  unchanged. Ranker is mutually exclusive with the earlier manually
  gated confidence classifier.

## Five immutable inputs

1. log1p(HF energy / midband energy)
2. log1p(5.2–10.5kHz spectral flatness)
3. log1p(high-subband energy balance)
4. log1p(attack energy / preceding 50ms high-frequency energy)
5. log1p(high-frequency tail 80–150ms / attack energy)

Schema, feature order, weights, mean/scale and training manifest SHA-256
are recorded in the private model file. Missing or NaN values fail
closed; edge-window candidates are rejected.

## Training input contract

The manifest must be placed next to the private WAV/MIDI data, with:

```json
{
  "schema_version": "1",
  "dataset": "E-GMD v1.0.0",
  "split": "train",
  "samples": [{
    "source_song_id": "real_official_train_performance_ID",
    "upstream_split": "train",
    "audio_path": "private_pair_01.wav",
    "reference_midi_path": "private_pair_01.mid",
    "wav_sha256": "<real 64-char hex sha>",
    "midi_sha256": "<real 64-char hex sha>",
    "reference_midi_mapping": "roland_td11_to_gm",
    "rights": {
      "status": "approved",
      "research_evaluation_allowed": true,
      "audio_license": "actual verified source license",
      "midi_license": "actual verified source license",
      "evidence_url": "actual official license URL"
    }
  }]
}
```

Replace placeholders and include **at least 4 independent TRAIN
performances**, with at least **10 incremental true and 10 false
candidate events**. One alternate kit render of the same source
performance is NOT a second independent source. Official
validation/test or reused score-derived samples are forbidden.

Command:

```bash
python -m scripts.train_hat_ranker \
  --manifest /private/e-gmd-train/train_manifest.json \
  --output /private/midivolt-hat-ranker-train-only.json
```

The output contains weights with
`commercial_distribution_approved:false` and
`independent_validation_completed:false`.
Do not commit it to a public repo or auto-enable it.

Explicit opt-in example (only after reviewing model provenance):

```python
import json
from pathlib import Path
from midivolt.hat_candidate_ranker import HatRankerModel
from midivolt.hat_subband import HatSubbandConfig
from midivolt.drums import transcribe_drum_wav

model = HatRankerModel.from_dict(
    json.loads(Path("/private/midivolt-hat-ranker-train-only.json").read_text())
)
midi, diagnostic = transcribe_drum_wav(
    Path("drum_stem.wav"),
    hat_subband_config=HatSubbandConfig(),
    hat_ranker_model=model,
)
```

## Decision gates

- Train only on official E-GMD **Train** data and allow different
  source-song / renderer IDs only under explicit metadata verification.
- Never select the model threshold using the six old E-GMD official
  Test songs or the 60 already inspected Validation performances.
- Validate using a genuinely disjoint cohort and publish **marginal
  precision on new GM42 notes**, hit-level F1 and no-hat control
  false positives, not simply training accuracy.
- Before candidate inclusion in the product, require independent
  direct acoustic microphone drum recordings and source/model weight
  license verification. Do not apply the model automatically.

The regression suite uses self-generated synthetic features and
synthetic MIDI to check determinism, TRAIN split gates, source-byte
checksum enforcement, honest baseline-unmatched labels, confidence
model schema and unchanged defaults. Synthetic classification success
is NOT musical transcription validation.
