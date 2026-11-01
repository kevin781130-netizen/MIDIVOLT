# MIDIVOLT AI → MIDI → Review: 40-test offline regression (2026-11-01)

## Executed result: 40 PASS, diagnostic runtime only

Executed on an isolated Linux system with Python **3.13.5**, pytest **9.0.2**,
pretty_midi **0.2.11**. No paid inference, real AI model, GitHub Actions,
Windows, or Cubase was used.

```sh
PYTHONPATH=src python -m pytest -q \
  tests/test_ai_provider_to_review_e2e.py \
  tests/test_review_engine.py \
  tests/test_approval_snapshot_standalone.py \
  tests/test_candidate_cleanup_standalone.py \
  tests/test_provider_contract_standalone.py \
  --junitxml=MIDIVOLT_BROAD_OFFLINE_20261101.junit.xml

# ........................................ [100%]
# 40 passed in 2.73s
```

JUnit attributes: tests=40, failures=0, errors=0, skipped=0,
time=2.732 seconds. JUnit SHA-256:
`343b234837bb74d10cce55333bf9e3b3204c710f9e300f128886e13e59795357`.

Suite partition:
- 5 provider HTTP fixture → MIDI → review/approval E2E
- 12 proposal/review engine regressions
- 6 approved-byte snapshot regressions
- 5 unpublished candidate cleanup regressions
- 12 provider completion regressions

## Source integrity

Each tested source and test file was verified using `git hash-object` and
matched its GitHub blob SHA on the branch before this report was committed.
No source substitutions or mock implementations of MIDIVOLT production logic.

- `ai_cli.py`: `b07f1e3d41ddd2ccc034d40303e9955e6f910d61`
- `ai_midi.py`: `e6f17e80220b8c3d209b03dc8f2fb2796cccc611`
- `prompt_music.py`: `b6d8496cb28563bdfc87971685a901b8ddc2304a`
- `io.py`: `f943c2c3d57891303a93e67236e98dafd06bd98b`
- `review_engine.py`: `ad7f24531666f802f005b6a587f1c369d3d79a3b`
- `review_cli.py`: `4749dc56a2a7745a4794ab87c2f631d5454b3197`
- `_approval_snapshot.py`: `75cd3d9a09efbf347fbf49f8f6a9241fc3a6ca30`
- `_candidate_cleanup.py`: `cbfd0b0ef850932a7a0c06b1b3b47be4c30b1c56`
- `_provider_contract.py`: `312091068d2fa51d24c189e0be8b26e509f3a42f`
- `test_ai_provider_to_review_e2e.py`: `cb6915116d8964320bb3e4ee2247894e5b86ec9e`
- `test_review_engine.py`: `5cbae9ae7c29a7d4acf5061edc45726a30e27b92`
- `test_approval_snapshot_standalone.py`: `06968a3f5eacde9936cd4ac8ef84b1e05315b039`
- `test_candidate_cleanup_standalone.py`: `320164e40bca73f082ea0aafa8390c68d0e63d5d`
- `test_provider_contract_standalone.py`: `06a77d249ad22c01a853b90ccea26bcf4c71faf5`

## Python 3.11 gate: BLOCKED, not passed

MIDIVOLT's `pyproject.toml` declares `>=3.11,<3.12`. The isolated
runtime only has 3.13.5. An explicit attempt to provision Python 3.11 through
`uv python install 3.11` failed because GitHub download DNS resolution was
unavailable. **No tests were executed under Python 3.11.**

To avoid falsely certifying the wrong runtime, the committed
`scripts/verify_ai_offline.py` exits status 3 with `BLOCKED_PYTHON`
on Python 3.13 unless `--diagnostic-unsupported-python` is explicitly set.

The following two commands were actually executed:

```sh
python scripts/verify_ai_offline.py
# {"status":"BLOCKED_PYTHON", "expected":"3.11.x", "actual":"3.13.5", "test_count":0}
# exit 3

python scripts/verify_ai_offline.py \
  --diagnostic-unsupported-python \
  --junit MIDIVOLT_40_DIAGNOSTIC_20261101.junit.xml
# 40 passed in 2.72s
# status: PASS_DIAGNOSTIC_UNSUPPORTED_RUNTIME
```

Exact checked-in runner blob SHA:
`b6e6b6fdfbec9c333d4148066eb6f671ceff1baf`.

## Remaining acceptance

1. **Python 3.11 supported-runtime**: NOT_RUN due interpreter provisioning.
2. Whole repository suite (beyond the specified 40 tests): NOT_RUN here.
3. Real Ollama/OpenAI trained-model output quality and licensing: NOT_RUN.
4. Physical Windows/Cubase Type-1 MIDI roundtrip and VST/DAW/UI: NOT_RUN.

This report is a diagnostic regression artifact, not a declaration of
product release or hardware acceptance. No changes to `main`; no Actions used.
