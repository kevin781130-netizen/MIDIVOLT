# MIDIVOLT — Python 3.13 core runtime / Basic Pitch audio split

Date: **2026-11-02**  
Branch: `fix/midivolt-core-python313-audio-extra-gate-20261102`

## Product change

The core MIDI product is no longer artificially restricted to Python 3.11.

- `requires-python = ">=3.11,<3.14"` — core support declaration is now
  Python 3.11, 3.12 and 3.13. Python 3.14 is not claimed by this RC.
- `music21>=9.7.1,<10` — remain on the stable 9.x API line while setting
  the minimum version that declares Python 3.13 compatibility.
- `audio` extra:
  - Basic Pitch 0.4.0 is selected only when `python_version < 3.12`.
  - NumPy 1.x is selected on Python 3.11 for the TensorFlow-based Basic
    Pitch environment.
  - NumPy 2.x is selected on Python 3.12–3.13 for the DSP/audio extra.
  - SciPy remains available for the drum-DSP path.
- `dev` extra uses the same interpreter-specific NumPy split, so the
  Python 3.13 test/development environment does not request NumPy 1.x.
- Updated the README, transcription instructions and missing-Basic-Pitch
  diagnostics to explain the two runtime lanes.

### Upstream compatibility evidence

The upstream music21 v9.7.1 project metadata declares Python 3.13 support
and `numpy>=1.26.4` with no upper bound:
https://github.com/cuthbertLab/music21/blob/v9.7.1/pyproject.toml

Basic Pitch 0.4.0 advertises Python classifiers through 3.11 and pins
TensorFlow below 2.15.1 for Python 3.11+:
https://github.com/spotify/basic-pitch/blob/main/pyproject.toml

The project therefore keeps Basic Pitch on its Python 3.11 lane rather
than allowing its old TensorFlow constraint to block core MIDI on 3.13.

## Executed Python 3.13.5 diagnostics

### Runtime-matrix tests

```sh
PYTHONPATH=src python3 -m pytest -q tests/test_runtime_compatibility.py
# 6 passed
```

The same six tests were then run with imports forced to the package
installed from the newly built Wheel (not the source checkout):
`6 passed in 0.07s`.

Tests verify:
- Core Python specifier accepts 3.11, 3.12 and 3.13, and rejects 3.14.
- Basic Pitch is selected only on 3.11.
- NumPy 1.x is selected on 3.11 and NumPy 2.x on 3.12/3.13.
- Missing Basic Pitch gives actionable Python 3.11 guidance in both
  single-file and batch transcription paths.

JUnit SHA-256 (source run):
`20480b5a14ad16ae2100146c2ba44032148dab7fcdc3316c115b9ca203a68f44`

JUnit SHA-256 (installed Wheel run):
`53ebfc48218f3d213fcf023176800117b258be3271b7df0133ff9a22c7db496c`

Test source Git blob:
`512b193344b20cde3fce817d50c6ad6f22effe45`.

### Real diagnostic Wheel and installed CLI

- Wheel: `midivolt-0.1.0rc1-py3-none-any.whl`
- Size: **84,852 bytes**
- SHA-256:
  `d7d0477e7ef53324ffea5361692a6024273cf82c92c4ae03694f5f9c845f18c9`
- Built with the real setuptools backend on Python 3.13.5.
- Fresh Python 3.13.5 venv installation: PASS (`--no-index --no-deps`;
  dependencies were not available offline).
- Wheel source parity: **36/36 product Python modules** match the pinned
  GitHub source commit.
- Console entry points: **13/13** installed `--help` invocations PASS.
- Wheel integrity: ZIP CRC PASS, 43/43 RECORD rows and hashes PASS,
  all 13 entry points present.
- Installed package path was confirmed under the fresh venv's
  `site-packages/midivolt`, not the source checkout.

### Actual MIDI generation on Python 3.13.5

Ran the installed `midivolt-prompt` command:

```sh
midivolt-prompt --prompt "Full song, 8 bars in D minor at 110 bpm" \
  --out python313-core-demo.mid
```

Result: deterministic rules engine, **8 bars / 110 BPM / 4 editable
tracks / 168 notes** (Chords, Melody, Bass, Drums). MIDI was reopened
with `pretty_midi` and the four tracks and note events were confirmed.
No LLM inference or pretrained model was used.

### Explicit missing-dependency boundary

`music21` is not installed in this offline container. A real installed
Wheel invocation of:

```sh
midivolt create --chords Bbmaj7 --out should-not-exist.mid
```

returned exit **2**, emitted the actionable missing-`music21` message,
and created **no MIDI file**. This is a safe failure, **not** a successful
chord-generation test.

## Still blocked / not claimed

- DNS resolution for `pypi.org` fails in the execution container.
- Python 3.11 is not installed here.
- Actual `music21` installation, chord parsing, voicing/arrangement and
  key-analysis execution: **NOT RUN**.
- Basic Pitch 0.4.0 and its TensorFlow backend on Python 3.11:
  **NOT RUN**; its platform-specific model backend also needs target-machine
  verification.
- Python 3.12 runtime execution: **NOT RUN**; marker selection is tested.
- Windows/Cubase GUI, VST3 and trained AI model inference: **NOT RUN**.
- The Wheel is a diagnostic artifact, not a production release.

## Source provenance and governance

- Immutable source commit:
  `c65806b6b67ecab6e5fd1a5f2c3f8aefb5e2ddf1`
- Offline source transport: **40/40 Git blob SHA checks PASS**,
  including **36/36 Python modules** across six parts.
- Offline Wheel builder now pins this exact source commit.
- `main` was not modified.
- GitHub Actions was not used.
