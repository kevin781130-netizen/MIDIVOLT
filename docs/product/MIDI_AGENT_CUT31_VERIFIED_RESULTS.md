# MIDIVOLT Cut31 — provider-ready AI MIDI: verified engineering results

Date: 2026-10-26. Base: Cut30 product branch founded on main (not divergent drum research).

## Verified test evidence

GitHub Core MIDI CI successful for commit 6d6085161f0a24e21ef540162411cef1b432cd02:
https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40293121184

- Windows Python 3.11: **151 passed, 1 skipped**.
- Ubuntu Python 3.11: **151 passed, 1 skipped**.
- Suite includes real loopback HTTP server request/response integration, serialized editable MIDI output, OpenAI API key transport contract, source-preserving extension proposal, approval-before-apply, malformed AI output fail-closed and existing product feature regressions.
- The local loopback server returns fixture note JSON. **A real trained LLM was not run in the CI workflow.**

## Artifacts actually implemented

- src/midivolt/ai_midi.py: real callable OpenAI Chat Completions and Ollama HTTP adapters; no hidden fallbacks.
- src/midivolt/ai_cli.py: midivolt-ai installed console command and manifest-based review.
- pyproject.toml: executable entrypoint registration.
- tests/test_ai_midi.py: transport, security, note and MIDI acceptance fixtures.
- docs/product/MIDI_AGENT_CUT31_AI_PROVIDER.md: user setup and limitations.

## Safety/commercial considerations

The system never executes text returned by a model and never requires provider packages or embeds keys. The remote model must produce exact role/notes JSON within specified 4/4 bars, MIDI pitch/velocity limits, and GM percussion mapping. It performs no audio rendering or music-quality inference. Existing MIDI requires a hash-verified review manifest and explicit approval for final application.

OpenAI API usage requires the user's own separately billed developer API key. Local Ollama usage requires a model to be installed by the user; a GitHub hosted runner is not evidence of an actual model being available on the user's Windows device. Do not assert ChatGPT consumer login integration, real instrument semantics, trained music-model accuracy, Cubase live GUI acceptance, VST3/AU/AAX plug-in delivery, or commercial Beta readiness.

## Product status

Subjective functional parity estimate against publicly advertised MIDI Agent capabilities moves from ~28% after Cut30 to **~33% after Cut31**, counting tested transport-and-conversion integration, not proof of end-user AI music quality. The largest remaining blockers are genuine user-credentialed model evaluation, multi-turn MIDI editing/history, standalone GUI, DAW-host plug-in and acoustic transcription correctness.

Next prioritized slice: a structured, stateful edit session that keeps source and result as separate MIDI versions; track-selective follow-up instructions, note-diff preview, undo and provider credential isolation. After that use a user-authorized real OpenAI/Ollama model to measure musical coherence and request adherence.
