# MIDIVOLT vs MIDI Agent — parity audit & product-first Cut30

Date: **2026-10-26**.
Reference product: https://www.midiagent.com/features
and https://www.midiagent.com/docs (feature documentation available online).
This audit is based on repository evidence, not presumed deployment.

## Product direction

MIDIVOLT's goal is **independent functional parity** with the public,
user-observable capabilities of MIDI Agent: natural-language MIDI
creation, selected instrument roles, editable MIDI, extension, model
providers, audio transcription, DAW-host integrations. Do not copy the
other company's application code, UI assets, proprietary prompts,
design, brand or model weights. Implement commercial-clean original
functions and validate license provenance.

## Important GitHub branch discovery

- `main` has the actual product under `src/midivolt/`, CLI, pretty_midi
  SMF, music21 chord/bass arranger, review engine, real external model
  *adapters* (not bundled checkpoints), optional Basic Pitch audio-to-MIDI,
  Cubase strict MIDI interchange, model hub and Windows **developer RC**.
- `feat/drum-audit-20261025` contains a second, top-level
  `midivolt/` research package and large E-GMD drum-study corpus,
  but its tree **does not contain** the product's `src/midivolt/`,
  `pyproject.toml`, README, Windows packaging or GUI/plugin.
  Therefore it cannot safely be treated as the next product release
  branch or blindly fast-forwarded into `main`.
- This Cut30 parity slice branches directly from the existing `main` at
  `6f59efafa94841116a0e1492c05c2777ace0f0e1`. Research algorithms
  should be independently reviewed and ported into `src/midivolt/`
  where useful, not merged by replacing the product tree.
- No official MIDI Agent source code or assets were accessed/used.

## Comparison of publicly advertised functions

| User-visible requirement | Verified MIDIVOLT capability before Cut30 | Maturity |
|---|---|---|
| MIDI read/write, tracks, timing and Cubase SMF Type 1 | Core code + tests, Windows GUI acceptance incomplete | Partial |
| Original chord+bass arranger | Rule-based, lead-sheet symbols | Partial |
| Free-form prompt-to-editable melody/chords/bass/drums | External model adapter requires provisioning; no one-command full sketch | Missing |
| Existing MIDI variation/extension | Review-first plus optional external model runner, not simple in-product chat | Partial |
| AI providers: OpenAI, Claude, Gemini, local LLMs | Typed provider contract and external model hub only | Mostly missing |
| Audio-to-MIDI | Basic Pitch and separate research drum DSP; multi-instrument quality unverified | Experimental |
| VST3/AU/AAX & stand-alone graphical app | No native host plug-in/GUI binaries | Missing |
| Windows distribution | Python developer RC packages; not a finished standalone DAW plug-in | Partial |
| Commercial source/model rights | Licensing gates; third-party weights unapproved for bundled release | Incomplete |

Estimated **functional parity around 25%**, a subjective checklist
estimate and **not** an empirically calibrated progress measurement,
forecast of remaining engineering hours or claim of Beta readiness.
Overall feature count and product depth are not evenly weighted.

## Cut30 implementation — real usable improvement

New:
- [prompt_music.py](../../src/midivolt/prompt_music.py): bounded
  bilingual prompt interpretation (English/Chinese keywords); key,
  minor/major mode, bars, BPM, roles, sparse/syncopated/rising and seed.
  Deterministic original music-theory pattern generation with separate
  Chords, Melody, Bass and General MIDI Drum tracks (Kick36, Snare38,
  Closed Hat42). Each result is editable note events, not audio.
- [prompt_cli.py](../../src/midivolt/prompt_cli.py): installed
  `midivolt-prompt` entrypoint. Safe atomic .mid output.
- Existing Standard MIDI can be extended non-destructively,
  preserving original notes, CC and tempo. First slice requires
  constant original tempo and 4/4; otherwise fails explicitly.
- Same prompt + seed returns repeatable notes; a new seed can make
  variations.
- MIDI file format, not a VST/AU/AAX wrapper; **no actual LLM is called
  here**. Natural-language understanding is deliberately constrained,
  not equivalent to MIDI Agent's AI prompt parser.

After `pip install -e ".[dev]"` from this branch:

```sh
midivolt-prompt \
  --prompt "Create a full song with 8 bars in D minor at 110 bpm" \
  --out new-sketch.mid

midivolt-prompt \
  --prompt "請寫8小節 F#小調旋律 貝斯 100 BPM" \
  --seed 24 --out melody-bass.mid

midivolt-prompt \
  --input existing.mid \
  --prompt "Extend with 4 bars of sparse melody in A minor" \
  --out extended.mid
```

The first two produce distinct editable tracks. The third adds new
tracks after the old music, using the existing MIDI's original tempo,
without altering existing tracks.

## Focused next cuts (product value order)

1. **Provider-to-structured-MIDI contract:** connect a real model
   through an audited, opt-in interface (API key or explicitly installed
   local model), bounded JSON notes, deterministic validator and MIDI
   review-then-export. Never claim AI generated output on the fallback
   algorithm.
2. **MIDI editing dialogue and context:** attach MIDI, select role or
   locked tracks, ask for continuation/revoice/swing/fill, audition
   results and iterate with undo. Preserve tempo and native content.
3. **Standalone Windows GUI then VST3 host integration:** note editor,
   model picker, prompt/chat panel, drag/export MIDI; Windows/Cubase
   acceptance testing and packaging. AU/AAX later.
4. **Audio transcription** remains independent research: insist on
   actual multitrack instrument quality, licensing, source separation
   and real mic/studio evaluation, not synthetic score pass rates.

Commercial restrictions: music21 BSD-3-Clause, pretty_midi MIT; the
algorithm in this slice is newly authored. Review existing third-party
licenses and user/provider terms before paid distribution.
