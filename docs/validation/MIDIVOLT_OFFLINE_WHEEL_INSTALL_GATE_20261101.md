# MIDIVOLT experimental Wheel — offline pip-install acceptance gate

**Date:** 2026-11-01. **Branch:** `test/midivolt-wheel-offline-install-gate-20261101`.

## Actually executed

On isolated Linux Python **3.13.5**, the test suite executed the **exact
committed scripts** and passed:

```bash
cd midivolt_install_cut
python -m pytest -q tests/test_verify_rc_wheel_install.py \
  --junitxml=/mnt/data/MIDIVOLT_INSTALL_GATE_20261101.junit.xml
# ...... [100%]
# 6 passed in 6.04s
```

JUnit: 6 tests; 0 failures, 0 errors, 0 skipped; 6.038s.
SHA-256: `fc1cfdb57041ed1417d28a65d48c23e8aa57aefc5b680e7518116466b450d800`.

## What really passed

A disposable **synthetic MIDIVOLT-shaped fixture** was built with the real
`pip wheel --no-deps --no-build-isolation --ignore-requires-python`
command. The newly added `scripts/verify_rc_wheel_install.py` then:

1. Checked a separately supplied expected wheel SHA-256 and compared the
   built artifact against its source tree using the existing
   `scripts/verify_rc_wheel.py`.
2. Created a fresh isolated Python venv, ran `pip install` offline with
   `--no-index --only-binary=:all: --find-links`, and loaded **all 13**
   installed console-script entry points, checking launchers and callables.
3. Confirmed the result is `PASS_DIAGNOSTIC_UNSUPPORTED_PYTHON`, never a
   supported-runtime success on Python 3.13.
4. Rejected unsupported Python without explicit diagnostic consent.
5. Rejected mismatched SHA-256, malformed expected SHA-256, missing local
   wheelhouse, and altered source files before installing.

The 13 synthetic CLI module implementations are test stubs. This verifies
the **install-gate implementation and offline pip mechanics**, not the
actual MIDIVOLT product's behavior.

## Exact GitHub-to-executed-code identity

| File | Git blob SHA |
| --- | --- |
| `scripts/verify_rc_wheel_install.py` | `994fa5df8d6d1ef6ebc96736215cf8e4379ecf16` |
| `tests/test_verify_rc_wheel_install.py` | `970b3473e8fe3564fda4fd1608fb9ca56001cb51` |

Both matched `git hash-object` on the executed isolated copies.

## Real Wheel deployment remains NOT_RUN

The repository's **experimental real-source** artifact remains at
`dist/midivolt-0.1.0rc1-py3-none-any.whl` on parent branch
`artifact/midivolt-experimental-wheel-20261101`, SHA-256
`573664da01e6ae99de3eb5a017a230a85d0258d877381ce6bf31ef61ecdbe38e`.

This isolated environment **could not fetch the private binary wheel through
the available GitHub connector**; binary GitHub blob decoding failed, and
direct container GitHub DNS resolution was unavailable. **Thus that exact
Wheel was NOT pip-installed or executed here**. This is a hard boundary; do
not interpret the 6/6 as official release acceptance.

## Remaining gates

- Actual experimental MIDIVOLT Wheel installed in clean Python **3.11**,
  with an offline wheelhouse containing all transitive dependencies: NOT_RUN.
- Official `setuptools.build_meta` build: NOT_RUN (experimental Wheel
  was previously assembled directly as PEP 427).
- Real OpenAI/Ollama model and MIDI musical-quality acceptance: NOT_RUN.
- Windows installer/Cubase roundtrip: NOT_RUN.
- GitHub Actions: NOT_USED. Protected `main`: UNCHANGED.

When a genuine Wheel and complete wheelhouse become locally available, run:

```bash
python3.11 scripts/verify_rc_wheel_install.py \
  --wheel dist/midivolt-0.1.0rc1-py3-none-any.whl \
  --wheelhouse /path/to/trusted/offline-wheelhouse \
  --project pyproject.toml \
  --sha256 573664da01e6ae99de3eb5a017a230a85d0258d877381ce6bf31ef61ecdbe38e
```

The tool enforces Python 3.11 for its non-diagnostic certification.
