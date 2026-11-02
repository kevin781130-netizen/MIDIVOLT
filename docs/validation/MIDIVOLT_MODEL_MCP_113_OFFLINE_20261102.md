# MIDIVOLT — official model subprocess + MCP integration test closeout (2026-11-02)

## Disposition

**OFFLINE_APPLICATION_SUBSET=113_PASS_1_SKIP_0_FAIL; OVERALL_PRE_MACHINE=BLOCKED.**

Actual execution on the restored real MIDIVOLT source, Linux Python 3.13.5, without GitHub Actions, external model inference, or a modified `main`.

## New genuinely executed GitHub tests

| Original GitHub test file | Git blob SHA-1 (matched local exact bytes) | Result |
| --- | --- | --- |
| `tests/test_models.py` | `42c453e125f05231437d0ffa5caefa00c015e3a0` | 7/7 PASS |
| `tests/test_tsov_mcp.py` | `e56fbb673630f2ea45428cbfd799a96e40b02639` | 8/8 PASS |

The real model subprocess test checks candidate MIDI generation, source track protection, guarded proposal approval, bad assets, out-of-range parameters, inference failure cleanup, and empty-model rejection using a small **synthetic model runner**. It does **not** test trained model accuracy. The real TSOV bridge tests exercise JSON-RPC stdio with a **fake local server** (read/write permissions, errors, notice handling, project traversal rejection, subprocess cleanup and explicit apply protection); they do **not** certify an installed TSOV upstream server.

Actual command:

```sh
cd /mnt/data/mdv_run
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests \
    --junitxml=/mnt/data/MIDIVOLT_113_GITHUB_EXACT_20261102.xml

# 113 passed, 1 skipped in 14.77s
```

**JUnit SHA-256**: `30fb6083c924feed24907992c1382c02621a98282dbbdee78cda9250804ccc11`.

The set includes previously restored real-product regression tests, of which some have small formatting differences from their GitHub blobs. This run is **not** the full original GitHub checkout test suite. The single skip is the real `music21` harmony test: do not label it a pass.

Evidence archive `MIDIVOLT_113_OFFLINE_EVIDENCE_20261102.zip` (conversation attachment) SHA-256: `58ff1a98c5e22bd19542d4fc92a56754983afc69cb62cbb65d547848aa65bcf9`.

## Remaining non-machine blockers

1. Full current-repository `pytest tests` has NOT been executed against an identical Git checkout; local worktree contains only a restored subset.
2. Real `music21 >=9.7.1,<10` is not installed. PyPI package URL and checksum were confirmed, but attempts to retrieve it failed due to blocked DNS / download service in the executor. No stub library was used.
3. Complete offline/online dependency wheelhouse for a clean `pip install` and verified 13 CLI imports is not available in the executor.
4. Legacy model-specific environment lifecycle requires Python 3.10/3.11 and is separate from the Python 3.11–3.13 core; the available Python 3.13 executor cannot certify the upstream model lifecycle. Do not silently skip this check if included in release scope.

**The candidate is not marked PASS_PRE_MACHINE.** No production code changed in this slice; the two official test files already existed in GitHub. No tag, no merge, no Actions.
