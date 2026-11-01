# MIDIVOLT approval flow — offline regression evidence (2026-11-01)

## Scope and verdict

**PASS (limited scope): 18 passed in 0.15s.** Tests ran in an isolated
container, without GitHub Actions, network access, AI model inference or DAW.
This is **not** official Python 3.11 / Windows / Cubase acceptance.

Test invocation:

```bash
PYTHONPATH=src python -m pytest -q tests/test_review_engine.py tests/test_approval_snapshot_standalone.py
# .................. [100%]
# 18 passed in 0.15s
```

Runtime: Linux container; Python **3.13.5**; pytest **9.0.2**;
pretty_midi **0.2.11**. MIDIVOLT's declared runtime is
`requires-python = ">=3.11,<3.12"`; the supported Python 3.11 gate remains NOT_RUN.

## Repository-source identity

The following exact repository files were reconstructed in the isolated
test directory and independently checked using `git hash-object`. Every
result matched the GitHub blob SHA on
`fix/midivolt-approved-snapshot-publish-20261101`.

| File | Git blob SHA |
| --- | --- |
| `src/midivolt/review_engine.py` | `ad7f24531666f802f005b6a587f1c369d3d79a3b` |
| `src/midivolt/review_cli.py` | `4749dc56a2a7745a4794ab87c2f631d5454b3197` |
| `src/midivolt/io.py` | `f943c2c3d57891303a93e67236e98dafd06bd98b` |
| `src/midivolt/_approval_snapshot.py` | `75cd3d9a09efbf347fbf49f8f6a9241fc3a6ca30` |
| `tests/test_review_engine.py` | `5cbae9ae7c29a7d4acf5061edc45726a30e27b92` |
| `tests/test_approval_snapshot_standalone.py` | `06968a3f5eacde9936cd4ac8ef84b1e05315b039` |

An empty `midivolt/__init__.py` was added **only in the isolated test
directory** to form the importable package, not as a repository change.

## Covered outcomes

- Review, preview, explicit approval, output MIDI serialization and no overwrite.
- Locked MIDI note/controller/instrument identity; rejected tempo modifications.
- Source and candidate SHA-256 consistency; no in-place/reused manifests.
- **Three race regressions:** reject changed source after review; reject
  changed candidate after review; publish the frozen, approved candidate
  even when the live candidate is modified after snapshot capture.
- **Six dependency-free snapshot regressions:** approved bytes, source edit,
  candidate edit, snapshot immutability, invalid digest and missing candidate.

## Not certified

- Full MIDIVOLT test suite and AI provider-to-MIDI workflow: NOT_RUN in this slice.
- Python 3.11 / Windows installation and Cubase SMF round trip: NOT_RUN.
- Real trained AI models and musical quality: NOT_RUN.
- The snapshot guards bytes but is not a cross-process filesystem transaction.
- GitHub Actions: NOT_USED (no remaining workflow quota).

Next remaining non-hardware action: run broader AI/provider regressions in
an isolated environment with a matching interpreter and full dependencies,
without using GitHub Actions.
