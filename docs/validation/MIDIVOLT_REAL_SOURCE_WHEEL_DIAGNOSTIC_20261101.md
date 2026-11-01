# MIDIVOLT real-source setuptools Wheel — actual diagnostic evidence (2026-11-01)

## Breakthrough: real source restored, not synthetic fixture

The isolated Linux container received all **40 actual MIDIVOLT GitHub source and metadata files**, including **36 product Python modules**, from an authenticated text snapshot. Every file was validated against its immutable Git blob SHA-1 before being written.

- Exact source commit: `dc96031bed0edc5c2746880ae1cb2997da1d15ef`
- Corrected pyproject Git SHA: `1b31f9b802ec2cd6681451acf5b638d29574246b`
- Checks: **40/40 Git blob SHA checks PASS**, 36 production Python files restored.
- Confirmed Apache-2.0 SPDX metadata and `LICENSE` + `THIRD_PARTY_NOTICES.md` present.
- No GitHub Actions, network dependency fetch, or `main` modification.

## Actual production setuptools build — PASS_DIAGNOSTIC_PY313

Executed the genuine `setuptools.build_meta` build against all the restored
**real** source modules (not a mock):

```sh
PIP_NO_INDEX=1 PIP_CONFIG_FILE=/dev/null python -m pip wheel \
  --no-index --no-deps --no-build-isolation --ignore-requires-python \
  --wheel-dir /mnt/data/midivolt_real_wheel \
  /mnt/data/midivolt_product_real
# Successfully built midivolt
```

- Linux Python **3.13.5** (unsupported by declared `>=3.11,<3.12`)
- setuptools **82.0.1**, wheel **0.46.3**, pip **25.1.1**
- `midivolt-0.1.0rc1-py3-none-any.whl`: **83,996 bytes**
- Real Wheel SHA-256:
  `455273361a086f5f52feeb72ddb469b1ac2c9daf6628c9d1cc88847feb436d3f`

`--ignore-requires-python` was used **only for explicitly non-release diagnostic build**.

## Real built Wheel: 16/16 integrity assertions PASS

Independent inspection of the generated real Wheel validated ZIP integrity,
all **36** source files byte-for-byte, all **13** CLI registration targets and
callable main declarations, 43 archive entries, source-identical license
contents, SPDX metadata, exact PEP 376 `RECORD` inventory with every member's
SHA-256 and size, runtime metadata and pure-Python tag.

## Actual offline install and CLI smoke

The real Wheel was installed with `pip install --no-index --no-deps
--ignore-requires-python` in a disposable **Python 3.13.5** venv:
**PIP INSTALL PASS**. All **13 launcher executables** were created.

Because `--no-deps` omits mandatory dependencies, initial CLI imports lacked
`pretty_midi` and `mido`. A second **diagnostic-only** load/help test used
`PYTHONPATH=/opt/pyvenv/lib/python3.13/site-packages` to expose already
installed local dependencies, then **12/13 actual CLIs imported and returned
`--help` exit=0**. The main `midivolt` launcher alone failed:

```
ModuleNotFoundError: No module named 'music21'
```

`music21` is declared as a core dependency, but is not available in the
offline container. That error is a **missing installed dependency**, not
proof of an intrinsic application bug.

## Remaining release gates (do not misreport as PASS)

- Official **Python 3.11** clean install with all declared dependencies:
  **NOT_RUN**; no Python 3.11 available in this container.
- **13/13 real CLI load/help** with complete dependencies: **BLOCKED** by
  unavailable offline `music21` wheel.
- Windows installer / actual Cubase DAW: **NOT_RUN**.
- Live model generation and musical-quality acceptance: **NOT_RUN**.
- GitHub Actions **NOT_USED**; protected `main` **UNCHANGED**.

**Disposition:** the previous source-transfer and real setuptools Wheel-build
blockers are resolved. Supported-runtime/dependency and real-hardware E2E
remain open. The diagnostic Wheel is available as a verified sandbox artifact
in its execution conversation, *not* uploaded to GitHub or certified as a
production release.
