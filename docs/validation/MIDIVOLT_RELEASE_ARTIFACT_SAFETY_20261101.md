# MIDIVOLT Release Artifact Safety — 2026-11-01

## Status and exact scope

This branch prevents a **stale experimental Wheel** from being mistaken
for the corrected Apache-2.0 / third-party-notices developer RC. It does
not certify the real Python 3.11 product build.

### GitHub branch changes verified

The inherited **old, manually assembled, unverified** binaries and manifests
were removed from THIS ISOLATED BRANCH ONLY (the parent branches are intact):

- `dist/midivolt-0.1.0rc1-py3-none-any.whl`
- `dist/EXPERIMENTAL_WHEEL_MANIFEST_20261101.json`
- `dist/EXPERIMENTAL_WHEEL_SHA256SUMS.txt`

GitHub recursive tree confirms **no `dist/` file remains** on this branch.
`main` is unchanged. GitHub Actions were not run.

### Corrected three-stage package policy

The source package metadata already declares
`license = "Apache-2.0"` and
`license-files = ["LICENSE", "THIRD_PARTY_NOTICES.md"]`.

1. `scripts/verify_rc_source_contract.py`: fails if either required source
   license-file declaration is absent or the SPDX expression differs.
2. `scripts/build_verified_wheel_offline.py` (inherited): fails if the
   actual wheel omits a declared license, PEP 639 metadata, or byte-for-byte
   source parity.
3. `scripts/verify_rc_wheel.py` (newly hardened): now checks **the same**
   license declarations, `License-Expression`, complete `License-File`
   metadata, presence of both `dist-info/licenses/` members, and exact
   contents against the checkout. Thus the separate
   `scripts/verify_rc_wheel_install.py` cannot accept an outdated
   wheel solely on the strength of a matching supplied SHA.

Added negative tests in `tests/test_verify_rc_source_contract.py` and
`tests/test_verify_rc_wheel.py`. **The modified GitHub test suites have
NOT yet run in this isolated execution container**, where the full private
repository is not mounted. Do not label these as PASSED.

## Actually executed independent setuptools packaging reproduction

Local Linux Python 3.13.5, setuptools 82.0.1, pip 25.1.1.
Executed a real `pip wheel --no-index --no-deps --no-build-isolation
--ignore-requires-python` build for two disposable, **synthetic**
MIDIVOLT-shaped source fixtures (legacy metadata and fixed metadata).

```sh
python -m pytest -q test_midivolt_license_packaging.py \
  --junitxml=MIDIVOLT_LICENSE_FIX_INDEPENDENT_20261101.junit.xml
# ..... [100%]
# 5 passed in 10.16s
```

Verified:
1. Old `license={file="LICENSE"}` metadata omits
   `dist-info/licenses/THIRD_PARTY_NOTICES.md`.
2. Fixed `license="Apache-2.0"` and `license-files` includes both
   mandatory license members in the actual built wheel.
3. Correct `License-Expression` and `License-File` metadata.
4. All 13 declared CLI targets in `entry_points.txt`.
5. `RECORD` inventory matches ZIP members.

JUnit SHA-256:
`9c3e3500a096e2cbba423099264b3eaf3e19f3d7c7c2a8693c5be5df8220dc59`.

The fixture does NOT contain real MIDIVOLT production code. This
independent reproduction is NOT proof of a genuine real-source Wheel build.

## Unresolved acceptance gates

- Full real 40-source / 36-module Python setuptools Wheel: **NOT_RUN**.
  The GitHub connector can read the real UTF-8 source snapshot, but it cannot
  directly mount it inside the isolated container and container DNS cannot
  resolve private GitHub. A prior experiment compressed the snapshot, but
  transfer to this container was not completed.
- Installed all 13 *real* CLI commands under supported Python 3.11:
  **NOT_RUN**.
- Windows PowerShell and Cubase integration: **NOT_RUN**.
- Trained live model and musical evaluation: **NOT_RUN**.

This is a targeted release-artifact safety fix. **No production release
acceptance is claimed.**
