# MIDIVOLT RC — actual installed Wheel MIDI core end-to-end (2026-11-02)

## Verified result: PASS_INSTALLED_WHEEL_CORE_E2E (NOT PASS_PRE_MACHINE)

This run **rebuilt a genuine MIDIVOLT 0.1.0rc1 Wheel**, installed it in a fresh Python 3.13.5 virtual environment, confirmed MIDIVOLT imports from the installed venv site-packages (not the working-tree source), and executed real installed CLI launchers.

**Actual application chain:**
1. `midivolt-prompt` generated a 4-track MIDI from a C-major 4-bar prompt.
2. `midivolt-prompt` extended that MIDI into a 6-track, physically serialized candidate.
3. `midivolt-review propose` locked all four original tracks, created a review manifest, and `preview` verified the diff.
4. `midivolt-review apply` **without `--approve` returned exit 2**, producing no artifact.
5. `apply --approve` successfully published a new six-track approved file; all four original tracks and the source file SHA were preserved.
6. `midivolt-cubase prepare --ppq 220` generated a real Type-1 Standard MIDI File.
7. `midivolt-cubase compare --strict` verified **112 note-on events**, **0 missing, 0 added**, metadata-preserving exact match.

**84 separate original product regression test cases passed against the installed Wheel** using `python -I -m pytest`, with **0 failed, 0 skipped**. Includes an explicit provenance assertion that `midivolt.__file__` resolves to the new virtualenv's installed package. Covered AI-MIDI protocol with loopback, SMF Type 0/1 preservation, prompt composition, review/approval, MIDI serialization and bridges.

- 36/36 production module files in the built Wheel matched the corresponding tested product source.
- Built Wheel SHA256: `2504f74163dc43a1a7d45543f3e0f30d1123dc325396b16e73bedd825324856c`.
- 84-test JUnit SHA256: `8f0254faf283b03e41b9f0d897da2b70f34521bba9633e2a2894312768d62f0d`.
- Complete user-side evidence archive SHA256: `8ad0a906a6ba47e2c39cf12060ce610acd5b3002f91a859f16d6a746f5d2bd8c`.
- Archive name: `MIDIVOLT_REAL_INSTALLED_WHEEL_E2E_84PASS_20261102.zip`, containing the actual Wheel, 4 MIDI files (`source.mid`, `candidate.mid`, `approved.mid`, `cubase-type1.mid`), JSON results, executed command log, actual JUnit XML, reproducer source, and SHA256 inventory.

## Explicit limitations and release blockers

**This is a diagnostic core-product Wheel integration test, NOT a dependency-complete clean installation and NOT an approved release.**

- The new Python 3.13 venv used `pip install --no-index --no-deps` plus a diagnostic .pth link to **real preinstalled `mido`, `pretty_midi`, `numpy`, and `scipy` from a separate existing Python 3.13 environment**. They were not replaced by fake modules; however, dependency isolation is not certified and installed `music21` is absent.
- `music21>=9.7.1,<10` chord/key/arrangement acceptance remains genuinely unexecuted, not mocked or passed.
- Full original GitHub checkout test suite and clean install in a compatible Python **3.11** bootstrap environment are still unexecuted. This runner has only Python 3.13 and outbound HTTPS is blocked even when DNS is bypassed.
- Actual Windows PowerShell installer, Cubase GUI import/export and trained-model inference/music quality remain machine-specific acceptance items.

**Pre-machine disposition: BLOCKED_NOT_READY_FOR_MACHINE_ONLY.** No mainline edits or GitHub Actions. Application code unchanged in this slice; the installed Wheel comes from the product source which had no changed production-module files since the branch's earlier PPQ-fix baseline.
