# MIDIVOLT Windows RC — pre-build source contract (2026-11-01)

## Outcome: source preflight tests PASS, wheel not built

- **Executed:** `python -m pytest -q /mnt/data/midivolt_rc_preflight/tests/test_verify_rc_source_contract.py`
- **Result:** **8 passed in 0.05s** under Linux Python 3.13.5, pytest 9.0.2.
- The eight tests use isolated fixtures and cover valid source metadata,
  missing entrypoint module/callable, empty entrypoint module, unsupported
  Python version contract, missing third-party notices, missing offline
  `--no-index` policy and source-file symlink escape.
- Every tested local code byte was verified against the private GitHub blob:
  - `scripts/verify_rc_source_contract.py`:
    `14bdf8ee2d61d00944cb52b927e5925d3c0ddbd5`
  - `tests/test_verify_rc_source_contract.py`:
    `93c761b1d71a131b5a973f96acbaa6e811667696`

## Actual repository inspection

On this isolated branch, GitHub's recursive tree was read successfully:
**97 tracked files**, including **36 Python source files** within
`src/midivolt/`. `pyproject.toml` declares **13 console scripts**. All
13 target Python modules were found and their `def main(...)` declarations
were inspected from GitHub directly. Windows Installer and Smoke scripts,
package license, notices, packaging README and wheel workflow recipe exist.

The committed preflight checks these conditions locally, plus exact Python
3.11 version metadata, package version identity, ZIP recipe contents,
installer's explicit offline wheelhouse mode, and the smoke entrypoint list.

**Do not interpret fixture tests or GitHub static inspection as an
executed full-source preflight against a complete local checkout.**
That whole-checkout command has not been run yet:

```sh
python scripts/verify_rc_source_contract.py --root .
```

## Remaining release blockers

- Python 3.11 acceptance: NOT_RUN (only Python 3.13 present here).
- Real source wheel creation and clean-venv install: NOT_RUN (no `wheel`
  or `build` in the isolated environment, and package registry DNS blocked).
- Windows PowerShell installer and Cubase DAW: NOT_RUN.
- Trained AI model and musical quality: NOT_RUN.
- GitHub Actions: NOT_USED. Protected `main`: UNCHANGED.

**Disposition:** offline preflight logic is tested and committed. This is
not a wheel-build, Python 3.11, or physical-machine acceptance certificate.
