# MIDIVOLT — real offline MIDI review and Cubase SMF validation

Date: **2026-11-01**. Isolated branch `fix/midivolt-review-music21-failclosed-20261101`.

## Actual fixed defect

When `music21` is absent, `midivolt-review propose --chords` used to fail
with an uncaught `ModuleNotFoundError`, exit 1, and a traceback. The
product now catches **only** missing `music21` or submodules, returns
**exit 2**, prints an actionable missing-dependency diagnostic and
**does not create a candidate MIDI or review manifest**. Other unexpected
missing modules remain errors rather than being mislabeled as music21.

The published `music21>=9.1,<10` requirement is **unchanged**.
No music21 implementation or actual model inference was substituted.

## Executed actual installed-product tests

The exact 36-module product source with this review fix was built using
setuptools via `pip wheel --no-index --no-deps --no-build-isolation
--ignore-requires-python`; the resulting genuine Wheel was installed into
a fresh Python 3.13.5 venv. Test execution verified
`midivolt.review_cli.__file__` was loaded from the **installed Wheel**,
not a loose checkout. Existing locally installed `mido`, `pretty_midi`,
`pytest` were supplied to the isolated venv via
`PYTHONPATH=/opt/pyvenv/lib/python3.13/site-packages`; that is a
diagnostic environment and **not** a clean supported-runtime dependency
installation.

```sh
PYTHONPATH=/opt/pyvenv/lib/python3.13/site-packages \
  venv/bin/python -m pytest -q tests/test_review_music21_and_cubase_offline.py \
  --junitxml=/mnt/data/MIDIVOLT_REVIEW_CUBASE_WHEEL_20261101.junit.xml
# ..... [100%]
# 5 passed in 1.78s
```

JUnit SHA-256:
`182cfee49bbf861dc68d4ca6beaa478930c1974fd79780280a79485627bcd61a`.

Five tests covered:
1. Review `--help` without music21;
2. Local chord proposal rejects missing music21 without traceback,
   output or modifying source;
3. Real deterministic four-part MIDI candidate -> review proposal,
   preview, refusal without approval and explicit approval with original
   piano track locked;
4. Actual approved MIDI -> Cubase-friendly Type 1 SMF at the **original
   PPQ (220)** -> strict semantic event comparison: **45 note-on
   events, 0 missing, 0 added**, source unchanged;
5. Converting PPQ **220 -> 480** preserves note-on count but changes
   timing quantization; strict comparison correctly reports a
   non-exact result. **Do not label PPQ conversion lossless.**

The generated MIDI is original, deterministic program output and
**not** a trained AI model's inference. The actual Cubase application
was not run; `cubase_import_verified = false`.

## Actual Wheel checks

- `midivolt-0.1.0rc1-py3-none-any.whl`: **84,207 bytes**
- SHA-256:
  `3bdff29d8a7debc7410c370029deef94082a8aea15a45db2b99fcbdf86c3de1a`
- Independent ZIP check PASS: **36/36** Python source files
  byte-for-byte equal; **13/13** CLI targets registered; 2 mandatory
  license documents identical; **43/43** `RECORD` SHA-256/size
  entries correct, ZIP CRC PASS.

## GitHub source integrity

Executed-file blob hashes match the committed files:

- `src/midivolt/review_cli.py` Git blob
  `3514b2055a03eb4b45fa084ae5ad41a2720c1363`
- `tests/test_review_music21_and_cubase_offline.py` Git blob
  `4cbab084768c42007e2c019691f0a83be7d77ef3`

Six text snapshot parts plus `source_transport/MANIFEST.json` and
`scripts/build_verified_wheel_offline.py` are pinned to **exact**
40-character source Git commit
`dd557b704c7783b5777751f4461c8f2b75c8c56d`.
Verified every source snapshot entry against this GitHub commit:
**40/40 Git source blobs, 36/36 modules, six parts PASS**.

## Remaining acceptance boundaries

- Supported **Python 3.11**: NOT_RUN (not installed here).
- `music21` installation and chord/key feature execution: NOT_RUN
  (missing dependency and no package network access).
- Actual Cubase import/export on Windows or macOS: NOT_RUN.
- Real provider model inference and musical quality: NOT_RUN.
- No GitHub Actions and no `main` modifications.
- This is a validated **diagnostic** Wheel, not a certified production release.
