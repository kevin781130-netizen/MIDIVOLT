# Drum WAV → GM MIDI (DSP baseline v1)

## What is supported

This is a fast, **locally executed, no-model-download** drum onset and spectral
classifier for **already-isolated drum WAV stems**. It detects candidate kick
(GM MIDI 36), snare (GM 38), and closed hi-hat (GM 42) hits. Simultaneous kick +
hat can generate two notes at the same time. Notes are unquantized; the MIDI
grid tempo **does not move onset times**.

This is a baseline DSP classifier built with NumPy/SciPy, **not a pretrained
state-of-the-art drum transcription network**. It does not claim to recognize
toms, rides, crash cymbals, open hats, rimshots, ghost notes, or complex
percussion kits. It can misclassify real snare/cymbal timbres. Do not advertise
a benchmark accuracy until a reference-annotated test set has been scored.

## Command

Install with Python 3.10 (see BASIC_PITCH.md for OS-specific setup):

    pip install -r requirements-transcribe.txt

Process an aligned folder containing Drums, Bass, Guitar, Keys and Vocal WAVs:

    python -m midivolt.transcribe --input ./stems --output ./midi --tempo 138 --drum-engine dsp

The default option is --drum-engine off, for backward-compatible and cautious
behavior. With off, drum WAVs are skipped. To process a single WAV whose name
does not mention Drums:

    python -m midivolt.transcribe --input ./DrumStem.wav --output ./midi --stem-type drums --drum-engine dsp

Output contains one "Drums.mid" per input stem, plus an aligned
MIDIVOLT_multitrack.mid with a GM-percussion-flagged (channel 10) track.
Every instrument stem remains an independent MIDI track. Original leading
silence must be preserved across stems.

Each drum stem's report includes kick/snare/closed-hat counts and an explicit
warning that no other drum type is supported. An empty/silent WAV generates
zero drum hits instead of fabricated notes. This is **not** stem separation:
provide already-isolated audio, not a full song.

## Implementation and test coverage

- scipy WAV decoding, mono summing, 22.05 kHz resampling;
- STFT positive spectral flux per kick/snare/hat frequency band;
- class acceptance using transient spectral-energy bands;
- adaptive peak threshold, suppression of repeated peaks per drum class;
- relative amplitude mapped to MIDI velocity;
- unit/integration test synthesized PCM has six reference events including
  a simultaneous kick and closed hat; this fixture measures pipeline behavior,
  not performance on real musicians.

## Licensing

This v1 adapter embeds **no external drum-model weights**. The signal-processing
libraries still need standard package/dependency license review. Do not
silently replace it with ADTOF (noncommercial upstream licensing) or other
unreviewed weights. A high-accuracy dedicated model is a separate candidate
subject to independent code, checkpoint, training-data and distribution rights
review as documented in DATASET_REGISTRY.md.

## Known gaps and next gates

1. Add **drum-event precision/recall/F1** with pitch-sensitive 50 ms onset
   matching; score every GM kit-piece independently.
2. Evaluate commercially cleared **real drum recordings** separately from
   synthetic fixture data.
3. Evaluate model candidates (including checkpoint licenses) against this
   baseline in MIDI timing, false hits, ghost-note recovery and wall-clock time.
4. Expand drum-piece classification only after measured evidence supports it.
