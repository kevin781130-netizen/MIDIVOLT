# MIDIVOLT drum model candidate: ADT_STR

Status: **experimental adapter; no bundled third-party model; NOT approved for commercial release.**

## What was verified

Official upstream: https://github.com/pier-maker92/ADT_STR

The official project labels its code CC BY-SA 4.0 and documents
a drum transcription CLI based on inference.py, checkpoint paths and
WAV-to-MIDI output. It supports drum pitches, onsets and velocities.
An independent redistribution identifies converted ADT_STR weights
as CC BY-SA 4.0 as well, but this does NOT replace direct verification
of the exact checkpoint and required attribution/distribution notices.

CC BY-SA allows commercial use subject to its conditions; it is NOT
equivalent to MIT/Apache, and a separately installed subprocess does
not automatically eliminate share-alike, attribution or derivative-work
issues. A commercial integration decision requires explicit review
of the source, checkpoint, dependencies, model provenance, and the
planned distribution/deployment topology.

Do not confuse it with ADTOF: upstream ADTOF uses noncommercial terms,
so it is not an eligible drop-in commercial alternative.


## Confirmed reduced-vocabulary issue (2026-10-25)

Actual pinned upstream code uses an internal reduced percussion taxonomy
(`utils/mapping_utils.py`). Its tokenizer decoder emits those internal
codes directly when `ADTOF_mapping` is false, and `save_midi` does not
invert them to full GM. The pinned tau=0.8 training source declares
`tokenizer.ADTOF_mapping: false`; verify the downloaded checkpoint's
config independently before new evaluation.

- Vendor 35 and 36 represent separate Kick classes (both real kicks).
- Vendor 58 means **Claves**, NOT full GM58 Vibraslap and NOT GM43 Tom.
- Several hats, rides, crashes and toms have vendor-specific numeric
  positions or merged classes.

Six-song exact numeric-label results remain unchanged for audit history,
but are NOT an apples-to-apples GM performance comparison:
[read full paired-onset evidence](../benchmark/EGMD_GM35_ONSET_REPLAY_RESULTS_2026-10-25.md).

The research-only ADT_STR adapter now writes diagnostic metadata
`pitch_namespace: adt_str_vendor_custom_drum_classes` and
`standard_gm_output: false`, so callers cannot silently assume MIDI
interoperability. No automatic MIDI remapping is performed.

## Two selectable drum engines

- **dsp**: no third-party model weights. Existing local Kick/Snare/Closed Hi-hat
  heuristic. Default is still "off" to preserve earlier behavior.
- **adt-str**: optional local third-party model. MIDIVOLT never installs
  or downloads the model. Requires an explicit --research-only flag,
  an independently obtained local upstream checkout and local checkpoint.

## Prepare ADT_STR separately

Follow the upstream installation instructions in a separate Python
virtual environment, on a trusted machine where torch/torchaudio can
run. Its upstream pyproject requires Python 3.10 to 3.12 and pins
Torch/TorchAudio 2.8.0.

For a confirmed LOCAL checkout and checkpoint directory:

    python -m midivolt.transcribe \
      --input ./stems \
      --output ./midi_ai \
      --tempo 138 \
      --drum-engine adt-str \
      --adt-root /absolute/path/to/ADT_STR \
      --adt-checkpoint /absolute/path/to/ADT_STR/checkpoints/setting-tau-0.8 \
      --adt-python /absolute/path/to/adt_str_env/bin/python \
      --research-only

On Windows, supply the full path of the external environment's
python.exe to --adt-python. If any WAV is pitched, Basic Pitch is
still required in MIDIVOLT's environment. The external ADT_STR
environment is separate.

The subprocess runs the locally trusted upstream inference.py without
shell expansion or downloading from the network. Checkpoint loading and
PyTorch can be computationally expensive, so set proper hardware limits.

## DSP baseline on the very same WAV

    python -m midivolt.transcribe \
      --input ./stems \
      --output ./midi_dsp \
      --tempo 138 \
      --drum-engine dsp

Drum MIDI files have the same basename and are written with
`is_drum=True`, **which is NOT proof they use the same note-number
vocabulary**. DSP produces standard GM pitches. The pinned ADT_STR
source uses a reduced custom 26-class vocabulary for its tokenizer,
so raw output can play the WRONG instrument in a GM-compliant DAW.
Do not deliver this raw ADT_STR MIDI as a commercial GM transcription
until an explicit, reviewed vendor-to-GM mapping has been implemented.
Neither model's note times are intentionally quantized by MIDIVOLT.

## F1 A/B benchmark, same audio and reference MIDI

**Warning: this historic scorer matches exact numeric MIDI pitches,
not drum ontology classes.** Since pinned ADT_STR writes custom-label
values directly to the MIDI drum track, its original exact-pitch F1
against DSP / GM references must NOT be interpreted as a fair
model-ranking metric. Matching `is_drum=True` does not fix the
namespace mismatch. The following legacy invocation is suitable only
for inspecting old diagnostic scores; a new ontology-aligned protocol
is required before a fair comparison.

    python -m midivolt.compare_drums \
      --reference ./ground_truth/Drums.mid \
      --dsp ./midi_dsp/Drums.mid \
      --adt-str ./midi_ai/Drums.mid \
      --output ./comparison.json

Outputs:

- Note onset precision, recall and F1 at 50 ms, with one-to-one
  exact-GM-pitch matching.
- A separate per-drum-GM-pitch breakdown (no collapsing open and closed
  hi-hats into one type).
- Mean absolute onset error and signed timing bias on matched events.
- Numerical ADT_STR minus DSP F1 for **that one clip only**.

Compare total time with each conversion folder's MIDIVOLT_report.json:
the inference_seconds field is measured wall time for each stem.
ADT_STR may pay model-load overhead each stem; warm-run performance
has not been optimized yet. For a professional conclusion benchmark
multiple commercially cleared real drum recordings, long songs,
simultaneous hits and multiple genres; report macro F1 and latency
distributions, and pin the checkpoint hash.

## Validation status

Adapter and evaluator have mock-checkpoint tests, but CI intentionally
does not download or execute the actual ADT_STR weights because doing
so would introduce a large runtime and unreviewed checkpoint into the
default build. The real Basic Pitch model smoke and DSP synthetic-WAV
tests remain separate.

**There is currently NO measured ADT_STR vs DSP F1 in MIDIVOLT.**
A numerical superiority claim before testing a real installed
checkpoint against an independent test set would be misleading.

## Future production gate

1. Verify checkpoint files and SHA-256, source revision and license
   notices directly from the upstream publisher.
2. Legal/product review of commercial, share-alike, source distribution,
   model adaptations and public API deployment implications.
3. Benchmark exact-checkpoint outputs against independently licensed
   real drum audio/reference MIDI, with class-specific metrics.
4. Decide whether commercial build may opt into this model; retain
   a permissive fallback until resolved.
