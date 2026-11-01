# MIDIVOLT — offline setuptools Wheel build gate (2026-11-01)

**Branch:** `build/midivolt-offline-setuptools-wheel-20261101`

## Executed tests: 8/8 PASS — synthetic source fixture

A genuine **setuptools.build_meta**, `python -m pip wheel --no-index
--no-deps --no-build-isolation` process was executed against a disposable,
**40-file MIDIVOLT-shaped test fixture** (including 36 Python modules and
13 CLI registrations). The built Wheel was then inspected for:

- 36 complete source modules and exact byte-for-byte source parity
- 13 console-script registrations
- Wheel METADATA, Python support range, ZIP CRC and missing/duplicate entries
- PEP 376 RECORD SHA-256 hashes and sizes

Negative tests verified rejection of modified source, modified packaged
source, tampered snapshot chunks, damaged manifest SHA, missing output
directory, and accidental overwrite. The default invocation refuses
unsupported Python versions.

**Actual command:**

```bash
cd midivolt_source_transport
python -m pytest -q tests/test_build_verified_wheel_offline.py \
  --junitxml=/mnt/data/MIDIVOLT_SETUPTOOLS_WHEEL_20261101.junit.xml
# ........ [100%]
# 8 passed in 6.59s
```

Runtime: isolated Linux Python 3.13.5, pytest 9.0.2,
setuptools 82.0.1 and importable wheel 0.46.3. The test passed the
`--ignore-requires-python` argument *only* in explicit diagnostic mode.
**This is not Python 3.11 supported-runtime acceptance.**

JUnit SHA-256:
`55c04a16c89df88b769da0332dcfa14842061e341bc10796aa32124b922629fc`.

Executed-file Git blob parity:
- `scripts/build_verified_wheel_offline.py`:
  `5d291ded876754d9762a9430993c3f207a6c9ae5`
- `tests/test_build_verified_wheel_offline.py`:
  `dd1e0c2ce154c7c27895c6aef1dc2e768c2cd74f`

## Real-source production Wheel: NOT_RUN

The exact real source snapshot (**40 original files, 36 Python modules**)
is committed as six UTF-8 GitHub parts under `source_transport/` on the
parent branch. Source chunks and embedded Git object SHA identities have
been verified via the GitHub connector, but **those private text chunks
could not be mounted into the separate local Python execution container**.
Therefore the actual production 36-module Wheel has **not** yet been built
through setuptools in this environment. The previously uploaded experimental
Wheel was assembled with a custom PEP 427 routine, not setuptools.

Do not count this fixture test as production installation or real CLI load.

Once a machine has this branch checked out:

```bash
# Default: supported Python 3.11 required; refuse overwrite, no network:
mkdir -p dist-rebuilt
python3.11 scripts/build_verified_wheel_offline.py \
  --snapshot-root . --output-dir dist-rebuilt

# Then verify/install only with an independently trusted wheelhouse:
python3.11 scripts/verify_rc_wheel_install.py \
  --wheel dist-rebuilt/midivolt-0.1.0rc1-py3-none-any.whl \
  --project pyproject.toml \
  --wheelhouse /trusted/wheelhouse \
  --sha256 <hash printed by build_verified_wheel_offline>
```

## Acceptance boundaries

| Gate | Status |
| --- | --- |
| Source snapshot transport (GitHub SHA checks) | COMPLETE |
| Offline setuptools builder + fixture regression | **8/8 PASS** |
| Genuine MIDIVOLT production setuptools wheel build | **NOT_RUN** |
| Installed 13 real CLIs on Python 3.11 | **NOT_RUN** |
| Trained AI provider output and Windows/Cubase | **NOT_RUN** |
| GitHub Actions | NOT_USED |
| Protected `main` | UNCHANGED |

No production release is claimed from this synthetic build-gate test.
