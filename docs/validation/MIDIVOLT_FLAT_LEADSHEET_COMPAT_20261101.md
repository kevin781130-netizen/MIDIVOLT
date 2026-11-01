# MIDIVOLT — lead-sheet flat spelling compatibility (2026-11-01)

## Change

`src/midivolt/theory.py` now accepts conventional flat spellings for
chord roots and slash basses, and normalizes them to music21's required
hyphen notation before calling `harmony.ChordSymbol`.

Examples:

| User / lead-sheet spelling | music21 input |
|---|---|
| `Bbmaj7` | `B-maj7` |
| `Ebm7` | `E-m7` |
| `Ab7` | `A-7` |
| `Dbm7b5` | `D-m7b5` |
| `C7/Bb` | `C7/B-` |
| `Bb7/Eb` | `B-7/E-` |

Alterations remain untouched: `G7b9` stays `G7b9`, and `F7#9` stays
`F7#9`. The normalizer only converts a flat immediately following the
root letter or slash-bass note.

The official music21 harmony documentation specifies hyphen notation for
flat chord roots and basses; it also documents slash basses:
https://music21.org/music21docs/moduleReference/moduleHarmony.html

The import of `music21` in `theory.py` was moved into the two operations
that actually need it (`parse_chords` and `estimate_key`). Importing the
module and using the pure spelling normalizer no longer requires music21.
The declared core dependency remains `music21>=9.1,<10`; it has NOT been
made optional.

## Executed tests

```sh
PYTHONPATH=src python3 -m pytest -q tests/test_chord_symbol_normalization.py \
  --junitxml=MIDIVOLT_FLAT_NOTATION_20261101.junit.xml
# .........s [100%]
# 9 passed, 1 skipped in 0.05s
```

- 9 pure normalization cases: **PASS**.
- 1 real music21 integration test (root pitch classes, slash bass pitch
  classes and chord intervals): **SKIPPED**, because music21 is not installed.

JUnit SHA-256:
`$(python3 -c 'import hashlib;print(hashlib.sha256(open("/mnt/data/MIDIVOLT_FLAT_NOTATION_20261101.junit.xml","rb").read()).hexdigest())')`

## Python/runtime blocker, verified

- Available interpreter: **Python 3.13.5 only**.
- Python 3.11: **NOT AVAILABLE**.
- `music21`: **NOT INSTALLED**.
- `curl https://pypi.org/simple/music21/`: DNS resolution failed.
- `uv python install 3.11`: failed after 3 retries; DNS could not resolve
  GitHub's python-build-standalone release host.
- No dependency was silently substituted and no fake music21 implementation
  was used.

Therefore no real music21 chord parsing, accompaniment generation, or key
analysis is claimed as passed in this step. Those acceptance tests are
committed and will run when the supported runtime and declared dependency
are available.

## Source provenance

- Exact source commit pinned by the offline source builder:
  `4e235224f15a6fca34d94db3ce77274e9b7a6a42`
- Source transport: **40/40 Git blob SHAs PASS**, including all
  **36/36 MIDIVOLT Python modules**.
- `src/midivolt/theory.py` blob:
  `1146296459a163f82af6eb79f2d1033d1acd0fc2`
- `tests/test_chord_symbol_normalization.py` blob:
  `1e55aa745ec04a52593946303376776bc61c9019`
- README documents supported conventional flat spellings.
- No Wheel was built in this step; Python 3.11/music21 were unavailable.
- No GitHub Actions run; `main` unchanged.

**Disposition:** notation normalization and offline unit tests pass.
Actual music21 integration and Python 3.11 runtime acceptance remain open.
