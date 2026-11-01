# MIDIVOLT AI Provider → MIDI → Review/Approval: executed offline E2E

**Execution date:** 2026-11-01 (UTC)  
**Branch:** `test/midivolt-ai-provider-to-review-e2e-20261101`  
**Result:** **5 passed / 0 failed / 0 skipped**. This is a real executed isolated test against the *exact GitHub code bytes* described below, not a claim of trained-model or DAW acceptance.

## Reproduction and command

In an isolated Linux test directory, all 8 required MIDIVOLT source files and the checked-in test file were restored from the private GitHub connector. Every byte stream was compared independently to its GitHub blob SHA (Git blob SHA-1 of `b"blob " + len + b"\\0" + payload`).

```sh
cd midivolt_ai_full_offline
PYTHONPATH=src python -m pytest -q tests/test_ai_provider_to_review_e2e.py \
  --junitxml=MIDIVOLT_E2E_20261101.junit.xml
# ..... [100%]
# 5 passed in 2.63s
```

Executed runtime: Python 3.13.5, pytest 9.0.2, pretty_midi 0.2.11 on Linux. **Python 3.13 is not the specified supported Python 3.11 runtime.**

JUnit results: `tests=5`, `failures=0`, `errors=0`, `skipped=0`, `time=2.628` seconds.

## Executed scenarios

1. `test_http_to_editable_multitrack_midi_without_review_for_new_song`: true loopback HTTP request to a fixture Ollama server, serializable two-track MIDI produced.
2. `test_http_to_approved_extension_preserves_original_midi`: existing flute track and controller remain unchanged, review manifest validates, approval required, approved MIDI created.
3. `test_truncated_ollama_reply_never_creates_midi_or_manifest`: `done_reason=length` refused, no candidate or manifest.
4. `test_provider_wrong_track_roles_rejected_before_publish`: duplicate generated roles rejected before writing MIDI.
5. `test_concurrent_source_change_during_provider_call_never_publishes`: original changed during provider request; no candidate or review manifest published.

## Byte-for-byte source verification

| GitHub file | Verified blob SHA |
| --- | --- |
| `src/midivolt/ai_cli.py` | `b07f1e3d41ddd2ccc034d40303e9955e6f910d61` |
| `src/midivolt/ai_midi.py` | `e6f17e80220b8c3d209b03dc8f2fb2796cccc611` |
| `src/midivolt/prompt_music.py` | `b6d8496cb28563bdfc87971685a901b8ddc2304a` |
| `src/midivolt/io.py` | `f943c2c3d57891303a93e67236e98dafd06bd98b` |
| `src/midivolt/review_engine.py` | `ad7f24531666f802f005b6a587f1c369d3d79a3b` |
| `src/midivolt/_approval_snapshot.py` | `75cd3d9a09efbf347fbf49f8f6a9241fc3a6ca30` |
| `src/midivolt/_candidate_cleanup.py` | `cbfd0b0ef850932a7a0c06b1b3b47be4c30b1c56` |
| `src/midivolt/_provider_contract.py` | `312091068d2fa51d24c189e0be8b26e509f3a42f` |
| `tests/test_ai_provider_to_review_e2e.py` | `cb6915116d8964320bb3e4ee2247894e5b86ec9e` |

The test directory used an empty `src/midivolt/__init__.py` solely to enable imports. That isolated convenience file was not committed to the repository.

## Truth limits

- The Ollama HTTP server is **a local fixture**, not a live trained Ollama model. No OpenAI billing.
- Linux Python 3.13 test does **not** establish supported Windows Python 3.11 compatibility.
- Full repository test suite and acoustic musical quality: NOT_RUN.
- Actual Cubase GUI import/export and plug-in integration: NOT_RUN.
- GitHub Actions: NOT_USED; `main` not modified.

**Disposition:** This specific five-scenario **offline AI Provider → MIDI → Review/Approval gate is PASS**. Continue broader regression and supported-runtime gates separately; do not declare Windows/Cubase or trained-model E2E accepted.
