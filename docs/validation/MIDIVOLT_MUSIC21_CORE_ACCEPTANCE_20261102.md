# MIDIVOLT — Real music21 core acceptance gate

Date: **2026-11-02**  
Branch: `fix/midivolt-core-python313-audio-extra-gate-20261102`

## Scope prepared

Added `scripts/accept_music21_core.py` and documented it in the README.
The runner is fail-closed: it reports PASS only when a real
`music21>=9.7.1,<10` installation is present on CPython 3.11–3.13.

The real-engine checks cover:

1. Lead-sheet parsing and pitch-class validation for `Bbmaj7`, `Ebm7`,
   `C7/Bb`, `Bb7/Eb`, `Dbm7b5`, and `C/E`.
2. Rejection of invalid root `H-7`.
3. Real chord/Bass MIDI generation for `C7/Bb Fmaj7/A`, including exact
   chord pitches, slash-bass MIDI notes, timing, and preservation of the
   original melody and tempo.
4. Real `Stream.analyze('key')` path through MIDIVOLT for C major and
   A minor fixtures built from the Krumhansl-Schmuckler pitch-class profiles.

This is an integration acceptance runner, not a mock-based success claim.

## Current execution result

**BLOCKED — real music21 was not available in this execution environment.**

- Runtime: Python 3.13.5.
- `music21`: not installed.
- Attempted isolated installation of `music21==9.7.1`: failed before package
  resolution because DNS lookup for PyPI failed
  (`Temporary failure in name resolution`).
- No music21 wheel or source distribution was found in the local filesystem
  or available package cache.
- No chord parsing, accompaniment generation, or key-detection assertion
  is marked PASS in this report.

The runner intentionally returns `BLOCKED_MUSIC21_NOT_INSTALLED` (exit 2)
in this condition. It must not silently skip the integration gate.

## Reproducible next execution

On a supported machine with package-index access, create an isolated venv and
run:

```powershell
py -3.13 -m venv .venv-music21
.venv-music21\Scripts\Activate.ps1
python -m pip install -e .
python scripts/accept_music21_core.py
```

Expected successful status: `PASS_REAL_MUSIC21_ACCEPTANCE`.

If the target machine has no network, provision an audited wheelhouse
containing MIDIVOLT's project dependencies and music21 9.7.1 dependencies,
then install with `pip --no-index --find-links <wheelhouse> -e .`.

## Governance

- Source branch only; `main` unchanged.
- No GitHub Actions used.
- No claim of successful real music21 execution until the runner exits 0.
