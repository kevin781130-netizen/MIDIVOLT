# MIDIVOLT — actual product-source and installed-wheel verification (2026-11-02)

## Decision

**PRODUCT_OFFLINE_SMOKE_PASS; PRE_MACHINE_RELEASE_GATE_STILL_BLOCKED.**
This is new execution evidence on real MIDIVOLT application modules, not only validator fixture tests. It **does not** authorize a release or claim `PASS_PRE_MACHINE`.

All activity was isolated. `main` was not changed, GitHub Actions were not used, no paid API/model was called and no DAW was opened.

## Source provenance

Recovered the pre-existing 2026-11-01 GitHub-source archive (40 files including 36 application Python modules) and the 2026-11-02 diagnostic RC Wheel from the user's file library. Overlaid all 36 application modules from the latter Wheel and compared their Git blob SHA-1 individually to the recursive GitHub tree for branch `fix/midivolt-rc-ai-runtime-gate-20261102` at `c42d59529aa02d0fbf1b2748ea79485f8c947e63`: **36/36 module blobs match**.

The restored `pyproject.toml` also matches current GitHub blob `972f6e39dabd956e3095c29fa41cee26a8242005`; this declares core Python >=3.11,<3.14 and music21 >=9.7.1,<10. **The old archive's README was not refreshed from the latest branch**, and the full repository test checkout is not available locally. The artifact built below is a diagnostic *source-code-identical* product Wheel, not a verified byte-for-byte checkout release.

## Actually built and verified (Linux Python 3.13.5)

Built the product with real `setuptools.build_meta`:

```sh
python -m pip wheel --no-index --no-deps --no-build-isolation -w /mnt/data /mnt/data/mdv_run
# Successfully built midivolt-0.1.0rc1-py3-none-any.whl
```

Resulting **real** 84,589-byte wheel SHA-256:
`51815d8580370ab70b162c967f17e83120e99db6a369233cd513f189080e7368`.

12 independent integrity assertions **PASS**: archive CRC, unique paths, package name/version, Requires-Python, SPDX license expression, both license notices byte-identical, 13 registered CLIs, 36 application modules byte-identical to the restored current source, RECORD inventory and all digests/sizes.

Installed in an isolated Python 3.13 venv with `--no-index --no-deps`. **13/13 installed CLI `--help` returned exit 0** when host `pretty_midi`/`mido` testing dependencies were exposed through PYTHONPATH. Confirmed tested `midivolt.ai_cli.__file__` resided in that venv's **site-packages**, not the unpacked project.

This is **not** dependency-complete clean installation: `pip check` reports missing `mido`, `music21`, `pretty-midi` in a truly isolated venv.

## Actually executed installed-product E2E and safety tests

```sh
PYTHONPATH=/opt/pyvenv/lib/python3.13/site-packages \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
/mnt/data/mdv_artifact_test_venv/bin/python -m pytest -q \
  /mnt/data/mdv_integration_tests.py /mnt/data/mdv_safety_tests.py \
  --junitxml=/mnt/data/MIDIVOLT_INSTALLED_WHEEL_REAL_E2E_20261102.junit.xml
# 12 passed in 4.75s
```

JUnit SHA-256: `543de1fdc787c5c82928b3764811932e7a471a4acc4fbd111613dac2d1d96133`.

12 **real MIDIVOLT** tests:
- Five loopback fake Ollama HTTP → editable MIDI → protected review/approval cases; rejects truncated provider reply, duplicate roles and concurrent source alteration. No trained model used.
- Seven product negative-path cases: refuse output overwrite, preserve locked source on approval, reject modified source, reject tampered manifest, flag changed MIDI notes in strict Cubase format comparison, fail closed on missing real music21, and reject AI request without explicit network consent.

Separate actual command-line E2E: deterministic eight-bar original MIDI with a melody, non-destructive accompaniment candidate, approval denial, approved three-track MIDI, Cubase Type 1 preparation and strict self-roundtrip. **52 MIDI note events**, **0 missing**, **0 added**; actual Cubase was **not run**. Generated four-track example: **168 MIDI notes**.

Separate actual DSP command-line execution on a synthetic 3-second WAV produced valid unquantized kick-track MIDI with **3 detected kicks**. No real-world transcription accuracy or Basic Pitch was inferred.

## Release blockers — cannot be reclassified as machine-only

1. **Full current GitHub checkout `pytest tests`** and actual project 40-case acceptance runner: NOT RUN in this reconstructed source environment, which lacks GitHub test sources.
2. **Real music21 9.7.1+ install and actual harmony/key acceptance**: BLOCKED; library is absent, local PyPI/GitHub DNS unavailable. No mock is accepted.
3. **Dependency-complete clean venv install and seven-stage `PASS_PRE_MACHINE`**: NOT RUN; trusted offline wheelhouse unavailable.
4. **Genuine application acceptance after those pass**: Windows installer, actual Cubase GUI MIDI import/export, actual provider inference and artistic quality, and Python 3.11 Basic Pitch WAV/stem workflow if commercial scope requires it: NOT RUN.

Neither the 12 E2E tests nor the Wheel build are substitutes for items 1–4. Keep the release closed until supported evidence exists.
