# MIDIVOLT

**AI-ready MIDI composition and arrangement engine.** This repository is the first working, commercially oriented core. It is not yet a DAW plugin or a text-to-MIDI generative model.

## What works in this first slice

- Read and write Standard MIDI Files with **pretty_midi** (MIT).
- Interpret lead-sheet chord symbols with **music21** (BSD-3-Clause).
- Generate separate chord and bass MIDI tracks without changing the original tracks.
- Detect a rough musical key and inspect a MIDI arrangement.
- Optionally transcribe audio to MIDI using **Spotify Basic Pitch** (Apache-2.0).
- A typed generator-provider contract for future models; **no model weights or pretrained systems are silently downloaded**.
- Windows and Linux core CI. No VST3/AU/AAX binaries yet.

## Install

Python **3.11** is used to intersect the supported versions of music21 9.x and the optional Basic Pitch 0.4.0. Use a virtual environment:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest -q
```

Linux/macOS: `python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.

Optional audio module (heavier dependencies, not part of CI):

```powershell
python -m pip install -e ".[audio]"
```

## External workstations: Sawdust and tsov

MIDIVOLT can now create target-specific **standard MIDI** files for separately installed [Sawdust](https://github.com/NeonMedusa/Sawdust) (MIT) and [tsov](https://github.com/luolianst/tsov) (AGPL-3.0):

```shell
midivolt-bridge --target sawdust --input demo.mid --out demo-sawdust.mid
midivolt-bridge --target sawdust --input demo.mid --out demo-grid.mid --quantize
midivolt-bridge --target tsov --input demo.mid --out demo-tsov.mid
```

Import the resulting MIDI in the target application's UI. `--quantize` is optional and lossy; original input files are never overwritten. The command prints a JSON compatibility report with known track, timing, and automation limitations. See [bridge documentation](docs/sawdust-tsov-bridge.md). The other applications and their native project formats are **not** bundled.

## AI editing in an external tsov Agent via MCP (experimental)

The original Apache-2.0 MIDIVOLT client can talk to a **separately installed** AGPL-3.0 tsov project through a child process. No tsov source, model weights or Python 3.12 dependency is shipped by MIDIVOLT. tsov's natural-language `edit_score` tool runs in its own environment and uses the LLM endpoint configured in tsov.

```powershell
midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" projects
midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" status --project demo
midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" edit --project demo --track 0 --feedback "Preserve the motif, add a short variation" --apply
midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" undo --project demo --apply
```

Default: read-only. Changes require `--apply`. tsov returns the **after-apply diff**; it is not a pre-approval preview. See [tsov MCP setup, protections and licensing](docs/tsov-mcp.md). Run `pytest -q tests/test_tsov_mcp.py` for protocol tests with a simulated server. Live Windows acceptance remains unverified.

## Reviewable AI arrangement candidates

**MIDIVOLT now supports a review-first multi-track arrangement workflow.** AI models or external workstations can generate a candidate MIDI; the built-in engine validates melody locks, checks changed notes and only exports an approved copy. This is a validation/editing workflow, **not yet a trained text-to-MIDI model**.

```powershell
# Work with an AI-generated MIDI candidate
midivolt-review propose --input melody.mid --candidate candidate.mid --manifest proposal.json --lock 0
midivolt-review preview --manifest proposal.json
midivolt-review apply --manifest proposal.json --out approved.mid --approve

# Or propose chords/bass from built-in deterministic arranger
midivolt-review propose --input melody.mid --chords "Fmaj7 Dm7 Gm7 C7" --candidate-out generated.mid --manifest generated.json --lock 0
```

Source and candidate hashes are checked before apply. Locked tracks preserve notes, expression and identity; tempo, meter and key maps cannot silently change. Existing output files will not be overwritten. [Review engine contract and limits](docs/arrangement-review.md).

## Optional local pretrained model generation

Two model runner adapters now call the upstream **Text2midi** Transformer (text-to-MIDI) and **Anticipatory Music Transformer** (melody-conditioned accompaniment) using local model assets in external Python environments. They do **not** download weights or install external model repositories:

```powershell
midivolt-model text2midi --python MODEL_PYTHON --checkout TEXT2MIDI_CHECKOUT --checkpoint MODEL_FILE --vocab REMI_PICKLE --t5-dir LOCAL_T5_DIR --prompt "F major romantic synth flute" --source melody.mid --out candidate.mid --manifest plan.json --lock 0
midivolt-model anticipation --python MODEL_PYTHON --checkout ANTICIPATION_CHECKOUT --checkpoint MODEL_DIR --source melody.mid --melody-program 73 --seconds 12 --out candidate.mid --manifest plan.json --lock 0
midivolt-review preview --manifest plan.json
midivolt-review apply --manifest plan.json --out approved.mid --approve
```

Each command requires real existing local paths. Choose one model command per candidate (do not reuse output names). The generated MIDI is appended to a copy of the original source, then passed to the existing locked-track review engine. No production model inference, Windows/Cubase, or VST3 acceptance has been verified yet. Read the [model installation, security and licensing guide](docs/model-adapters.md).

## Quick start

```shell
midivolt create --chords "Fmaj7 Dm7 Gm7 C7" --bpm 70 --out demo.mid
midivolt analyze --input demo.mid
midivolt arrange --input melody.mid --chords "Fmaj7 Dm7 Gm7 C7" --out arranged.mid
midivolt transcribe --input solo.wav --out solo.mid
```

The `arrange` operation deep-copies the MIDI data, retains every existing track and note, and adds separate named `MIDIVOLT Chords` and `MIDIVOLT Bass` tracks. MIDI tick/tempo mapping is used, so existing tempo maps are preserved. Chords are one bar each in **4/4 quarter-note units** by default; this is not yet a meter-aware arranger. Set `--beats-per-chord` to override.

Existing output files are protected: use `--overwrite` to replace them. Input and output may not be the same file unless explicitly overwritten.

## Current limitations / next modules

- No transformer model is connected yet. Future adapters: Text2midi and Anticipatory Music Transformer, subject to separate code/weight/data rights review and runtime benchmarks.
- MIDI file interchange with independently installed DAWs exists; no embedded DAW/VST3 instrument/effect, live MIDI routing, piano-roll UI, or MusicXML export.
- Key analysis is an estimate, not guaranteed harmonic ground truth.
- Audio-to-MIDI quality depends on source audio; Basic Pitch is best tested with isolated instruments and can fail on dense mixes.
- Chord accompaniment uses a straightforward root-position voicing; sophisticated voice leading and genre-specific arrangement are future milestones.
- User materials remain local; the application does not contact hosted AI services.

## Architecture

- `src/midivolt/arrange.py` — non-destructive MIDI accompaniment.
- `src/midivolt/theory.py` — chord parsing / rough key detection.
- `src/midivolt/audio.py` — optional Basic Pitch adapter.
- `src/midivolt/io.py` — validated MIDI file I/O.
- `src/midivolt/providers.py` — pluggable future AI generation contract.
- `src/midivolt/cli.py` — runnable command-line entry point.

## Licensing

MIDIVOLT is Apache-2.0. Third-party packages are installed as dependencies rather than vendored. See `THIRD_PARTY_NOTICES.md` for direct dependencies and licensing boundaries. Review model **weights**, data and redistribution conditions independently before adding models.
