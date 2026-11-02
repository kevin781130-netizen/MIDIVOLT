# MIDIVOLT — one-command offline pre-machine acceptance (2026-11-02)

## Status

**OFFLINE_PRE_MACHINE_GATE_IMPLEMENTED_AND_NEGATIVE_TESTED; PRODUCT_RELEASE_NOT_YET_CERTIFIED.**

Latest isolated branch: `fix/midivolt-rc-ai-runtime-gate-20261102`.
`main` unchanged, GitHub Actions unused.

## Code delivered

`scripts/verify_pre_machine_rc.py` runs **seven ordered fail-closed gates**:

1. Source/Windows RC packaging contract.
2. Whole repository pytest suite (not only earlier partial tests).
3. Real AI → MIDI → review 40-test offline acceptance (must emit `PASS_SUPPORTED_RUNTIME`).
4. Real installed `music21` acceptance (must emit `PASS_REAL_MUSIC21_ACCEPTANCE`).
5. Offline no-deps setuptools Wheel build from current checkout.
6. Wheel exact-source/entrypoint/license/RECORD integrity validation.
7. Clean dependency-complete offline Wheel installation and all 13 CLI imports from a supplied audited wheelhouse.

Only when **all seven gates pass**, the command returns exit 0 and `PASS_PRE_MACHINE`. It cannot label absent dependencies, unavailable wheels, missing real music21, fixture-only test evidence, or nonzero pytest exit as success. No network is used.

To reproduce on an available machine with a complete Git checkout and preprovisioned packages:

```sh
python scripts/verify_pre_machine_rc.py --wheelhouse /path/to/audited/wheelhouse --expected-head <exact-commit-sha>
```

`--expected-head` is optional for diagnostics, but strongly recommended for the final acceptance record. Do not confuse this gate with Windows/Cubase GUI or live trained-provider acceptance.

## Actually executed in this slice

Isolated Linux Python 3.13.5, pytest 9.0.2:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_verify_pre_machine_rc.py \
  tests/test_verify_ai_offline_gate.py \
  tests/test_verify_ai_offline_process.py \
  tests/test_verify_rc_source_contract.py
# 28 passed, 5 subtests passed in 3.57s
```

GitHub blob integrity checked against local test bytes:
- `scripts/verify_pre_machine_rc.py`: `9ce68cb20f2d2c5c056e5a8f4abd2b42a0990143`.
- `tests/test_verify_pre_machine_rc.py`: `607b2b8e37ef0297afb5137bde0318c5b08b7bd8`.

Seven new release gate negative tests passed, exercising missing project metadata, malformed Python policy, source contract rejection, AI regression rejection, absent real music21 PASS marker, expected commit mismatch, and Wheel build failure. The earlier 21 controller/source-contract tests and five subtests also passed.

**The 28 tests are release-gate/validator regression tests, NOT the complete MIDIVOLT product test suite.**

## Outstanding non-physical blockers

- **Full product regression on the complete checkout:** NOT_RUN in this environment (only a subset of repository files is locally mounted).
- **Current source Wheel and clean dependency-complete install:** NOT_RUN here (complete checkout and audited wheelhouse absent).
- **Real music21 parsing/accompaniment/key acceptance:** BLOCKED because music21 is not installed and this container cannot reach PyPI.

These do not become `PASS` merely because a new gate exists. Run all seven stages on a provisioned checkout to change the status to `PASS_PRE_MACHINE`.

## Remaining genuine real-environment acceptance after passing the gate

- Windows PowerShell installer and actual Cubase graphical import/export MIDI Type 1 roundtrip.
- Live model/OpenAI/Ollama provider availability, musical output quality and commercial rights.
- If WAV/stem transcription is in selling scope, Python 3.11 Basic Pitch with TensorFlow on actual user audio.

No release tag or mainline merge has been created.
