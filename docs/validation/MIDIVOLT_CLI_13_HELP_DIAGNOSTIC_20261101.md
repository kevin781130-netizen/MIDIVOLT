# MIDIVOLT: genuine Wheel CLI lazy-music21 gate — 2026-11-01

## Result

**13/13 installed real MIDIVOLT CLI `--help` commands PASS** on diagnostic-only
Linux Python **3.13.5**, without `music21`. This is a true production-source
`setuptools.build_meta` Wheel, not a synthetic fixture.

### Product repair

`src/midivolt/cli.py` previously imported `midivolt.arrange` and
`midivolt.theory` at module import time; `theory` imported `music21`
before argument parsing, so even `midivolt --help` failed when that core
dependency was missing.

The CLI now imports the chord/key backend **only inside** `create`,
`arrange` or `analyze`. Without `music21`, those commands fail closed:
exit **2**, clear install-dependencies message, **no MIDI output**; `--help`
works. The published `music21>=9.1,<10` runtime requirement is **unchanged**.
This does not make `music21` optional for composition/analysis.

### Executed regression suite

```sh
PYTHONPATH=src python -m pytest -q tests/test_cli_music21_lazy_gate.py \
  --junitxml=/mnt/data/MIDIVOLT_MUSIC21_LAZY_GATE_20261101.junit.xml
# ..... [100%]
# 5 passed in 3.69s
```

JUnit SHA-256:
`4aace00e7241ccfcd4a2b4f9f12ea9244cadb5c5be55fe9bb3af16e2fcc987ab`.

GitHub blobs match the exact executed product and regression code:

- `src/midivolt/cli.py`: `f41cc6255518c6a306cf0753989649c6eab3ac30`
- `tests/test_cli_music21_lazy_gate.py`: `7ad77685fd1143e6ff0657d4eb857d36981eb28d`

### Real production-source Wheel

Executed `pip wheel --no-index --no-deps --no-build-isolation
--ignore-requires-python` on **36 real MIDIVOLT product modules**.

- Wheel: `midivolt-0.1.0rc1-py3-none-any.whl`
- Size: **84,101 bytes**
- SHA-256:
  `7c400b62a8a5832fdd7de305c27a05e9e98d592a1c3b6384bb3a05887e67bdfe`
- Independent artifact inspection: exact parity of 36 source files,
  13 registered console entry points, both Apache-2.0/third-party notices,
  correct PEP 376 `RECORD` digests and ZIP CRC; 43 ZIP members: PASS.

**The new Wheel is a conversation artifact, not committed as a GitHub
release or pushed into `dist/`**.

### Real isolated Wheel installation and CLI help

In fresh Python 3.13.5 venv:

```sh
python -m venv /mnt/data/midivolt_music21_slice/venv
venv/bin/python -m pip install --no-index --no-deps \
  --ignore-requires-python dist/midivolt-0.1.0rc1-py3-none-any.whl
# Successfully installed midivolt-0.1.0rc1
```

All **13 actual installed launchers** returned exit 0 and usage text with
`--help` (including `midivolt`, `midivolt-ai`, `midivolt-cubase`).
Diagnostic subprocesses used
`PYTHONPATH=/opt/pyvenv/lib/python3.13/site-packages`
to expose **locally existing pretty_midi/mido**: runtime dependencies were
not installed in the fresh venv. Confirmed module
`/mnt/data/midivolt_music21_slice/venv/lib/python3.13/site-packages/midivolt/cli.py`
was used, **not the local source checkout**.

With `music21` absent, `midivolt create --chords Cmaj7 --out ...`
returned **exit 2**, an actionable message, and **did not write a MIDI file**.

Diagnostic acceptance JSON SHA-256:
`66b2184b1b94100b8735f9ae5bd96859c510ada9b02316f5e92bc3ef78cb7fa8`.

### Source snapshot synchronized

The six private GitHub-readable `source_transport/part-XX.json` chunks
and `source_transport/MANIFEST.json` were updated; every one of the
**40/40 source Git blob SHAs** matched the pinned immutable source commit
`a1d0acf4f30547e1e6fa9e02b6a29904ad080e28`.
`scripts/build_verified_wheel_offline.py` now defaults to that commit.
Original `main` was not modified. No GitHub Actions run.

## Remaining release blockers

- **Supported Python 3.11 clean offline dependency install** including
  `music21`: **NOT_RUN**; Python 3.11 and the `music21` wheel are
  unavailable locally.
- **13/13 actual CLI musical functions or real model outputs:** NOT_RUN.
  **Only their `--help` entry points have passed**, not their functionality.
- Windows installer / actual Cubase roundtrip / live AI musical quality:
  NOT_RUN.
- No claims of formal release certification based on this diagnostic run.

**Disposition:** production Wheel build, 13/13 CLI help and fail-closed
missing-`music21` handling are verified in Python 3.13 diagnostic mode;
full supported Python 3.11/dependency and hardware acceptance remains.
