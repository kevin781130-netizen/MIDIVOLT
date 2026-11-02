# MIDIVOLT RC — real P0 resolution and GitHub-matched suite (2026-11-02)

**Disposition: P0_CLI_DEPENDENCY_DIAGNOSTIC_FIXED; OVERALL_PRE_MACHINE_NOT_CERTIFIED.**

## Actual execution (not mock product code)

Runtime Linux Python 3.13.5, current restored real MIDIVOLT application source.

Added three *exact, SHA-matching GitHub test files* from the current candidate branch, verified locally via `git hash-object`:
- `tests/test_runtime_compatibility.py`: `512b193344b20cde3fce817d50c6ad6f22effe45`
- `tests/test_chord_symbol_normalization.py`: `1e55aa745ec04a52593946303376776bc61c9019`
- `tests/test_cli_music21_lazy_gate.py`: `7ad77685fd1143e6ff0657d4eb857d36981eb28d`

Before the fix, the three-suite run was **18 passed / 2 failed / 1 skipped**. Two genuine failures: `midivolt analyze --input missing.mid` and `midivolt arrange --input missing.mid` emitted input file errors instead of the actionable `music21 is required` diagnostic in a `music21`-absent runtime.

**Production fix committed on isolated branch only**: `src/midivolt/cli.py`, the actual SHA-matching working-tree source, now preflights `music21` immediately before input-I/O for these two symbolic-music commands. It remains lazily loaded for CLI help and audio-only commands. This does **not** fake, vendor, or mock the missing library.

```sh
cd /mnt/data/mdv_run
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests \
  --junitxml=/mnt/data/MIDIVOLT_POSTFIX_GITHUB_SUBSET_20261102.xml
# 98 passed, 1 skipped in 9.25s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python scripts/verify_ai_offline.py \
    --junit /mnt/data/MIDIVOLT_OFFICIAL_40_AFTER_P0_20261102.xml
# 40 passed, 0 failed, 0 skipped; PASS_SUPPORTED_RUNTIME
```

The 1 skipped test calls `pytest.importorskip("music21")`; **it is NOT a successful real-music21 test**. The 98 tests include a subset of restored original GitHub tests and the existing property matrix; this is **NOT** whole-current-checkout `pytest tests`.

- Main JUnit SHA-256: `0712298cba2a50db8a1be476e1759788c7b618f490514e8e13be6a7fbd21b08b`.
- Updated production CLI Git blob SHA: `ffb81cc8ea4ba87a26bcef971bb6dd4f6690da34`.
- Isolated branch fix commit: `6af460ec90fc48ef4d7381a7f2b4135598bc9c5e`.

## Remaining mandatory nonphysical release blockers

1. Whole *exact current Git checkout* complete regression has not been run.
2. Real `music21>=9.7.1,<10` chord parsing, harmony and key-detection acceptance is **BLOCKED**: trusted package absent, container cannot resolve PyPI/GitHub DNS; the PyPI Wheel download also failed.
3. Fully dependency-complete clean Wheel install with verified 13 CLI imports is **BLOCKED**, with no audited offline wheelhouse.

Therefore **do not claim `PASS_PRE_MACHINE` or `only real-machine tests left`**. Actual Windows installer, Cubase GUI roundtrip, trained-model/live provider and, when sold, Basic Pitch WAV/stem acceptance remain future real-workstation checks. No mainline changes and no GitHub Actions. Evidence package: `MIDIVOLT_98_POSTFIX_EVIDENCE_20261102.zip` in conversation artifacts.
