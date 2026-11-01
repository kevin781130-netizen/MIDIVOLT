# MIDIVOLT Wheel source provenance gate — 2026-11-01

## Code change

Official offline Wheel builder now pins the expected immutable source commit:
`f2e4b45a7bbc28805f71918033627e983b714268`.

- Added `--expected-source-commit` CLI option and 40-character lowercase
  Git SHA validation.
- Refuses `SOURCE_COMMIT_MISMATCH` before setuptools is invoked, rather than
  building a self-consistent but unintended snapshot.
- Returns `INVALID_EXPECTED_SOURCE_COMMIT` for malformed expected commit.
- The committed `source_transport/MANIFEST.json` on this branch was
  inspected against GitHub and **matches the pinned source commit**.
- Only the builder and its tests were modified; protected `main` unchanged.

## Actually executed (isolated Linux Python 3.13.5)

```bash
python -m pytest -q tests/test_build_verified_wheel_offline.py \
  --junitxml=/mnt/data/MIDIVOLT_PROVENANCE_GATE_20261101.junit.xml
# .......... [100%]
# 10 passed in 6.88s
```

JUnit tests=10, errors=0, failures=0, skipped=0, time=6.880 s.
JUnit SHA-256:
`2108a727d30802caa6975e20428099d82371fb77521968b4ef3b9b2cb7818d6f`.

The executed code matched committed GitHub blobs:
- `scripts/build_verified_wheel_offline.py`:
  `2ce0651351f6f92ad8736c6628c6660df06f96ad`
- `tests/test_build_verified_wheel_offline.py`:
  `85156ca5cf2ca265cac899f3798c2842f6b7ae13`

**Scope:** Ten tests build/test a *synthetic 40-file fixture*. Two new
tests verify a mismatched or malformed expected source commit cannot
generate any Wheel.

## Real production build: BLOCKED, not PASS

The local isolated build command was actually attempted:

```bash
python scripts/build_verified_wheel_offline.py \
  --snapshot-root . --output-dir /mnt/data/midivolt_build_gate_out \
  --diagnostic-unsupported-python
# status: BLOCKED
# errors: ["Missing safe snapshot manifest"]
# built: false
```

The six private GitHub source parts remain verified in the repository but
are not mounted into this container. The container has Python 3.13.5,
not the supported Python 3.11, and cannot resolve GitHub DNS.

Consequently **official product setuptools Wheel build and clean Python 3.11
installation with 13 real CLI imports remain NOT_RUN**. No GitHub Actions.
No real trained model or Cubase acceptance.

On a proper Python 3.11 checkout of this branch (including
`source_transport/`), run:

```bash
mkdir dist-real
python3.11 scripts/build_verified_wheel_offline.py \
  --snapshot-root . --output-dir dist-real \
  --expected-source-commit f2e4b45a7bbc28805f71918033627e983b714268
```
