# MIDIVOLT RC packaging — required third-party notices

**2026-11-01 · Isolated branch:** `fix/midivolt-rc-license-notices-20261101`

## Actual defect and fix

MIDIVOLT's previous real `pyproject.toml` declared
`license = {file = "LICENSE"}` but did **not** register
`THIRD_PARTY_NOTICES.md` for packaging. With setuptools 82.0.1 and the
original metadata scheme, a genuine `pip wheel` diagnostic build
contained `dist-info/licenses/LICENSE` but **omitted**
`dist-info/licenses/THIRD_PARTY_NOTICES.md`.

The repository's LICENSE is Apache License 2.0, so the corrected
project metadata is:

```toml
[build-system]
requires = ["setuptools>=77", "wheel"]

[project]
license = "Apache-2.0"
license-files = ["LICENSE", "THIRD_PARTY_NOTICES.md"]
```

A genuine offline `pip wheel --no-index --no-deps --no-build-isolation
--ignore-requires-python` diagnostic build with these packaging fields
**contained both license files** and emitted `License-Expression:
Apache-2.0` and both `License-File` metadata entries.

`scripts/build_verified_wheel_offline.py` now fails closed if either
license file is missing, the files differ from source bytes, or PEP 639
license metadata is incorrect.

## Snapshot provenance was updated, not silently bypassed

The changed pyproject was committed at immutable Git commit
`dc96031bed0edc5c2746880ae1cb2997da1d15ef`.
All six `source_transport/part-XX.json` files and the source inventory
were regenerated with the corrected commit reference and exact Git blob
SHAs. GitHub source tree checking confirmed:

- **40/40** source/metadata files match their immutable Git blob SHAs
- **36** real `src/midivolt/**/*.py` modules present
- pyproject Git blob `1b31f9b802ec2cd6681451acf5b638d29574246b`
- the six text chunks agree with the updated manifest commit

The builder's default expected commit was changed to the new immutable
source commit; it still rejects substituted source snapshots.

## Executed regression gate (diagnostic runtime, not release)

```sh
cd /mnt/data/midivolt_source_transport
python -m pytest -q tests/test_build_verified_wheel_offline.py \
  --junitxml=/mnt/data/MIDIVOLT_LICENSE_GATE_20261101.junit.xml
# ............ [100%]
# 12 passed in 6.83s
```

JUnit: tests=12, failures=0, errors=0, skipped=0, time=6.832 s.
SHA-256:
`4f04c2445889ee5be1ac1739c7d23563c0e0942ccff8e32ce6a02bd7018f076a`

Tests perform an actual setuptools build of a **synthetic 40-file fixture**
and check the two license members in the built Wheel. New negative tests
remove the third-party notice from the Wheel or change its source bytes,
verifying the builder refuses both. They do **not** establish that the
full production source was assembled or built in this container.

Both committed test files match the locally executed Git blobs:

- `scripts/build_verified_wheel_offline.py`:
  `6b9c104608b7531da64ef8aa270ee36d13965cd3`
- `tests/test_build_verified_wheel_offline.py`:
  `a7411b1f8a77742c6e60b8e101c5496c6102c3f5`

## Outstanding release gates

- Official full 36-module setuptools build from restored source: **NOT_RUN**
  (the GitHub text snapshot is not mounted into the Python container).
- Clean supported Python 3.11 dependency install and all 13 true CLIs: **NOT_RUN**.
- Windows installer, actual Cubase and live AI model: **NOT_RUN**.
- Inherited `dist/midivolt-0.1.0rc1-py3-none-any.whl` belongs to the
  **older experimental source assembler** and was **not rebuilt** by
  this patch. Do not treat it as containing the new license metadata.
- GitHub Actions: **NOT_USED**; protected `main`: **UNCHANGED**.

The packaging omission is fixed in source, snapshot, and build gate.
The full production installation is not yet certified.
