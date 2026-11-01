# MIDIVOLT — rebuilt flat-spelling diagnostic Wheel acceptance (2026-11-01)

## Result

The Wheel was rebuilt from the exact 40-file source snapshot pinned to
`4e235224f15a6fca34d94db3ce77274e9b7a6a42`, including the latest
`theory.py` flat-spelling normalizer, lazy `music21` imports, the
`review_cli.py` missing-dependency guard, and updated README.

- Wheel: `midivolt-0.1.0rc1-py3-none-any.whl`
- Size: **84,548 bytes**
- SHA-256:
  `bb88e1aa66a097484b7b59f9c28e050122a3457976b75efb93a13ddeacb20abd`
- Setuptools backend build: **PASS**
- ZIP CRC: **PASS**
- 36/36 Python product modules in archive: **PASS**
- 13/13 console-script registrations: **PASS**
- 43/43 PEP 376 RECORD inventory rows, SHA-256 digests and sizes:
  **PASS**
- Declared core dependency `music21>=9.1,<10`: preserved in metadata.

## Fresh offline install and actual CLI tests

Installed the Wheel into a newly created Python **3.13.5** virtual
environment using:

```sh
python3 -m venv venv
venv/bin/python -m pip install --no-index --no-deps \
  --ignore-requires-python dist/midivolt-0.1.0rc1-py3-none-any.whl
```

This is a **diagnostic-only** install. Project metadata requires
`>=3.11,<3.12`; `--ignore-requires-python` was not a release workaround.
The offline venv intentionally omitted dependencies. Tests used the
container's preinstalled `pretty_midi`, `mido`, `numpy` and `pytest`
through `PYTHONPATH=/opt/pyvenv/lib/python3.13/site-packages`.
`music21` is not installed.

The test runner imported the package from the newly installed venv, not
the source tree:

`/mnt/data/midivolt_flat_build/venv/lib/python3.13/site-packages/midivolt/theory.py`

Executed:

```sh
venv/bin/python -m pytest -q \
  tests/test_chord_symbol_normalization.py \
  tests/test_review_music21_and_cubase_offline.py
# 14 passed, 1 skipped in 1.86s
```

JUnit SHA-256:
`9431e2f9bfa229a696d79b39abfd7a5b91d93114780bdd15bbe366d1c71b0a38`.

- Nine flat-spelling / alteration-preservation cases: **PASS**.
- Real music21 chord parse, slash bass and interval integration: **SKIPPED**
  because `music21` is unavailable.
- Review help, controlled missing-music21 rejection, locked-source
  preservation, explicit approval, Type 1 MIDI export and strict event
  comparison: **5/5 PASS**.

All **13/13 installed console launchers** returned `--help` successfully.

A separate real installed-Wheel call
`midivolt create --chords Bbmaj7 --out ...` returned exit **2**, printed
the expected missing-`music21` diagnostic and created **no MIDI output**.
This verifies safe failure, not successful chord generation.

## What this does not prove

- Supported Python 3.11 installation: **NOT RUN**; interpreter absent.
- Clean dependency installation: **NOT RUN**; offline dependency wheels absent.
- Real `music21` chord parsing, voicing generation and key estimation:
  **NOT RUN**.
- Real Cubase GUI import/export and trained model inference: **NOT RUN**.
- This diagnostic Wheel is not a production release.

The previous environment search found only Python 3.13.5, no Python 3.11
binary or cached `music21` package, and no DNS resolution for PyPI. No
fake dependency or substitute implementation was used.

## Source and governance

- Source snapshot: **40/40 Git blob SHA checks PASS**, 36 product modules.
- Source commit: `4e235224f15a6fca34d94db3ce77274e9b7a6a42`.
- No GitHub Actions run.
- Protected `main` was not modified.
