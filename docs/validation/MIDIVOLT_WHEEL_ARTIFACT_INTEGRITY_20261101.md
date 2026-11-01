# MIDIVOLT Wheel artifact integrity gate — 2026-11-01

**Branch:** `test/midivolt-wheel-artifact-integrity-20261101`

## Executed outcome

**11 passed, 0 failed, 0 skipped.** Executed locally on Linux / Python 3.13.5
with pytest 9.0.2, setuptools 82.0.1 and wheel 0.46.3. GitHub Actions
were not used.

```sh
python -m pytest -q tests/test_verify_rc_wheel.py \
  --junitxml=MIDIVOLT_WHEEL_PREFLIGHT_20261101.junit.xml
# ........... [100%]
# 11 passed in 5.39s
```

JUnit SHA-256:
`c877ee46dcfe8034830dbb7b284ab8106ad35d39be0f40b1ec0b5fcef861421f`.

**Important:** the tests generated a **synthetic MIDIVOLT-shaped fixture**
containing stubbed CLI modules, not the real MIDIVOLT code. The fixture was
**actually built using `pip wheel --no-deps --no-build-isolation
--ignore-requires-python` and installed with `pip install --no-index
--ignore-requires-python --no-deps --target`**. The stub module successfully
imported and executed. The Python 3.11 requirement was deliberately bypassed
*only for this synthetic verifier test*, never for an official release.

The other tested cases force an invalid/missing registered module, omitted
non-CLI source module, changed source bytes, manipulated wheel bytes,
missing console entry point, incompatible Requires-Python metadata, ZIP path
traversal, missing RECORD member and invalid RECORD rows. Each is rejected.

## GitHub code identity

The exact locally executed files were committed unmodified:
- `scripts/verify_rc_wheel.py`: Git blob `7fab4d75b7662a6d3a721167a7f499eec4e9f453`
- `tests/test_verify_rc_wheel.py`: Git blob `ef3e7999ba2fb14a05d4f630a5f58280c72f41d5`

## Usage once a real MIDIVOLT wheel has been built

```sh
python scripts/verify_rc_wheel.py \
  --project pyproject.toml \
  --wheel dist/midivolt-0.1.0rc1-py3-none-any.whl
```

The verifier checks package metadata, 13 CLI entry points and their callable
definitions, all package-source Python files byte-for-byte against the
repository checkout, `RECORD` SHA-256 and sizes, archive paths, symlinks,
ZIP CRC, and Python runtime metadata.

A PASS means **built-wheel source integrity only**, not installation quality
or platform acceptance.

## Release readiness remains blocked

- **Complete production MIDIVOLT wheel build:** NOT_RUN. The isolated container
  has only a partial private repository checkout and cannot resolve GitHub DNS.
- **Clean Python 3.11 venv installation and CLI smoke:** NOT_RUN; this
  container has Python 3.13 only.
- **Windows PowerShell/DAW/Cubase and real AI model:** NOT_RUN.
- **GitHub Actions:** NOT_USED. `main`: UNCHANGED.

This artifact intentionally must not be described as a built or installed
official MIDIVOLT RC.
