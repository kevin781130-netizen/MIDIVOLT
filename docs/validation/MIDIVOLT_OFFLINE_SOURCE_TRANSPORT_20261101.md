# MIDIVOLT verified offline source transport — 2026-11-01

## Purpose

Unblock obtaining **real MIDIVOLT source** when GitHub can be accessed
through an authenticated connector but a separate container cannot download
private GitHub binary blobs. This does **not** constitute a successful
install of the previously produced experimental Wheel.

## Repository source facts (GitHub verified)

- Source commit: `f2e4b45a7bbc28805f71918033627e983b714268`
- **40** source/package metadata files; **36** real `src/midivolt/**/*.py`
  modules; no substituted test stubs.
- Six JSON snapshot chunks are committed as ordinary UTF-8 **text**, not
  unreferenced Git objects or binary artifacts.
- Each chunk's Git object SHA and all 40 embedded file Git blob SHAs were
  checked against the private GitHub tree before the snapshot was committed.
- Metadata and file-count inventory:
  `source_transport/MANIFEST.json`.

## Executed verifier tests (limited)

Executed locally under Linux Python 3.13.5, pytest 9.0.2:

```bash
python -m pytest -q tests/test_restore_source_snapshot.py \
  --junitxml=MIDIVOLT_SOURCE_TRANSPORT_20261101.junit.xml
# ........ [100%]
# 8 passed in 0.07s
```

JUnit SHA-256:
`2ad6dea84d7a0c490e82897f27a04ec971262a9c48ff9f376155d06c59b49054`

These eight tests verify the restore script against realistic **synthetic**
40-file fixtures, including source SHA validation, successful restoration,
refusal to overwrite, tamper detection, manifest tamper detection, unsafe
paths, missing chunk, and verify-only operation. **They do not replace
running the restore script on the complete real snapshot in the container.**

The locally executed scripts exactly match the committed Git blobs:

- `scripts/restore_source_snapshot.py`:
  `c4e598d220c6d24553575f728d15b9a19e71ae7d`
- `tests/test_restore_source_snapshot.py`:
  `7d556af6b4532badef26371311d5d5bc0a62ed2d`

## Repeatable next commands on a machine with this GitHub branch available

```bash
# Inspect six text chunks and 40 embedded Git blob SHA-1s, without writes:
python scripts/restore_source_snapshot.py --verify-only

# Restore verified real source into an empty directory:
python scripts/restore_source_snapshot.py --destination ./midivolt-verified-source

# Offline genuine setuptools build (requires installed setuptools + wheel):
python3.11 -m pip wheel --no-index --no-deps --no-build-isolation \
  --wheel-dir ./dist-rebuilt ./midivolt-verified-source

# Check actual newly built wheel against restored source tree:
python3.11 scripts/verify_rc_wheel.py \
  --project midivolt-verified-source/pyproject.toml \
  --wheel dist-rebuilt/midivolt-0.1.0rc1-py3-none-any.whl
```

The newly built Wheel SHA-256 will differ from the previously manually
assembled experimental Wheel; independently calculate and verify it.

## Not yet accepted

- Genuine setuptools Wheel build from the source snapshot: **NOT_RUN here**.
- Actual experimental private Wheel pip install: **NOT_RUN here**, because
  the private binary cannot be passed through the GitHub connector.
- Python 3.11 clean-venv install / all 13 real CLIs: **NOT_RUN**.
- Real trained AI model, Windows installer, Cubase: **NOT_RUN**.
- GitHub Actions: **NOT_USED**; protected `main`: **UNCHANGED**.

**Disposition:** Real source transport via GitHub-readable text is
complete; official Wheel build and runtime acceptance still require an
environment capable of materializing the source and running Python 3.11.
