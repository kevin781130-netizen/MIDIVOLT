# MIDIVOLT — Genuine installed-product regression extension (2026-11-02)

## Disposition

**INSTALLED_PRODUCT_OFFLINE_REGRESSION_PASS; PRE_MACHINE_RELEASE_CERTIFICATION_BLOCKED.**

This report does not mark the release as qualified for hardware-only acceptance. No GitHub Actions, commercial AI provider, DAW or change to `main`.

## Actually executed against the installed, real production Wheel

Runtime: isolated Linux CPython 3.13.5 Wheel venv. The 36 product modules were verified against the predecessor branch's GitHub source by blob hashes in `MIDIVOLT_PRODUCT_WHEEL_E2E_20261102.md`. Existing host `pretty_midi`/`mido` packages were exposed to this diagnostic venv via `PYTHONPATH`. Thus this is **not** a dependency-complete clean install.

```sh
PYTHONPATH=/opt/pyvenv/lib/python3.13/site-packages \
  /mnt/data/mdv_artifact_test_venv/bin/python -m pytest -q \
  /mnt/data/mdv_integration_tests.py \
  /mnt/data/mdv_safety_tests.py \
  /mnt/data/mdv_run/tests/test_deterministic_property_matrix.py \
  --junitxml=/mnt/data/MIDIVOLT_PRODUCT_REGRESSION_20261102.junit.xml

# 13 passed in 7.00s
```

JUnit SHA-256: `fe812b28a1f451efcfa4b07013a2b447615dd6d2fee2542de6ed8daf2e312e92`.

The previous 12 genuine installed-product integration/safety tests were rerun and passed. The newly added **actual product** property-regression test executed **560 deterministic MIDI generation and roundtrip cases** and **140 source-MIDI extension cases**, varying fourteen key spellings, two modes, multiple BPMs/bar counts, part selections and random seeds. It checked deterministic notes, valid note bounds, 4/4 bar timing, track preservation, MIDI serialize/parse, and source immutability. These are 700 checked scenarios inside one pytest testcase, not 700 pytest testcases.

Committed `tests/test_deterministic_property_matrix.py` Git blob SHA: `3cbb95e21376950aa6dac7cbcbf516a4e3ad64a3`, independently compared with the executed local test file's `git hash-object`. The only production-branch delta from `9360556` to this test commit is this new test file; no application code was changed.

## Actual blockers

- The isolated test container cannot resolve GitHub or PyPI DNS. Attempts to obtain a trusted `music21>=9.7.1,<10` distribution cannot complete, and no local `music21` wheel is available. Do not fake or mock the real-engine release gate.
- Current full GitHub `pytest tests` checkout has not been executed in this container; the file library includes the real product source and Wheel, but not all repository test files.
- The clean, dependency-complete `midivolt` venv still fails `pip check` due to missing `mido`, `music21`, `pretty-midi` (and a separate system-installed supervisor dependency). Only diagnostic `--no-deps` Wheel installation is verified.
- Actual Cubase import/export and real OpenAI/Ollama model musical-quality acceptance remain outside this environment.

**Do not label this `PASS_PRE_MACHINE` or `ONLY_MACHINE_TESTS_LEFT`.**
