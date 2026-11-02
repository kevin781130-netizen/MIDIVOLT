# MIDIVOLT — Expanded real-product offline acceptance (2026-11-02)

**Decision: 165_PASS, 1_SKIP, 0_FAIL; official AI gate 40_PASS; PRE_MACHINE=BLOCKED.**

This is actual CPython 3.13.5 execution against the restored real 36-module MIDIVOLT product, with 18 locally restored product test files. **It is not the full original Git checkout suite** and does not certify actual Cubase, a trained model, Python 3.11 model environments or a dependency-complete Wheel installation.

## Actually executed

```sh
cd /mnt/data/mdv_run
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests \
    --junitxml=/mnt/data/MIDIVOLT_165_OFFLINE_REAL_20261102.xml
# 165 passed, 1 skipped in 26.10s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python scripts/verify_ai_offline.py \
    --junit /mnt/data/MIDIVOLT_AI_GATE_POST165_20261102.xml
# 40 passed in 2.68s; PASS_SUPPORTED_RUNTIME
```

- Full restored test subset JUnit SHA-256: `0ea949fe0d3406cf8d1cd831dd2b87441e8ab3fe0398e5439ab43fa0f594a48c`.
- Official AI gate JUnit SHA-256: `80ca4ab327130c35ce2245bef4113642b4fcaa06349fb2e7d7635d80396f4c35`.
- Evidence package `MIDIVOLT_165_OFFLINE_EVIDENCE_20261102.zip` SHA-256: `10d949c85b01a394e48b16fcb598fea7436b0348dfd2211e367976f377906f9e`.

The **three newly recovered exact GitHub test sources** and `git hash-object` SHA-1 match:

| Exact GitHub test | SHA-1 | Tests |
| --- | --- | --- |
| `tests/test_model_hub.py` | `fd59fcd88375957949d53954ff15d61798518321` | 13 pass |
| `tests/test_review_music21_and_cubase_offline.py` | `4cbab084768c42007e2c019691f0a83be7d77ef3` | 5 pass |
| `tests/test_ai_midi.py` | `e9d75f63434946204944a4170672406bf692b9ba` | 34 pass |

These are genuine application tests, including real local loopback HTTP to a fake provider and actual MIDI serialization/review/strict Cubase SMF checks. No actual remote AI model inference, no GUI/DAW use. The single skip is the genuine music21 harmony test, not a pass. Previously restored application test files may be byte-different from their GitHub originals; only the three sources above were SHA matched in this slice.

## Remaining release-blocking work

1. **Full exact Git checkout regression** is NOT_RUN; 18 recovered local test sources are not all GitHub tests.
2. **True installed music21 9.x** harmony, chord/key and arrangement acceptance is BLOCKED: no installed package, DNS to PyPI unavailable. The official `music21-9.7.1-py3-none-any.whl` is known on PyPI, SHA-256 `9bf2a169162206f72bd774dfa8fcf9c726d699cfa1aea7b5ad3eaa94452d3c16`, but direct download into this executor FAILED. Do not replace with a mock library.
3. **Clean dependency-complete Wheel installation** is NOT_PASS because music21 and complete audited wheelhouse are unavailable; earlier diagnostic installs used `--no-deps`.
4. Separate Python 3.11 legacy model environment smoke is unverified and should remain in the workstation scope if model-adapter functionality is shipped.

**Do not claim `PASS_PRE_MACHINE` or `only real machine remains`**. The next software closeout must execute the original full test tree, true music21 and exact-wheel clean install, not change the release success marker.

Only evidence documentation was added to this branch by this step. No production code or tests were edited, `main` was not touched, GitHub Actions were not run.
