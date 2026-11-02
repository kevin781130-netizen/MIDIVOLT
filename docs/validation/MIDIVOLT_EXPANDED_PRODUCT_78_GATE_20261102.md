# MIDIVOLT RC: expanded real product offline regression (2026-11-02)

## Decision

**78/78 PASS (expanded restored product subset); overall PRE_MACHINE still BLOCKED.**

No mainline changes, GitHub Actions, commercial AI provider, actual Cubase DAW, or customer audio. This report preserves a real local execution, not a synthetic validation result, and does not claim full-repository release acceptance.

## Actual execution

- Linux CPython 3.13.5; restored real MIDIVOLT 36-module product source from verified Wheel.
- Ran `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests --junitxml=/mnt/data/MIDIVOLT_EXPANDED_REAL_PRODUCT_20261102.junit.xml` in restored local working directory.
- **78 passed, 0 failed, 0 errors, 0 skipped** in **5.10 seconds**.
- JUnit SHA-256: `e303826ca86ab0e95864f7bb04b85eb3b9f1758954253576158cb4b6d8ec72f4`.
- Evidence archive SHA-256: `e962a6853f609ba718f776172797dce764fc0a2017ba84621231c0094e7e7a51`.

## Test-source provenance

Ten product test files were present in the local restored source suite.

Exactly matched GitHub blob SHA-1:
- `test_ai_provider_to_review_e2e.py`
- `test_review_engine.py`
- `test_approval_snapshot_standalone.py`
- `test_candidate_cleanup_standalone.py`
- `test_provider_contract_standalone.py`
- `test_deterministic_property_matrix.py`

Four more test files, reconstructed from the current GitHub test contents, have formatting differences from their original Git blobs and **must not be claimed byte-for-byte GitHub-identical**:
- `test_io.py` — four tests.
- `test_bridges.py` — five tests.
- `test_prompt_music.py` — nineteen parametrized testcases.
- `test_cubase_smf.py` — nine tests.

Executed coverage: AI-to-MIDI-to-review/approval safety, on-disk MIDI serialization and overwrite protection, TSOV/Sawdust bridges, seeded symbolic arrangement and source-preserving extension, Cubase SMF Type 0/1 normalization and strict event comparison, and 560 MIDI generation + 140 extension property scenarios (within one testcase).

## Still blocked (NOT hardware-only)

1. **Whole original repository `pytest tests`: NOT_RUN.** Only ten reconstructed test files were executed; other GitHub suites remain absent in this local environment.
2. **Actual installed music21 9.7.1–9.x acceptance: BLOCKED.** No package found locally; PyPI/GitHub DNS lookup failed.
3. **Full dependency-complete clean Wheel installation: BLOCKED.** Existing successful install used diagnostic `--no-deps`, and `pip check` reports missing `music21`, `mido`, `pretty-midi`.

After these pass on an adequately provisioned isolated executor, pending real workstation acceptance still includes Windows PowerShell installer, actual Cubase GUI import/export, live trained-model output/quality, and optional Python 3.11 Basic Pitch acceptance if WAV/stem transcription is in scope.

**Do not mark `PASS_PRE_MACHINE` until all mandated gates have actually passed.** The evidence zip `MIDIVOLT_EXPANDED_OFFLINE_EVIDENCE_20261102.zip` is attached to the conversation, not a GitHub release.