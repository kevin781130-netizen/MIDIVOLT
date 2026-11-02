# MIDIVOLT RC1 — quickest safe code-closeout (2026-11-02)

## Decision

**OFFLINE_CLI_CORE_CODE_FREEZE_CANDIDATE** — **NOT a commercial
production release**.

The existing core RC package can be built and diagnosed on Python 3.13.5.
The final real music21, Windows/Cubase GUI, and pretrained-provider checks
remain open and are not silently waived.

## P0 corrected on this isolated branch

The previous source configuration expanded core Python support to
`>=3.11,<3.14`, but **three different release gates still hard-coded
Python 3.11** and misclassified a valid 3.13 build/install:

1. `scripts/verify_rc_source_contract.py`: now checks the actual
   `>=3.11,<3.14` project contract instead of the obsolete `<3.12`.
2. `scripts/build_verified_wheel_offline.py`: now parses the
   `requires-python` policy **from the SHA-verified source snapshot**,
   permits the exact interpreter range and blocks unknown/out-of-range
   policies without the explicit diagnostic override.
3. `scripts/verify_rc_wheel_install.py`: now reads the actual
   project's Python policy, checks the interpreter before pip install,
   and will only label a dependency-complete install as supported when
   the source Python policy allows it.

Associated unit-test fixtures and release policy assertions were updated,
including the license/third-party-notice requirements for wheel fixtures.

**Modified GitHub gate test suites have not been re-executed in the isolated
container after these patches. Do not mark them PASS from static review.**

## Real previously built Wheel — actually re-tested locally

A production-source Wheel **from the previous core runtime branch** was
re-tested in a *fresh* Python 3.13.5 venv on 2026-11-02.
This binary **does not contain the updated gate scripts** (they are repository
tools, not product modules), and this is a diagnostic installation using
`--no-deps`, with existing host dependencies supplied to CLI-help subprocesses.

Artifact: `midivolt-0.1.0rc1-py3-none-any.whl`

- SHA-256:
  `d7d0477e7ef53324ffea5361692a6024273cf82c92c4ae03694f5f9c845f18c9`
- Size: **84,852 bytes**
- Actual venv `pip install --no-index --no-deps`: **PASS**
- 36 packaged Python source modules: present
- 13 actual CLI `--help` executable invocations: **13/13 PASS**
- ZIP CRC and PEP 376 RECORD digests/sizes: **PASS**
- Required Apache 2.0 and third-party notice files: **present**
- Real installed `midivolt create --chords Bbmaj7` with missing music21:
  exit 2, clear diagnostic, **no output artifact**.

Actual diagnostic evidence:
`MIDIVOLT_RC_CLOSEOUT_ACTUAL_WHEEL_20261102.json` in the conversation
attachments.

## Fail-closed release decision

| Gate | Actual state |
| --- | --- |
| Core Python 3.13 diagnostic Wheel install | **PASS** |
| Package payload/13 CLI help/ZIP RECORD | **PASS** |
| SHA-verified real source snapshot (previous slice) | **PASS** |
| Release-gate Python policy consistency in GitHub | **PATCHED, TESTS NOT_RUN** |
| True music21 `9.7.1..<10` parsing + slash chords + key analysis | **BLOCKED: library absent** |
| Clean dependency-complete Python 3.11–3.13 venv install | **NOT_RUN** |
| Python 3.12 interpreter | **NOT_RUN** |
| Basic Pitch 0.4.0 TensorFlow under 3.11 | **NOT_RUN** |
| Actual Windows installer and Cubase GUI import/export | **NOT_RUN** |
| Live provider/model performance, artistic quality | **NOT_RUN** |

There is no local music21, Python 3.11, nor a complete audited offline
wheelhouse. PyPI DNS is unavailable in the execution container. Do not
invent a successful music21 test or call this production release `PASS`.

## Smallest remaining acceptance action

On a connected machine with Python 3.13:

```sh
python3.13 -m venv .venv-music21
. .venv-music21/bin/activate
python -m pip install -e .
python scripts/accept_music21_core.py
```

Windows equivalent uses `py -3.13 -m venv .venv-music21` and
`.venv-music21\\Scripts\\Activate.ps1`.

**Pass only on explicit `PASS_REAL_MUSIC21_ACCEPTANCE` exit 0**.
The existing runner tests six actual harmony symbols, slash-chord bass
and accompaniment, source MIDI preservation, and C-major/A-minor
music21 key estimation.

After that, separately run a real Windows/Cubase roundtrip and any
Basic Pitch/model checks required for the intended commercial scope;
no automatic promotional "release" is authorized.

## Governance

- Only the isolated branch
  `fix/midivolt-rc-closeout-python313-gates-20261102` was modified.
- Protected `main` was **not** modified.
- GitHub Actions were **not** used.
- No release tag or production deployment was created.
