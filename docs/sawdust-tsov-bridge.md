# MIDIVOLT ↔ Sawdust / tsov: first interoperability bridge

**Scope:** transport existing MIDI arrangements into other DAWs, without copying their code. This is not a native project converter or a live audio/VST bridge.

## How to use (Python 3.11 MIDIVOLT environment)

1. Prepare an original MIDI with MIDIVOLT:
   `midivolt create --chords "Fmaj7 Dm7 Gm7 C7" --bpm 70 --out demo.mid`
2. Prepare a Sawdust-readable SMF:
   `midivolt-bridge --target sawdust --input demo.mid --out demo-for-sawdust.mid`
3. In **Sawdust**, use its MIDI import UI to open `demo-for-sawdust.mid`.
4. For the separately installed **tsov** workspace:
   `midivolt-bridge --target tsov --input demo.mid --out demo-for-tsov.mid`
5. In **tsov web** (`tsov web --host 127.0.0.1 --port 8790`), import the resulting MIDI into an editable project.

**Optional:** add `--quantize` for Sawdust to snap notes to 24 grid steps per quarter note; this is lossy and edits *only the exported copy*. Omit it to keep original timing in the outgoing SMF (Sawdust will snap imported notes to its internal grid).

The command returns JSON: target, output, track/note counts, quantized note count, known fidelity warnings.

## Validated interfaces and limitations (upstream source reviews)

**Sawdust** (https://github.com/NeonMedusa/Sawdust):
- Zig 0.16 / Windows. `src/midi.zig` implements Standard MIDI File parsing and writing. The parser groups notes by channel and rounds to 24 steps/quarter. It recognizes initial pan CC10; further CC automation and pitch bends should not be assumed preserved.
- `pretty_midi` uses 15 pitched MIDI channels and channel 10 for drum tracks; channel reuse on large sessions merges tracks on the Sawdust side.
- Sawdust `.saw` is an application-specific project, **not** written by this bridge. MIDI import is not a full project transfer. VST3 state, mixer and audio tracks will not move.

**tsov** (https://github.com/luolianst/tsov):
- Python 3.12 in its own venv, Windows-first. Its `tsov/midi/import.py` reads Standard MIDI files through pretty_midi. It currently imports the initial tempo and first time signature only.
- tsov WebUI and its optional MCP server are *independently installed services*. This bridge only exports a MIDI for its existing user-facing import; it **does not** invoke tsov MCP tools or copy tsov code into MIDIVOLT.
- tsov's dependency stack and optional transcription models are not installed by MIDIVOLT. Note/pitch-bend/CC or native project state round-trip is not guaranteed.

## Commercial licensing boundary

- Sawdust **MIT**: future reuse of its self-contained MIDI/UI/DSP modules is technically possible if license and attribution are retained. This first bridge imports **no** Sawdust source.
- tsov **AGPL-3.0**: not copied, linked or vendored into MIDIVOLT. Users operate tsov independently and exchange standardized MIDI files. Further service/MCP integration and distribution arrangements require a separate AGPL compliance review, especially if a combined derivative or modified network service is planned.
- This document is engineering guidance, not legal advice. Licenses of bundled effects, models, data, soundfonts and native plugins require separate review.

## Test boundary

`pytest -q tests/test_bridges.py` verifies MIDIVOLT file production and analysis without starting the third-party DAWs. Actual end-to-end import, UI playback, VST3 behavior and exact round-trip fidelity require Windows installations of Sawdust and tsov. Do not mark those as passed from these tests.
