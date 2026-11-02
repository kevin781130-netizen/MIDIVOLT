# MIDIVOLT RC — AI runtime gate alignment and executed preflight (2026-11-02)

## Scope and release decision

**TARGETED_CODE_GATE_PASS; OVERALL_RC_NOT_YET_CERTIFIED.** No changes to `main`, no GitHub Actions, no real model inference or Cubase.

Previous `scripts/verify_ai_offline.py` certified only Python 3.11 even after the core project declared `>=3.11,<3.14`. It now reads the exact core `requires-python` range from `pyproject.toml`, certifies a real in-range interpreter, and fails closed on missing/unparseable/wrong-project Python policy. Unsupported interpreters remain blocked unless the diagnostic flag is used, which cannot claim a supported-runtime PASS.

## Actually executed on isolated Linux Python 3.13.5

GitHub file bytes were reconstructed in a separate local directory. `git hash-object` matched the actual GitHub blob IDs:

| Source | Git blob SHA-1 |
| --- | --- |
| `scripts/verify_ai_offline.py` | `d38cb75d3e9bb6e6599dcb301f0ad3faaba6baaa` |
| `tests/test_verify_ai_offline_gate.py` | `6b1accd6f44a4d7646d50df4dae343eff766ac58` |
| `tests/test_verify_ai_offline_process.py` | `65d73bc58be6206bd1f9ac1f3478473ae99c6d44` |
| `scripts/verify_rc_source_contract.py` | `0f4707a1d3d04265f437e4714f531d1126cc1103` |
| `tests/test_verify_rc_source_contract.py` | `94de9e7c1f32b6fd21a24bf98c169f75f5e1cf88` |
| `pyproject.toml` | `972f6e39dabd956e3095c29fa41cee26a8242005` |

Actual command:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_verify_ai_offline_gate.py \
  tests/test_verify_ai_offline_process.py \
  tests/test_verify_rc_source_contract.py
# 21 passed, 5 subtests passed in 3.75s
```

The process-level tests use **synthetic 40-case pytest fixtures** to verify the real gate controller end-to-end. This is NOT the real MIDIVOLT product's 40-test AI suite. Observed controller behavior:
- Supported Python 3.13.5 + 40 synthetic cases: `PASS_SUPPORTED_RUNTIME`, exit 0.
- Required suite file removed: `BLOCKED_MISSING_TEST_FILES`, exit 4.
- Unrecognized project Python policy: `BLOCKED_PROJECT_POLICY`, exit 4.

The actual full-product 40-test gate **has not been rerun on this branch**. Prior 2026-11-01 40-test results are historical evidence only.

## Remaining acceptance (do not waive)

1. Run the **real** `python scripts/verify_ai_offline.py` against the complete repo checkout on a supported interpreter. The isolated checkout only had the specified validator, its tests, and the source-contract test; no complete application source was mounted.
2. Re-run the modified 2026-11-02 Wheel builder and clean-install gate suites against GitHub-matching source, then build/install the full **current** candidate with dependencies; old diagnostic Wheels do not certify this branch.
3. Run real `music21` harmony/lead-sheet/key-detection acceptance and a clean dependency-complete environment; `music21` and trusted offline wheels were unavailable, and the package index could not be reached in the isolated test container.
4. Physical workstation acceptance: Windows PowerShell installer and actual Cubase MIDI Type 1 roundtrip; if included in sales scope, Python 3.11 Basic Pitch WAV/stems acceptance and real OpenAI/Ollama or pretrained model output-quality/licensing checks.

The last two categories require working application/model environments; items 1–3 are still unverified and must **not** be relabeled as physical-machine-only residuals. The code changes in this slice are limited to the AI gate, its regressions and this report.
